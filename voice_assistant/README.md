# Voice Assistant — Tool-Calling Orchestrator

Text-only REPL that uses Ollama's native tool-calling API to give local LLMs real capabilities (web search, calendar, notes).

## Quick Start

```bash
# From the project root:
pip install -r voice_assistant/requirements.txt
python -m voice_assistant.main
```

## How It Works

```
You type → orchestrator.chat():
  1. Append user message, trim history
  2. POST /api/chat with tools=[web_search, check_calendar, search_notes]
  3. Ollama returns text → display, done
     — or tool_calls → execute → loop back to 2
  4. Max 5 tool iterations, then force text response
```

## Tools

| Tool | Status | Description |
|------|--------|-------------|
| `web_search` | Functional | Brave Search + DuckDuckGo fallback |
| `check_calendar` | Stub | Returns fake calendar data |
| `search_notes` | Stub | Returns fake notes data |

## Configuration

Reads from parent `.env` file. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `qwen3:8b` | Preferred model (Qwen 3 has native tool support) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `BRAVE_API_KEY` | _(empty)_ | Brave Search API key (optional, DDG is free fallback) |

## Commands

- `quit` / `exit` / `q` — Exit the REPL
- `clear` — Reset conversation history
- `--debug` flag — Enable verbose logging
