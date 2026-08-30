.PHONY: install dev test lint macos macos-check macos-verify

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

macos-check:
	scripts/check-macos-build-environment.sh

macos-verify:
	scripts/verify-macos-release.sh
