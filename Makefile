PY=.venv/bin

setup:
	python3 -m venv .venv
	$(PY)/pip install -e "backend[dev]" -e mcp-server
	@test -f .env || cp .env.example .env

dev-backend:
	cd backend && ../$(PY)/uvicorn app.main:app --reload --port 8000

test:
	cd backend && ../$(PY)/pytest -q

lint:
	$(PY)/ruff check backend

NODE22=$(HOME)/.nvm/versions/node/v22.22.2/bin

web-install:
	cd web && PATH=$(NODE22):$$PATH npm install

dev-web:
	cd web && PATH=$(NODE22):$$PATH npx vite

test-web:
	cd web && PATH=$(NODE22):$$PATH npx vitest run && PATH=$(NODE22):$$PATH npx tsc --noEmit

build-web:
	cd web && PATH=$(NODE22):$$PATH npm run build

# Backend with the deterministic demo model: no API key, network or rate limits needed for the chat
dev-backend-demo:
	cd backend && LLM_PROVIDER=demo ../$(PY)/uvicorn app.main:app --reload --port 8000
