.PHONY: rebaseline-bench

rebaseline-bench:
	uv run python -m bench.indiapii.harness rebaseline \
	    --corpus bench/indiapii/data/indiapii-v1.0.jsonl --subset 200 \
	    --out bench/baselines.json
