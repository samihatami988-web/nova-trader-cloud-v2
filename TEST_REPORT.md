# NOVA Trader V7.1.0 — Build Test Report

Validated in the build workspace:

- Python compile: `app.py` — PASS
- Dashboard JavaScript syntax (`node --check`) — PASS
- Indicator logic with synthetic bullish/bearish 240-candle series — PASS
- Multi-timeframe aggregation (5m/15m/1h/4h) — PASS
- Strong opposite candle confirmation gate — PASS
- FastAPI smoke: `/health` returns `7.1.0` — PASS
- Authenticated `/api/candle-intelligence` — PASS
- Authenticated `/api/dashboard` contains `candle_intelligence` — PASS
- Invalid NOVA Admin Key rejected with 401 — PASS
- LIVE execution remains hard-locked in source — PASS

Not validated inside this isolated build container:

- Live outbound Binance HTTP calls (container DNS/network is unavailable here).
- Northflank container build/runtime behavior.

After Northflank deployment, confirm `/health`, the Candle Intelligence card, and that `TRACKED` becomes non-zero after the first candle refresh.
