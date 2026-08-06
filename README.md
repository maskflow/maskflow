# MaskFlow

PII protection for AI workflows. Mask PII before it reaches an LLM (Claude, OpenAI, or anything
else), unmask the response.

```python
from maskflow import mask_and_call

response = mask_and_call(prompt, call_fn)
```

## Packages

- [`core/`](core) — the detection and masking engine
- [`sdk/python/`](sdk/python) — the Python SDK (`pip install maskflow-sdk`), see its README for usage
