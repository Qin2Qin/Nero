.PHONY: backend backend-demo frontend dev reset-demo test smoke-ui

backend:
	cd backend && if [ -f ../.env ]; then set -a; . ../.env; set +a; fi; DEMO_MODE=$${DEMO_MODE:-false} ../.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000

backend-demo:
	cd backend && DEMO_MODE=true ../.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev -- --host 0.0.0.0

dev:
	@echo "Run backend and frontend in separate terminals:"
	@echo "  make backend"
	@echo "  make frontend"

reset-demo:
	rm -f backend/nero.db
	@echo "Demo state reset. Start backend with make backend-demo."

test:
	.venv/bin/python -m pytest backend/tests

smoke-ui:
	cd frontend && npm run smoke:ui
