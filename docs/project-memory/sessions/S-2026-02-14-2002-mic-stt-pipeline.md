# Session

Session-ID: S-2026-02-14-2002-mic-stt-pipeline
Title: Milestone 5 — iPhone Mic to Server STT to Display Text
Date: 2026-02-14
Author: Claude

## Goal
Add bidirectional audio: browser mic streams to Mac server via WebRTC, server runs Whisper STT, transcribed text displayed in browser UI.

## Context
Milestone 4a (TTS to WebRTC) is complete. The current flow is type text, server runs TTS, audio streams back. This milestone adds the reverse direction: speak into mic, server transcribes, text appears in UI.

## Plan
1. Create `engine/stt.py` — faster-whisper wrapper with lazy model loading
2. Update `gateway/webrtc.py` — add `on("track")` handler, mic buffering, `start_recording()`/`stop_recording()`
3. Update `gateway/server.py` — handle `mic_start`/`mic_stop` WS messages, return `transcription`
4. Update browser (`web/index.html`, `web/app.js`, `web/styles.css`) — mic capture via getUserMedia, sendrecv, Record button, transcription display
5. Update `scripts/smoke_test.py` — STT round-trip test
6. Add `faster-whisper>=1.0` to `requirements.txt`

## Changes Made
- `engine/stt.py` — New file: Whisper STT wrapper (lazy-load, transcribe PCM to text)
- `gateway/webrtc.py` — Added `on("track")` handler, `_recv_mic_audio()` background task, `start_recording()`/`stop_recording()` methods
- `gateway/server.py` — Added `mic_start`, `mic_stop` WS message handlers, sends `transcription` response
- `web/index.html` — Added STT section with Record button and transcription display area
- `web/app.js` — Changed to sendrecv, added getUserMedia for mic, Record toggle, transcription display
- `web/styles.css` — Added `.btn-record`, `.recording` animation, `#transcription-display` styles
- `scripts/smoke_test.py` — Added Test 5 (STT round-trip) and Test 5b (empty input)
- `requirements.txt` — Added `faster-whisper>=1.0`

## Decisions Made
- **WebRTC sendrecv** over WebSocket blobs: reuses existing connection, lower latency, works well on iOS Safari
- **faster-whisper** over openai/whisper: 4x faster, less memory, CPU mode sufficient for short utterances
- **base** model size: good accuracy/speed balance (~75MB)
- **Mic mute/unmute** approach: mic track added at offer time but muted, unmuted only when recording — avoids re-negotiation
- **Simple list buffer** for mic frames (not ring buffer): recording has clear start/stop boundaries

## Open Questions
- Should we add a "hold to talk" mode in addition to toggle?
- Consider adding language detection or multi-language support later

## Links

Commits:
- (pending commit)

PRs:
- None

ADRs:
- None
