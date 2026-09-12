# V7.1.3 Profit Core Restore

- Restored V7.0.0 signal thresholds exactly.
- Restored V7.0.0 Launch score gate exactly.
- Restored V7.0.0 Launch profit-cycle sizing floor.
- Removed Candle score overlay from trading decisions.
- Disabled Candle hard gate permanently for this release; Candle Brain is monitor-only.
- Global Loss Guard now affects only risk sizing and circuit-breaker cooldowns; it does not alter signal thresholds/scores.
- Retained V7.1.1 single-flight dashboard polling and Candle worker isolation.
- Added explicit health/dashboard proof: V7.0 profit core locked.
