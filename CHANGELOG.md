# NOVA Trader V7.2.2

- Added visible OpenAI HTTP status, latency, error type/message, attempts, successes and detailed error counters.
- Added Northflank-safe `[NOVA][OpenAI]` diagnostic log lines.
- Fixed AI success accounting: attempts and successful analyses are now counted separately.
- Fixed major-perp AI cache key fallback when a CEX/perp candidate has no mint.
- Raised default OpenAI timeout to 20s while keeping calls off the meme/launch hot path.
- Trading/risk thresholds remain unchanged from V7.2.1.
