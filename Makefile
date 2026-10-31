.PHONY: help install test lint build clean release demo

PYTHON ?= python3

help:            ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:         ## Install in editable mode (zero dependencies)
	$(PYTHON) -m pip install -e .

test:            ## Run the full unit test suite
	$(PYTHON) -m unittest discover -s tests -t . -v

build:           ## Build sdist + wheel into dist/
	$(PYTHON) -m pip install --upgrade build
	$(PYTHON) -m build

clean:           ## Remove build artefacts and caches
	rm -rf build dist *.egg-info .pytest_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

demo:            ## Run the end-to-end demo script
	$(PYTHON) scripts/demo.py

release: clean build  ## Build a release (then: twine upload dist/*)
	@echo "Built:"; ls -1 dist/
