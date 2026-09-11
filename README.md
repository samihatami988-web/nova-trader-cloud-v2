# NOVA Trader V7.1.0 — Multi-Timeframe Candle Brain

Adds a conservative OHLCV technical-analysis overlay to the V7 Universal Multi-Market engine.

- PAPER/SHADOW only; live execution remains hard-locked.
- Binance Spot/Futures public klines for top CEX markets.
- 5m/15m/1h/4h EMA, RSI, ATR, VWAP, structure, S/R, breakout/retest, volume and candle-pattern features.
- Existing V7 flow/momentum scores remain primary; candle intelligence is a weighted overlay.
- Strong high-confidence multi-timeframe contradiction can block an entry.
- Meme/launch logic remains realtime/event-driven.

See `DEPLOY_V7.1_FA.txt` for deployment steps and optional environment variables.
