NOVA Trader V6.7.1 — Launch / Token-Trade Hotfix
=================================================

WHY
---
V6.7.0 successfully connected to PumpPortal (HTTP 101) and received new-token
events, but create events were also being counted as Pulse events while actual
Launch Sniper buy/sell trade events stayed at zero.

WHAT V6.7.1 CHANGES
-------------------
- Separates CREATE / BUY / SELL / MIGRATION / PROVIDER messages.
- CREATE events are no longer treated as buy events.
- Captures PumpPortal control/error messages that have no mint.
- Gives fresh launches priority for subscribeTokenTrade slots.
- Rotates old non-position subscriptions when the Free-Lite cap is full.
- Tracks subscription requests/errors and last real trade event.
- Keeps one WebSocket connection.
- Keeps existing entry/risk/security/Edge Governor logic unchanged.
- LIVE execution remains hard locked.

UPLOAD
------
1) Add hotfix_v671.py to nova-trader-cloud-v2 root.
2) Replace Dockerfile with this Dockerfile.
3) Keep final_v670.py, app.py and requirements.txt.
4) Trigger NEW BUILD + DEPLOY in Northflank (restart is not enough).

EXPECTED
--------
/health -> version 6.7.1
/api/dashboard -> realtime_pulse.message_counts
/api/diagnostics/pumpportal -> detailed safe trade-stream telemetry

After 1-3 minutes of active Pump.fun traffic:
- message_counts.create should rise
- message_counts.buy / sell should rise if metered token subscriptions are accepted
- launch_sniper.trades_seen should rise
- Pulse events_total should represent real buy/sell prints, not token creates

If create rises but buy/sell remains 0:
check last_provider_message / trade_subscription_errors.
