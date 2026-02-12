# F-002: Fast-Think / Slow-Think Dual-LLM Architecture

## Summary

Run two LLMs in parallel: a fast model for real-time conversation and a slow reasoning model for background research. The slow model indexes insights into a shared store that the fast model picks up on subsequent turns. This solves the fundamental tension between response speed and reasoning depth.

## Architecture: 3-Lane Cognitive System

```
                    ┌─────────────────────────────┐
                    │         Fast-Think           │
                    │  (real-time conversation)    │
                    │  Qwen2.5-1.5B / Phi 3.5     │
                    │                              │
                    │  - Responds in <2s           │
                    │  - Picks up indexed insights  │
                    │  - Dispatches topics to slow  │
                    └──────┬──────────▲────────────┘
                           │ dispatch  │ poll/pickup
                    ┌──────▼──────────┴────────────┐
                    │      Insight Store            │
                    │  (ring buffer, 20 items)      │
                    │  Light bulb UI badge          │
                    └──────▲──────────▲────────────┘
                           │          │
              ┌────────────┴──┐  ┌────┴───────────────┐
              │  Slow-Think A │  │   Slow-Think B     │
              │  (Reviewer)   │  │   (Explorer)       │
              │               │  │                    │
              │  Reviews full │  │  Takes dispatched  │
              │  conversation │  │  topics, researches│
              │  indexes      │  │  deeper, indexes   │
              │  reflections  │  │  findings          │
              └───────────────┘  └────────────────────┘
```

### Roles

- **Fast-Think**: Small, fast model handles real-time conversation. Picks up insights from the store. Dispatches interesting topics to slow-think for deeper research.
- **Slow-Think A (Reviewer)**: Reviews the whole conversation every ~3 turns. Identifies unspoken assumptions, missed connections, or deeper patterns. Indexes reflections.
- **Slow-Think B (Explorer)**: Takes topics dispatched by fast-think. Researches them deeply using the reasoning model's full `<think>` capability. Indexes distilled findings.

Slow-Think A and B share one model instance with different prompts — they alternate tasks in a scheduler queue.

### Future Tier (Not in MVP)

A **middle LLM** between fast and slow that curates/filters slow-think insights. Fast-think polls the middle for relevant items rather than reading the insight store directly. This adds a quality filter and lets the fast model ask targeted questions about the slow model's research.

## Key Technical Discovery

web-llm's `CreateMLCEngine` accepts `string | string[]` — it natively supports loading multiple models into one engine with per-model request locks. Both models share WebGPU VRAM but requests interleave without explicit coordination.

## How It Works

1. User speaks → fast-think responds in <2s using small model
2. After responding, fast-think's reply is analyzed for research-worthy topics
3. Topics get queued for slow-think (explorer role)
4. Every 3 turns, a conversation review task is also queued (reviewer role)
5. Slow-think runs during IDLE/SPEAKING states (pauses when user is talking)
6. Slow-think strips `<think>` tags, distills output into 1-3 sentence insights
7. Insights land in the InsightStore → light bulb badge appears in UI
8. On the next turn, fast-think sees relevant insights as context snippets
9. Fast-think produces a better-informed answer without the latency cost

## Key Considerations

- **GPU sharing**: Both models share WebGPU VRAM. Model pairs must fit in available memory. Fallback: fast-only mode if VRAM insufficient.
- **Cooperative scheduling**: Slow-think yields to fast-think during PROCESSING state. No GPU contention during conversation.
- **Insight freshness**: 5-minute TTL, used-count penalty, relevance scoring. Stale insights get evicted.
- **Token budget**: Fast-think keeps 512-token cap. Slow-think gets 2048 tokens + 30s timeout.
- **Graceful degradation**: If slow model can't load, system works identically to current single-model behavior.

## Model Pairing Recommendations

| VRAM Budget | Fast Model | Slow Model | Total |
|---|---|---|---|
| ~2GB | SmolLM2 360M (0.5GB) | Qwen2.5-1.5B (1.0GB) | ~1.5GB |
| ~4GB | Llama 3.2 1B (0.8GB) | Qwen3 4B (2.8GB) | ~3.6GB |
| ~6GB | Qwen2.5-1.5B (1.0GB) | DeepSeek R1 7B (4.5GB) | ~5.5GB |

## Implementation Sketch

New files (under `web-app/src/lib/`):
- `dualEngine.ts` — Multi-model engine wrapper with cooperative scheduling
- `insightStore.ts` — Ring buffer of 20 insights with relevance scoring
- `slowThinkScheduler.ts` — Background research orchestrator (reviewer + explorer tasks)
- `topicExtractor.ts` — Pure string-ops topic extraction from conversation

Modified files:
- `llm.ts` — Refactor to delegate to DualEngine
- `conversationPack/compose.ts` — Add insights as 5th RAG lane
- `conversationPack/pipeline.ts` — Wire InsightStore into compose
- `conversationPack/types.ts` — Add `'insights'` to Lane type
- `main.ts` — Wire everything + light bulb UI

## Open Questions

- What's the right balance of reviewer vs explorer tasks in the queue?
- Should the light bulb UI show insight source (reviewer vs explorer)?
- When the middle LLM tier is added, does it replace the InsightStore or sit on top of it?
- Should slow-think have access to RAG context, or just conversation history?
