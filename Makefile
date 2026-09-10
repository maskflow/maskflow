.PHONY: rebaseline-bench rebaseline-bench-intl

rebaseline-bench:
	uv run python -m bench.indiapii.harness rebaseline \
	    --corpus bench/indiapii/data/indiapii-v1.0.jsonl --subset 200 \
	    --out bench/baselines.json

rebaseline-bench-intl:
	uv run python -m bench.intlpii.harness rebaseline \
	    --corpus bench/intlpii/data/intl-pii-v1.0.jsonl --subset 300 \
	    --out bench/baselines-intl.json
