.PHONY: install dev test lint sop-audit macos macos-check macos-verify

install:
	python3 -m pip install -e '.[dev]'

dev:
	nalu-runtime

test:
	pytest -q

lint:
	ruff check services tests

sop-audit:
	python3 scripts/audit_product_sop.py

macos:
	scripts/build-macos-app.sh

macos-check:
	scripts/check-macos-build-environment.sh

macos-verify:
	scripts/verify-macos-release.sh
