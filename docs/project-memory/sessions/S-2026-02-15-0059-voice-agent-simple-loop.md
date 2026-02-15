# Session

Session-ID: S-2026-02-15-0059-voice-agent-simple-loop
Title: Milestone 6 — Voice Agent Simple Loop (mic → STT → LLM → TTS → speaker)
Date: 2026-02-15
Author: Claude

## Goal
Close the loop: user speaks into iPhone mic → server transcribes → LLM generates a reply → TTS speaks the reply back through the iPhone speaker. Creates a voice agent.

## Context
Milestone 5 is complete with two separate working paths:
- Mic → STT → display text
- Type text → TTS → speaker

These paths are disconnected. This milestone connects them into a full voice agent loop.

## Plan
1. Create engine/llm.py — LLM wrapper with Claude Haiku + Ollama support
2. Create engine/conversation.py — Conversation history with sliding window
3. Wire STT → LLM → TTS chain in gateway/server.py on mic_stop
4. Update browser UI with chat bubbles and thinking indicator
5. Update requirements.txt and .env.example

## Changes Made
- **engine/llm.py**: New file. LLM provider abstraction with Claude API (Haiku) and Ollama support. Switchable via LLM_PROVIDER env var, auto-detects based on API key presence. Lazy-loaded clients, thread-pool execution.
- **engine/conversation.py**: New file. ConversationHistory class with 10-turn sliding window. Configurable system prompt via SYSTEM_PROMPT env var.
- **gateway/server.py**: Modified mic_stop handler to chain STT → LLM → TTS when agent_mode is enabled. Sends agent_thinking and agent_reply WS messages.
- **web/app.js**: Added chat bubble helpers, agent_thinking/agent_reply message handlers. Replaced transcription display with conversation log.
- **web/index.html**: Replaced transcription-display div with conversation-log div. Renamed section to "Voice Agent".
- **web/styles.css**: Added chat bubble styles (.msg-user blue right-aligned, .msg-agent dark left-aligned), thinking animation, conversation log container.
- **requirements.txt**: Added anthropic>=0.40, httpx>=0.27.
- **.env.example**: Added LLM_PROVIDER, ANTHROPIC_API_KEY, OLLAMA_MODEL, OLLAMA_URL, SYSTEM_PROMPT.

## Decisions Made
- **Agent loop in server.py, not Session**: Keeps WebRTC session focused on audio; server orchestrates the pipeline.
- **Simple blocking loop**: Full STT → full LLM → full TTS. Streaming pipeline deferred to next milestone.
- **Auto-detect provider**: If ANTHROPIC_API_KEY is set, use Claude; otherwise fall back to Ollama. Explicit override via LLM_PROVIDER.
- **10-turn sliding window**: Keeps token usage low for a voice agent where deep memory isn't needed.
- **max_tokens=300**: Voice responses should be concise (1-3 sentences).

## Open Questions
- Streaming pipeline (sentence-level TTS while LLM still generating) — next milestone
- Interrupt handling (speak while agent is responding)

## Links

Commits:
- (pending)
