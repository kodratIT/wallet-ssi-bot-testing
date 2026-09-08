.PHONY: install dev prod test docker clean

# Default python - pakai venv jika ada
PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

install:
	$(PIP) install -r requirements.txt

dev:
	$(PYTHON) run.py

prod:
	$(PYTHON) run.py --prod

# Alternatif legacy
holder:
	$(PYTHON) holder.py

test:
	$(PYTHON) -m pytest tests -v

docker:
	docker-compose up --build

docker-prod:
	docker-compose up --build -d

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .venv venv
