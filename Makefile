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
# Which local model: qwen3 (default, best so far) or llama31 (Llama 3.1 8B Instruct). PORT: where llama-server listens.
LOCAL_MODEL ?= qwen3
PORT ?= 8080
ifeq ($(LOCAL_MODEL),llama31)
  MODEL_REPO = bartowski/Meta-Llama-3.1-8B-Instruct-GGUF
  MODEL_FILE = Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
  MODEL_DIR = models/llama31-8b
  MODEL_ALIAS = llama3.1-8b
  MODEL_ARGS =
else
  MODEL_REPO = Qwen/Qwen3-8B-GGUF
  MODEL_FILE = Qwen3-8B-Q4_K_M.gguf
  MODEL_DIR = models/qwen3-8b
  MODEL_ALIAS = qwen3-8b
  # Qwen3 thinking mode is far too slow here: answer directly
  MODEL_ARGS = --chat-template-kwargs '{"enable_thinking":false}'
endif

# make local-model [LOCAL_MODEL=llama31]
local-model:
	$(if $(CA_BUNDLE),SSL_CERT_FILE=$(CA_BUNDLE) REQUESTS_CA_BUNDLE=$(CA_BUNDLE) )$(PY)/modelscope download --model $(MODEL_REPO) --include "$(MODEL_FILE)" --local_dir $(MODEL_DIR)

# --jinja: tool calling. Set LLM_MODEL in .env to the alias shown by `make local-llm-info`.
local-llm:
	llama-server -m $(MODEL_DIR)/$(MODEL_FILE) --alias $(MODEL_ALIAS) --jinja $(MODEL_ARGS) -c 8192 -ngl 99 --port $(PORT)

local-llm-info:
	@echo "LOCAL_MODEL=$(LOCAL_MODEL)  alias=$(MODEL_ALIAS)  url=http://localhost:$(PORT)/v1  file=$(MODEL_DIR)/$(MODEL_FILE)"
