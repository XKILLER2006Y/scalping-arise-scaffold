# E2E Test Infra: Scalping Arise Trading Bot

## Test Philosophy
- Opaque-box, requirement-driven derived from ORIGINAL_REQUEST.md.
- Methodology: Category-Partition + BVA + Pairwise + Workload Testing across Backend, Frontend, and Auto-Trade Loop.

## Feature & Acceptance Inventory
| # | Feature / Criterion | Source | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---------------------|--------|:------:|:------:|:------:|:------:|
| 1 | Backend Pytest Suite Passing | ORIGINAL_REQUEST §Acceptance | 5 | 5 | ✓ | ✓ |
| 2 | Frontend Production Build | ORIGINAL_REQUEST §Acceptance | 5 | 5 | ✓ | ✓ |
| 3 | Core Auto-Trading Loop Execution | ORIGINAL_REQUEST §Acceptance | 5 | 5 | ✓ | ✓ |
| 4 | Market Data & Slicing | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 5 | Execution Broker & Paper Portfolio | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- Backend Runner: `.venv/bin/python -m pytest backend/tests -q`
- Frontend Runner: `npm run build` in `frontend/`
- Auto-Trading Loop E2E Runner: `.venv/bin/python -m pytest backend/tests/test_auto_trade_loop.py -q`
- Directory layout: `backend/tests/`

## Acceptance Criteria
1. Backend test suite (`.venv/bin/python -m pytest backend/tests -q`) runs and passes completely without errors.
2. Frontend build (`npm run build` in the `frontend` directory) completes successfully with no linting or type errors.
3. The core auto-trading loop (`auto_trade_loop` in `main.py`) can run without throwing unhandled exceptions.
