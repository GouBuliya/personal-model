.PHONY: check test lint lint-check format-check shell scans secret pii language docs \
	check-harness

check: lint shell test scans docs

test:
	PERSOME_LLM_MOCK=1 uv run pytest -m "not macos and not integration" -q

lint: lint-check format-check

lint-check:
	uv run ruff check .

format-check:
	uv run ruff format --check .

shell:
	bash -n install.sh uninstall.sh resources/*.sh .githooks/pre-push \
		templates/compound-engineering/.githooks/pre-push

scans: secret pii language

secret:
	uv run python scripts/secret_scan.py

pii:
	uv run python scripts/pii_scan.py

language:
	uv run python scripts/language_scan.py

docs:
	uv run python scripts/check_doc_links.py

check-harness:
	uv run pytest tests/test_compound_engineering.py -q
