# Runnable example

`rag_pii.py` builds a small `VectorStoreIndex`, queries it with
`MaskflowNodePostprocessor` masking the retrieved context, and restores the
answer with `unmask_response` and `MaskflowQueryEngine`.

```bash
pip install maskflow-llamaindex "llama-index"
python packages/maskflow-llamaindex/examples/rag_pii.py
```

With `OPENAI_API_KEY` set it uses `gpt-4o-mini`; without one it uses
LlamaIndex's `MockLLM` / `MockEmbedding`, so the point still shows:

```
LLM context    : <PERSON_NAME_1> (PAN <PAN_1>) filed his return on 2024-07-15. ...
```

The synthesizer LLM never sees `ABCPE1234F`; the caller gets it back.
