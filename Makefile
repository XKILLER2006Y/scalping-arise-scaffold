test:
	.venv/bin/python -m pytest backend/tests -q

run:
	.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000

front:
	cd frontend && npm install --no-audit --no-fund && npm run build

up:
	docker compose up --build
