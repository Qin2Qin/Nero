.PHONY: dev demo reset test

dev:
	if [ -f ../.env ]; then set -a; . ../.env; set +a; fi; DEMO_MODE=$${DEMO_MODE:-false} ../.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000

demo:
	DEMO_MODE=true ../.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000

reset:
	rm -f nero.db

test:
	cd .. && .venv/bin/python -m pytest backend/tests
