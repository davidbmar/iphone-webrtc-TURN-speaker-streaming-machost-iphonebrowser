# Session

Session-ID: S-2026-02-15-1749-rich-model-selection
Title: Rich Model Selection with Ollama Default + Cloud API Fallback
Date: 2026-02-15
Author: Claude

## Goal
Replace the flat provider dropdown with a grouped model selector that shows installed Ollama models, downloadable models, and cloud APIs. Support downloading new models from the UI.

## Context
Current model selector is a flat `<select>` with provider names. Ollama model is hardcoded at startup via `OLLAMA_MODEL` env var. Users can't switch models or download new ones at runtime.

## Plan
1. Add curated model catalog and Ollama API integration to engine/llm.py
2. Add set_model/pull_model WS handlers to gateway/server.py
3. Add download progress bar to web/index.html
4. Implement grouped optgroup select + download UI in web/app.js
5. Add progress bar and optgroup styles to web/styles.css

## Changes Made
(to be filled)

## Decisions Made
- Grouped `<select>` with `<optgroup>` rather than custom panel (iOS Safari renders native section headers)
- Curated model list (10 models) rather than full Ollama library
- Auto-select after download completes
- Graceful degradation when Ollama is offline

## Open Questions
None

## Links

Commits:
- (to be filled)
