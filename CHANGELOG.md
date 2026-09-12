# Changelog

## 7.2.1 — OpenAI AI Brain
- Added real OpenAI Responses API integration for major perpetual markets.
- Added strict structured JSON assessment: LONG/SHORT/WAIT, confidence, regime, risk, bounded score adjustments, reasons.
- Added asynchronous AI worker and cache so LLM latency never blocks the trading loop.
- Meme/launch hot path remains LLM-free and event-driven.
- Added high-confidence contradiction veto for major perps only.
- Added `/api/ai-analysis` and dashboard OpenAI AI Brain telemetry.
- API key remains server-side only.
- Risk guards and LIVE execution hard-lock remain authoritative.
