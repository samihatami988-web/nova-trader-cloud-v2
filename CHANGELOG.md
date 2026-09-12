# NOVA Trader V7.2.3 — Free AI Mode

- Added zero-cost Local Quant AI for major perpetuals.
- Added LONG / SHORT / WAIT local confidence + regime + risk classification.
- Added automatic OpenAI quota/credit suspension on 429 insufficient_quota / credit_balance_exhausted.
- Prevents repeated paid-API failures after quota exhaustion.
- OpenAI remains optional; local mode stays available with no network calls.
- Fixed stable OpenAI cache lookup for CEX/perp candidates without mint identifiers.
- Added free AI status to health/dashboard payload.
- Preserved meme/launch hot path and V7.0 risk/signal core.
