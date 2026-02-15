"""Gateway server — HTTP static serving + WebSocket signaling."""

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from aiohttp import web
from dotenv import load_dotenv

load_dotenv()  # Must be before engine imports so they see .env vars

from engine.adapter import list_voices
from engine.conversation import ConversationHistory
from engine.llm import generate as llm_generate, is_configured as llm_is_configured, get_provider_name, available_providers
from gateway.turn import fetch_twilio_turn_credentials

log = logging.getLogger("gateway")

PORT = int(os.getenv("PORT", "8080"))
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "devtoken")
ICE_SERVERS_JSON = os.getenv("ICE_SERVERS_JSON", "[]")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
INDEX_TEMPLATE = None  # Loaded on startup


def build_index_html() -> str:
    """Read index.html and inject ICE servers config."""
    raw = (WEB_DIR / "index.html").read_text()
    return raw.replace("__ICE_SERVERS_PLACEHOLDER__", ICE_SERVERS_JSON)


# ── HTTP routes ───────────────────────────────────────────────

async def handle_index(request: web.Request) -> web.Response:
    """Serve index.html with injected config."""
    return web.Response(text=INDEX_TEMPLATE, content_type="text/html")


# ── WebSocket handler ─────────────────────────────────────────

async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    log.info("WebSocket connected from %s", request.remote)

    session = None  # Will hold WebRTC Session once created
    ice_servers = []  # Populated on hello, shared with WebRTC session
    conversation = ConversationHistory()
    agent_mode = llm_is_configured()
    llm_provider = ""  # Empty = use default from env

    async for raw in ws:
        if raw.type != web.WSMsgType.TEXT:
            continue
        try:
            msg = json.loads(raw.data)
        except json.JSONDecodeError:
            await ws.send_json({"type": "error", "message": "Invalid JSON"})
            continue

        msg_type = msg.get("type")
        log.debug("WS recv: %s", msg_type)

        if msg_type == "hello":
            token = msg.get("token", "")
            if token != AUTH_TOKEN:
                await ws.send_json({"type": "error", "message": "Bad token"})
                await ws.close()
                break
            # Fetch fresh TURN credentials (falls back to ICE_SERVERS_JSON)
            ice_servers = await fetch_twilio_turn_credentials()
            if not ice_servers:
                try:
                    ice_servers = json.loads(ICE_SERVERS_JSON)
                except json.JSONDecodeError:
                    ice_servers = []
            voices = [asdict(v) for v in list_voices()]
            await ws.send_json({
                "type": "hello_ack",
                "voices": voices,
                "ice_servers": ice_servers,
                "llm_providers": available_providers(),
                "llm_default": get_provider_name(),
            })

        elif msg_type == "webrtc_offer":
            sdp = msg.get("sdp", "")
            if not sdp:
                await ws.send_json({"type": "error", "message": "Missing SDP"})
                continue
            # Lazy import to avoid loading aiortc until needed
            from gateway.webrtc import Session
            session = Session(ice_servers=ice_servers)
            answer_sdp = await session.handle_offer(sdp)
            await ws.send_json({"type": "webrtc_answer", "sdp": answer_sdp})

        elif msg_type == "start":
            voice_id = msg.get("voice_id", "")
            if session:
                session.start_audio(voice_id)
                log.info("Audio started: %s", voice_id)
            else:
                await ws.send_json({"type": "error", "message": "No WebRTC session"})

        elif msg_type == "stop":
            if session:
                session.stop_audio()
                log.info("Audio stopped")

        elif msg_type == "speak":
            text = msg.get("text", "").strip()
            if not text:
                await ws.send_json({"type": "error", "message": "Empty text"})
            elif session:
                log.info("TTS speak: %r", text[:80])
                await session.speak_text(text)
            else:
                await ws.send_json({"type": "error", "message": "No WebRTC session"})

        elif msg_type == "set_provider":
            provider = msg.get("provider", "")
            if provider in ("claude", "openai", "ollama"):
                llm_provider = provider
                log.info("LLM provider switched to: %s", provider)
                await ws.send_json({"type": "provider_set", "provider": provider})
            else:
                await ws.send_json({"type": "error", "message": f"Unknown provider: {provider}"})

        elif msg_type == "stop_speaking":
            if session:
                session.stop_speaking()
                log.info("TTS playback stopped by user")

        elif msg_type == "mic_start":
            if session:
                async def on_transcription(text, partial):
                    await ws.send_json({"type": "transcription", "text": text, "partial": partial})
                    log.info("Partial transcription: %r", text[:80] if text else "")
                session.start_recording(on_transcription=on_transcription)
                log.info("Mic recording started (live)")
            else:
                await ws.send_json({"type": "error", "message": "No WebRTC session"})

        elif msg_type == "mic_stop":
            if session:
                log.info("Mic recording stopping, final STT...")
                text = await session.stop_recording()
                await ws.send_json({"type": "transcription", "text": text, "partial": False})
                log.info("Final transcription: %r", text[:80] if text else "")

                # Agent mode: STT → LLM → TTS
                if agent_mode and text.strip():
                    conversation.add_turn("user", text)
                    await ws.send_json({"type": "agent_thinking"})
                    active_provider = llm_provider or get_provider_name()
                    log.info("Agent thinking (provider=%s)...", active_provider)
                    try:
                        reply = await llm_generate(
                            conversation.system, conversation.get_messages(), llm_provider
                        )
                        conversation.add_turn("assistant", reply)
                        await ws.send_json({"type": "agent_reply", "text": reply})
                        log.info("Agent reply: %r", reply[:80])
                        await session.speak_text(reply)
                    except Exception as e:
                        log.error("LLM error: %s", e)
                        await ws.send_json({"type": "error", "message": f"LLM error: {e}"})
            else:
                await ws.send_json({"type": "error", "message": "No WebRTC session"})

        elif msg_type == "ping":
            await ws.send_json({"type": "pong"})

        else:
            await ws.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})

    # Cleanup on disconnect
    if session:
        await session.close()
    log.info("WebSocket disconnected")
    return ws


# ── App setup ─────────────────────────────────────────────────

def create_app() -> web.Application:
    global INDEX_TEMPLATE
    INDEX_TEMPLATE = build_index_html()

    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/ws", handle_ws)
    app.router.add_static("/static", WEB_DIR, show_index=False)
    return app


LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


if __name__ == "__main__":
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / "server.log"

    fmt = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)

    filelog = logging.FileHandler(log_file)
    filelog.setLevel(logging.INFO)
    filelog.setFormatter(fmt)

    logging.basicConfig(level=logging.INFO, handlers=[console, filelog])

    # Silence noisy aiortc internals
    logging.getLogger("aiortc").setLevel(logging.WARNING)
    logging.getLogger("aioice").setLevel(logging.WARNING)
    log.info("Logging to %s", log_file)
    app = create_app()

    # HTTPS mode for LAN testing (getUserMedia requires secure context)
    ssl_ctx = None
    if os.getenv("HTTPS"):
        import ssl
        from gateway.cert import ensure_cert

        local_ip = os.getenv("LOCAL_IP", "192.168.1.1")
        cert_path, key_path = ensure_cert(local_ip)
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(str(cert_path), str(key_path))
        log.info("HTTPS enabled with self-signed cert for %s", local_ip)
        log.info("Serving on https://0.0.0.0:%d", PORT)
    else:
        log.info("Serving on http://0.0.0.0:%d", PORT)

    web.run_app(app, host="0.0.0.0", port=PORT, ssl_context=ssl_ctx)
