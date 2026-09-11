NOVA Trader V6.8.2 — Engine Control Center
===========================================

WHAT'S NEW
----------
A manual ON/OFF control layer for each trading engine:

- SCALP
- PUMP
- SNIPER
- LAUNCH
- PERP LONG
- PERP SHORT
- REALTIME PULSE
- PAID STREAM
- SELECTIVE ROUTER

IMPORTANT BEHAVIOR
------------------
Turning an engine OFF blocks NEW entries from that engine.
It does NOT abandon an already-open position.

Existing positions continue to be managed by automatic protective exits:
- Stop / hard-loss controls
- Profit Lock / Micro Profit exits
- Event-driven exit when available
- Fallback position watcher
- Capital / Survival / Equity guards

PAID STREAM
-----------
PAID STREAM OFF:
- prevents new subscribeTokenTrade requests
- unsubscribes active paid token-trade subscriptions through the cost supervisor
- keeps free NewToken/Migration websocket streams online
- does not disable fallback position management

REALTIME PULSE OFF:
- blocks new realtime pulse/sniper entries
- does not automatically disable Paid Stream, because Paid Stream may still be
  useful for Launch and event-driven exit.

SAFETY SYSTEMS
--------------
The Engine Control Center intentionally does NOT provide OFF switches for:
- Capital Shield
- Survival Guard
- Global Equity Guard
- Exit engine / existing-position management
- Cost Optimizer

These are protective systems.

BACKEND DEPLOY
--------------
Repository: samihatami988-web/nova-trader-cloud-v2

Keep the repo clean with:
Dockerfile
README.md
app.py
requirements.txt

Replace app.py with backend/app.py.
Dockerfile and requirements.txt are included for a clean upload.

Northflank:
Start Build -> main -> latest commit -> Deploy.

Expected:
GET /health
version = 6.8.2

GET /api/engines
returns current control state.

POST examples (requires NOVA Admin Key header):
/api/engines/scalp/off
/api/engines/scalp/on
/api/engines/launch/off
/api/engines/paid_stream/off

DASHBOARD
---------
Repository: samihatami988-web/nova-trader-mobile

Replace index.html with dashboard/index.html.

The new "Engine Control Center" card provides all switches from the phone.

NOTE
----
PAPER profitability is not guaranteed. The controls are designed to let you
isolate weak engines during testing without turning off risk management.
