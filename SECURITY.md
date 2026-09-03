# Security Policy (100% free stack)

- Do NOT commit `.env`, API keys, or credentials. Only `.env.example` is tracked.
- Twelve Data key lives in `backend/.env` (gitignored) or compose secret. Demo-synthetic mode runs with no key.
- Optional API guard: set `SCA_API_KEY` in backend env; clients then send `X-API-Key`. Unset = open demo mode.
- Report suspected secret leaks by rotating the key immediately and purging history with `git filter-repo`, never by posting the value.
- Analysis only. No auto-execution, no withdrawal permissions, no customer funds handling in this scaffold.
