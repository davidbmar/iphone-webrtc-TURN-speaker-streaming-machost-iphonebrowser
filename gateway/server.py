"""Gateway server — HTTP static serving + WebSocket signaling."""

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from aiohttp import web
from dotenv import load_dotenv

from engine.adapter import list_voices
from gateway.turn import fetch_twilio_turn_credentials

load_dotenv()

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


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
    )
    app = create_app()
    log.info("Serving on http://0.0.0.0:%d", PORT)
    web.run_app(app, host="0.0.0.0", port=PORT)
