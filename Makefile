.PHONY: install dev test lint macos

install:
	python3 -m pip install -e '.[dev]'

dev:
	nalu-runtime

test:
	pytest -q

lint:
	ruff check services tests

macos:
	scripts/build-macos-app.sh
