.PHONY: test samples backend frontend

test:
	cd backend && python3 -m pytest

samples:
	python3 scripts/generate_samples.py

backend:
	cd backend && python3 -m uvicorn qalam.main:app --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev
