# NOVA Trader V7.1.2 — Build Test Report

Validated in the build workspace:

- Python compile: `app.py` — PASS
- Dashboard JavaScript syntax (`node --check`) — PASS
- `/health` version = `7.1.2` — PASS
- `/api/dashboard` contains `global_loss_guard` — PASS
- Global guard: no trades -> `NORMAL` — PASS
- 1 consecutive global loss -> `CAUTION`, risk `0.50`, threshold `+3` — PASS
- 2 consecutive global losses -> `COOLDOWN`, entry blocked — PASS
- Expired 2-loss cooldown -> `RECOVERY_PROBE`, risk `0.25`, threshold `+5` — PASS
- 3 consecutive global losses -> `SAFE_MODE`, entry blocked — PASS
- Win after a loss -> `RECOVERING`, staged risk `0.65` — PASS
- Existing V7.1.1 connection-stability logic retained — PASS
- LIVE execution remains hard-locked in source — PASS

Not validated inside this isolated workspace:

- Real Northflank deployment/runtime behavior.
- Live outbound provider behavior after deployment.

After deploy, confirm `/health` reports `7.1.2` and verify the new `Global Loss Guard` card on the dashboard.
