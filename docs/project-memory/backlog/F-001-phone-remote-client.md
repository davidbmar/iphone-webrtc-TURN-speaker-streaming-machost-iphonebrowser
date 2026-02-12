# F-001: Phone Remote Client

## Summary

Split the app so the MacBook handles all heavy compute (LLM, RAG, TTS, FSM/Pipeline) while a phone acts as a wireless thin client over local WiFi. The phone provides STT (mic input), chat display, and audio playback — no model downloads needed on the phone side.

## Motivation

During live testing of DeepSeek R1 via the in-app diagnostic runner, the MacBook proved capable as a local compute host. A phone remote would allow natural conversation from anywhere in the room while the MacBook stays plugged in and running models.

## Architecture

```
┌─────────────────────────┐         WebSocket (LAN)         ┌──────────────────────┐
│       MacBook            │ ◄──────────────────────────────► │       Phone          │
│                          │                                  │                      │
│  FSM + Pipeline          │   ── user text (JSON) ──►       │  STT (Web Speech API)│
│  LLM (DeepSeek/etc)     │   ◄── reply tokens (JSON) ──    │  Chat display        │
│  RAG (embedder+search)  │   ◄── TTS audio (binary WAV) ── │  Audio playback      │
│  TTS (vits-web)         │                                  │  Mic capture         │
│  WebSocket server       │                                  │  Thin HTML client    │
└─────────────────────────┘                                  └──────────────────────┘
```

**MacBook (server)**:
- Runs existing FSM/Pipeline/LLM/RAG/TTS unchanged
- Adds a WebSocket server alongside Vite dev server
- Accepts user text, returns streaming reply tokens + TTS audio blobs

**Phone (client)**:
- Lightweight HTML page served by the MacBook
- Uses Web Speech API for STT (works great on mobile Chrome/Safari)
- Renders chat transcript as messages stream in
- Plays TTS audio blobs as they arrive over WebSocket

## Implementation Sketch

### WebSocket Server (~100 lines)

A small WebSocket server that bridges the phone to the existing pipeline:

```typescript
// server/ws-bridge.ts
import { WebSocketServer } from 'ws';

const wss = new WebSocketServer({ port: 8765 });

wss.on('connection', (ws) => {
  ws.on('message', async (data) => {
    const msg = JSON.parse(data.toString());

    if (msg.type === 'user-text') {
      // Feed into existing pipeline
      // Stream back reply tokens as JSON frames
      // Stream back TTS audio as binary frames
    }
  });
});
```

### Phone Client

Minimal HTML + JS page:
- Connect to `ws://<macbook-ip>:8765`
- Start Web Speech API recognition on mic button tap
- Send recognized text as `{ type: 'user-text', text: '...' }`
- Receive JSON frames for chat display, binary frames for audio playback

### Deployment Options

| Approach | Pros | Cons |
|----------|------|------|
| Standalone Node script (`node server/ws-bridge.ts`) | Simple, no coupling to Vite | Separate process to manage |
| Express + `ws` alongside Vite | Single process | Tighter coupling |
| Vite plugin with WS upgrade | Integrated dev experience | More complex, Vite-specific |

## Key Considerations

- **Latency**: WebSocket over LAN is <10ms round-trip, well within conversational tolerance
- **Audio transport**: Send TTS output as binary WAV frames over WebSocket; phone plays via `AudioContext`
- **STT stays on phone**: Web Speech API runs on-device on mobile — no need to stream raw audio to MacBook
- **No model downloads on phone**: Phone is purely a thin client, all ML models stay on MacBook
- **Discovery**: Phone needs MacBook's LAN IP; could display a QR code on the MacBook UI for easy connect
- **Multiple clients**: WebSocket server could support multiple phones, but single-client is the MVP

## Open Questions

- Should the phone client be a separate Vite entry point or a standalone HTML file?
- Push-to-talk vs continuous listening on the phone?
- How to handle FSM state sync — does the phone need to know about PROCESSING/SPEAKING states for UI feedback?
