# NOVA Trader V7.1.1 — Connection Stability Hotfix

V7.1.1 is a stability-only release built on the V7.1 Multi-Timeframe Candle Brain. It preserves the trading logic and current PAPER/SHADOW data while fixing dashboard connection flicker and isolating candle-provider latency from the core trading loop.

## What changed

- Single-flight dashboard polling; no overlapping `load()` requests.
- Recursive polling instead of fixed `setInterval` overlap.
- 30-second health cache to reduce API traffic.
- 20-second connection grace window and 3-failure threshold before hard `DISCONNECTED`.
- Transient failures render `RETRYING` while keeping the last good dashboard data visible.
- Authentication/configuration failures still fail immediately.
- Candle OHLCV refresh moved to `candle_intelligence_loop()` background worker.
- Core `engine_loop()` only consumes the latest candle cache and no longer waits for Binance klines.
- Bounded candle HTTP timeout/retry and lower FREE_LITE concurrency.
- Candle worker health fields exposed in `/health` and candle intelligence status.

## Deployment

Replace `app.py` on Northflank and `index.html` on GitHub Pages. Keep the existing database and environment variables. Do not reset the PAPER test.
