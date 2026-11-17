# One-word commands. Run `make` to list them.
.DEFAULT_GOAL := help
PY ?= python3

help:  ## list commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-8s %s\n", $$1, $$2}'

install:  ## install the one dependency (openai SDK) plus pytest
	$(PY) -m pip install -r requirements.txt pytest

mock:  ## offline demo of the loop, no API key (about 1 second)
	$(PY) skillopt_mini.py --task dates --mock --epochs 3 --runs-dir runs/mock

train:  ## live: train the bank-statement skill (about 16 min on the Groq free tier)
	$(PY) skillopt_mini.py --task transactions --epochs 3

demo:  ## live: seed skill vs trained skill on the November statement (about 2 min)
	$(PY) ledger.py statements/nov2026.csv --compare

test:  ## offline tests
	$(PY) -m pytest -q
