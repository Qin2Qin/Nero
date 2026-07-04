.PHONY: backend frontend dev reset-demo test

backend:
	cd backend && DEMO_MODE=true uvicorn main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev -- --host 0.0.0.0

dev:
	@echo "Run backend and frontend in separate terminals:"
	@echo "  make backend"
	@echo "  make frontend"

reset-demo:
	rm -f backend/nero.db
	@echo "Demo state reset. Start backend with DEMO_MODE=true."

test:
	python3 -m pytest backend/tests
