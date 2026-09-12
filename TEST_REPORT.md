# NOVA Trader V7.1.3 — Profit Core Restore Test Report

Build target: keep V7.1.2 operational improvements while restoring V7.0.0 trading behavior.

## Passed checks

- Python compile (`app.py`) — PASS
- Dashboard JavaScript syntax (`node --check`) — PASS
- `/health` identity — PASS
  - `version = 7.1.3`
  - `profit_core_version = 7.0.0`
  - `profit_core_locked = true`
  - `candle_decision_impact = false`
- Candle telemetry mutation test — PASS
  - Candle cache was intentionally set strongly bearish against a LONG candidate.
  - `long_score`, `short_score`, `pump_score`, `scalp_score`, and `direction` remained unchanged.
- Candle entry gate — PASS
  - returns `True, monitor_only`; it cannot block an entry.
- Global Loss Guard threshold effect — PASS
  - `global_loss_threshold_add() = 0.0`.
- Global Loss Guard persisted two-loss test — PASS
  - state = `COOLDOWN`
  - entry blocked = true
  - risk multiplier = 0
  - threshold add = 0
- V7.0 function-core comparison — PASS
  - 221 common named functions inspected.
  - 211 are AST-identical to V7.0.0.
  - The remaining changed functions are limited to status/stability, candle metadata attachment, and Global Loss Guard risk/cooldown integration.

## V7.0 functions confirmed identical

- `score_pair`
- `perp_intelligence`
- `suggested_strategy`
- `strategy_entry_score`
- `entry_router_assess`
- `effective_threshold`
- `open_position`
- `manage_positions`
- `manage_positions_safe`
- `pulse_metrics`
- `pulse_gate_metrics`
- `evaluate_pulse_mint`
- `evaluate_launch_mint`
- `choose_sniper_entry`

## Intentional differences from V7.0

- `gate` / `launch_gate`: only add Global Loss Guard circuit-breaker blocking after a losing streak.
- `planned_collateral`: V7.0 sizing multiplied by the Global Loss Guard risk multiplier.
- `launch_position_size`: V7.0 launch sizing floor restored; only Global Loss Guard risk multiplier is added.
- `engine_loop`: V7.0 market logic retained; Candle Intelligence only attaches display metadata.
- `startup`: independent Candle monitor worker retained from V7.1.1.
- `position_watch_loop`: stability release identity only.
- `health` / `dashboard`: expose profit-core lock/monitoring metadata.
- `close_position`: invalidates Global Loss Guard status cache after a trade closes; no exit-rule change.

LIVE execution remains hard-locked. Real Northflank/provider behavior must still be verified after deployment.
