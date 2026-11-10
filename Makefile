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

# Local open-weight model (no cloud LLM). Needs: brew install llama.cpp ; pip install -e "backend[local]"
local-model:
	$(PY)/modelscope download --model Qwen/Qwen2.5-7B-Instruct-GGUF --include "qwen2.5-7b-instruct-q4_k_m*.gguf" --local_dir models/qwen2.5-7b

local-llm:
	llama-server -m models/qwen2.5-7b/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf --alias qwen2.5-7b --jinja -c 8192 -ngl 99 --port 8080
