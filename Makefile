.PHONY: rebaseline-bench rebaseline-bench-intl quality-bench quality-bench-smoke

rebaseline-bench:
	uv run python -m bench.indiapii.harness rebaseline \
	    --corpus bench/indiapii/data/indiapii-v1.0.jsonl --subset 200 \
	    --out bench/baselines.json

rebaseline-bench-intl:
	uv run python -m bench.intlpii.harness rebaseline \
	    --corpus bench/intlpii/data/intl-pii-v1.0.jsonl --subset 300 \
	    --out bench/baselines-intl.json

# LLM-utility benchmark: does masking degrade the model's answer? Needs
# ANTHROPIC_API_KEY. ~1200 cached calls (~$1.50 with haiku task / sonnet
# judge); a rerun to regenerate the report costs nothing.
quality-bench:
	uv run python -m bench.indiapii.quality run \
	    --task-model claude-haiku-4-5 --judge-model claude-sonnet-5 \
	    --out bench/reports/indiapii-quality-v1.0

# Cheap end-to-end check: 2 tasks per type, ~36 calls (~$0.05).
quality-bench-smoke:
	uv run python -m bench.indiapii.quality run --sample-per-type 2 \
	    --task-model claude-haiku-4-5 --judge-model claude-haiku-4-5 \
	    --out bench/reports/indiapii-quality-v1.0-smoke
