.PHONY: help setup run test clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UV := $(shell command -v uv 2>/dev/null)

# Prefer 3.12, fall back to 3.11 (mediapipe has no wheels for newer CPython).
PYTHON_BOOT := $(shell command -v python3.12 2>/dev/null || command -v python3.11 2>/dev/null)

help:
	@echo "Targets:"
	@echo "  make setup  - create .venv (Python 3.11/3.12) and install dependencies"
	@echo "  make run    - launch HorusAccess"
	@echo "  make test   - run the unit tests"
	@echo "  make clean  - remove .venv"

# Recreate the venv when python or pip is missing (partial/broken envs).
$(PYTHON) $(PIP):
	@if [ -n "$(UV)" ]; then \
		echo "Creating virtualenv with uv (Python 3.12) ..."; \
		$(UV) python install 3.12; \
		rm -rf $(VENV); \
		$(UV) venv --seed --python 3.12 $(VENV); \
	elif [ -n "$(PYTHON_BOOT)" ]; then \
		echo "Creating virtualenv with $$($(PYTHON_BOOT) --version) ..."; \
		rm -rf $(VENV); \
		$(PYTHON_BOOT) -m venv $(VENV); \
	else \
		echo "error: need uv, or python3.12/python3.11 on PATH (mediapipe needs 3.11/3.12)"; \
		exit 1; \
	fi
	@if [ ! -x "$(PIP)" ]; then \
		echo "error: venv has no pip — system Python may be incomplete; install uv and retry"; \
		exit 1; \
	fi

setup: $(PIP)
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt
	@echo ""
	@echo "Done. On Linux, also install system packages if needed:"
	@echo "  Debian/Ubuntu: sudo apt install python3-tk xdotool"
	@echo "  Arch:          sudo pacman -S tk xdotool"
	@echo "Then run: make run"

run:
	@if [ ! -x "$(PYTHON)" ]; then \
		echo "error: .venv missing — run 'make setup' first"; \
		exit 1; \
	fi
	PYTHONPATH=HorusAccess $(PYTHON) HorusAccess/main.py

test:
	@if [ ! -x "$(PYTHON)" ]; then \
		echo "error: .venv missing — run 'make setup' first"; \
		exit 1; \
	fi
	$(PYTHON) -m unittest discover -s tests

clean:
	rm -rf $(VENV)
