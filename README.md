# NOVA Trader V7.1.2 — Global Loss Guard + Adaptive Recovery

V7.1.2 is a defensive hotfix built on V7.1.1. It does **not** replace the existing strategy, Candle Brain, Micro Profit Cycle, Capital Shield, Edge Governor, or connection-stability work.

## New protection layer

The new Global Loss Guard watches **closed trades across all strategies together**.

- `NORMAL`: no recent consecutive global loss restriction.
- `CAUTION`: after the first closed loss, next entries use 50% global risk and require +3 signal points.
- `COOLDOWN`: after 2 consecutive global losses, new entries are blocked for 30 minutes.
- `SAFE_MODE`: after 3+ consecutive global losses, new entries are blocked for 90 minutes.
- `RECOVERY_PROBE`: after cooldown expires, only one reduced-size probe position is allowed, at 25% global risk and +5 threshold points.
- `RECOVERING`: after a recovery win, risk returns gradually at 65% rather than jumping straight back to full size.

The state is reconstructed from persisted `Trade` rows, so the protection survives a Northflank redeploy/restart.

## Launch Sniper change

Launch Sniper now respects the global loss-risk multiplier and no longer forces the previous 0.50 governor floor while in profit-cycle mode. During CAUTION/RECOVERY states its launch score requirement is also tightened.

## Dashboard

A new **Global Loss Guard** card shows:

- Loss streak
- Risk multiplier
- Threshold tightening
- Cooldown remaining
- NORMAL / CAUTION / COOLDOWN / SAFE_MODE / RECOVERY_PROBE / RECOVERING

## Important

- PAPER / SHADOW only; LIVE execution remains hard-locked.
- Do not change `DATABASE_URL` if you want to keep existing PAPER history.
- Do not press `RESET PAPER TEST` before comparing the run.
- This reduces exposure after losses; it cannot make losses impossible.
