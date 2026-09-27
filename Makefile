PYTHON ?= python3
VENV := .venv
RUNNER := $(VENV)/bin/python

.PHONY: setup run test clean check package metrics live-check
setup:
	@$(PYTHON) -c 'import sys; assert sys.version_info >= (3, 9), "Python 3.9+ required"'
	@git --version
	$(PYTHON) -m venv $(VENV)
	$(RUNNER) -m pip install --disable-pip-version-check -r requirements.txt

run:
	@$(RUNNER) -m harness tui

test:
	@$(RUNNER) -m unittest discover -s tests -v

check:
	@$(RUNNER) tools/submission.py check

package:
	@$(RUNNER) tools/submission.py package

metrics:
	@$(RUNNER) -m harness.metrics

live-check:
	@$(RUNNER) tools/live_check.py

clean:
	@$(PYTHON) tools/submission.py clean
