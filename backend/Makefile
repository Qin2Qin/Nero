.PHONY: dev reset test

dev:
	DEMO_MODE=true uvicorn main:app --reload --host 0.0.0.0 --port 8000

reset:
	rm -f nero.db

test:
	cd .. && python3 -m pytest backend/tests
