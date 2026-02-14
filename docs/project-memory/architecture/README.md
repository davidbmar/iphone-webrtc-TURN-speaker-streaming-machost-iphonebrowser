# Architecture Documentation

This directory holds system architecture docs for the WebRTC speaker streaming project.

## What Goes Here

- High-level system design (Mac host → WebRTC → iPhone browser)
- Component diagrams (engine, gateway, web client)
- Data flow diagrams (TTS → PCM → ring buffer → WebRTC → Opus → browser)
- Technology stack decisions and rationale

## Current Architecture

```
┌──────────────┐     WebSocket      ┌──────────────┐
│  iPhone      │◄──── signaling ────►│  Mac Host    │
│  Safari      │                     │  (Python)    │
│              │◄──── WebRTC ───────►│              │
│  web/app.js  │     Opus audio      │  gateway/    │
└──────────────┘                     │  engine/     │
                                     └──────────────┘
```

## Key Components

| Component | Path | Role |
|-----------|------|------|
| TTS Engine | `engine/tts.py` | Piper TTS → 48kHz PCM |
| Ring Buffer | `gateway/audio/pcm_ring_buffer.py` | Thread-safe producer/consumer bridge |
| WebRTC Source | `gateway/audio/webrtc_audio_source.py` | PCM → av.AudioFrame → Opus |
| Signaling | `gateway/server.py` | aiohttp WebSocket server |
| TURN Relay | `gateway/turn.py` | Twilio ephemeral credentials |
| Browser Client | `web/app.js` | WebRTC playback + UI |

## Related ADRs

Link to relevant ADRs as they are created.
