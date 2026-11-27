.PHONY: install dev test build-frontend static docker-up docker-down run

PYTHON := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
BACKEND_DIR := backend

install:
	$(PYTHON) -m pip install -r $(BACKEND_DIR)/requirements.txt

dev:
	cd $(BACKEND_DIR) && $(CURDIR)/$(PYTHON) -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

test:
	$(PYTHON) -m pytest tests/ -q

# The dashboard is a static Tailwind SPA served automatically by FastAPI
# (SERVE_FRONTEND=true). No bundler or build step is required - this target
# only validates the entry point exists.
build-frontend:
	@test -f frontend/index.html && echo "dashboard assets are served from frontend/" || (echo "frontend/index.html missing" && exit 1)

static: build-frontend

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down
run:
	./run.sh
