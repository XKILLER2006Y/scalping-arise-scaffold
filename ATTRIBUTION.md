# Attribution

## Hash-sudo-cell/scalping-arise (used with the author's permission)

Ported concepts + adapted code (rewritten to our dict-based pipeline, not copied verbatim):

- `backend/app/strategy/invalidation.py` — rule IDs, veto semantics, and evaluator
  structure adapted from `backend/app/modules/strategies/invalidation.py`
  (CHOCH/regime/breakout/deep-pullback/sweep-acceptance rules).
- `backend/app/strategy/eligibility.py` — gate order and source-policy idea from
  `backend/app/modules/strategies/eligibility.py`
  (analysis → timeframes/candles → features → source → regime).
- `PULLBACK_CONT` strategy (`backend/app/strategy/strategies.py`, engine) —
  modeled on his `pullback_continuation` definition (underlying trend + pullback
  + S/R + momentum recovery + 61.8% depth invalidation).
- `market_data/service.py` LRU+TTL eviction — pattern from
  `backend/app/modules/market_data/cache.py` (`CandleCache`).
- GET `evaluate-quick` / `trace-quick` endpoints — his GET-with-query-params API UX.

His repo: https://github.com/Hash-sudo-cell/scalping-arise (Private license —
ported with explicit permission from the author; no verbatim file copies).
