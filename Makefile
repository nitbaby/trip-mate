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

# Local open-weight model (no cloud LLM, no key, nothing leaves the machine).
# Needs: brew install llama.cpp ; .venv/bin/pip install -e "backend[local]"   (then make local-model, make local-llm)
# If modelscope fails with CERTIFICATE_VERIFY_FAILED (corporate TLS inspection), point it at a CA bundle:
#   make local-model CA_BUNDLE=/path/to/ca.pem   (system certs + your company root certificate in one PEM file)
CA_BUNDLE ?=
local-model:
	$(if $(CA_BUNDLE),SSL_CERT_FILE=$(CA_BUNDLE) REQUESTS_CA_BUNDLE=$(CA_BUNDLE) )$(PY)/modelscope download --model Qwen/Qwen3-8B-GGUF --include "Qwen3-8B-Q4_K_M.gguf" --local_dir models/qwen3-8b

# --jinja: tool calling; enable_thinking=false: Qwen3 answers directly (thinking mode is far too slow here)
local-llm:
	llama-server -m models/qwen3-8b/Qwen3-8B-Q4_K_M.gguf --alias qwen3-8b --jinja --chat-template-kwargs '{"enable_thinking":false}' -c 8192 -ngl 99 --port 8080
