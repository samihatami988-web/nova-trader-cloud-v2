# NOVA Trader V7.1.1 — Stability Hotfix Test Report

Validated in the build workspace:

- Python compile (`python -m py_compile app.py`) — PASS
- Dashboard JavaScript syntax (`node --check`) — PASS
- Import smoke test with isolated SQLite DB — PASS
- `/health` direct function smoke — PASS (`version=7.1.1`)
- Admin auth check with configured test key — PASS
- Candle status includes worker/in-flight fields — PASS
- Static regression: core `engine_loop()` no longer awaits candle refresh — PASS
- Static regression: dedicated `candle_intelligence_loop()` is started on startup — PASS
- Static regression: old `setInterval(load,5000)` removed — PASS
- Static regression: single-flight load guard + 3-failure disconnect threshold present — PASS

Not validated in this isolated runtime:

- Real Northflank scheduling/resource behavior.
- Live outbound Binance/PumpPortal stability under production network conditions.

After deploy, verify:

1. `/health` reports `7.1.1`.
2. Dashboard stays `CONNECTED` during short latency spikes, or shows `RETRYING` instead of flickering `DISCONNECTED`.
3. Candle Intelligence continues updating while core market scans remain responsive.
4. PumpPortal realtime status is evaluated separately from API connection status.
