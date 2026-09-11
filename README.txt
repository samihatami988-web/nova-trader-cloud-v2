NOVA V6.7.3 COST OPTIMIZER

Defaults:
- 3 max paid token subscriptions
- 12 second paid TTL
- 12 new paid subscriptions/minute
- 4000 BUY/SELL events/hour
- wallet reserve floor 0.025 SOL
- dynamic cap reduces to 2 then 1 as hourly budget fills
- free NewToken/Migration streams stay online
- LIVE execution remains locked

Upload hotfix_v673.py and replace Dockerfile.
Then New Build + Deploy in Northflank.

Recommended Northflank env:
PUMPPORTAL_PUBLIC_WALLET=<PUBLIC address only>

Optional:
NOVA_METERED_COST_OPTIMIZER=true
NOVA_METERED_MAX_ACTIVE_SUBS=3
NOVA_METERED_MAX_NEW_SUBS_PER_MIN=12
NOVA_METERED_TOKEN_TTL_SEC=12
NOVA_METERED_MAX_EVENTS_PER_HOUR=4000
NOVA_METERED_WALLET_FLOOR_SOL=0.025
NOVA_METERED_WALLET_CHECK_SEC=60
NOVA_METERED_EST_SOL_PER_10K=0.01
