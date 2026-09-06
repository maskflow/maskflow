# maskflow-llamaindex

MaskFlow for [LlamaIndex](https://github.com/run-llama/llama_index): keep
PII out of your RAG pipeline. Three pieces:

- **`MaskflowNodePostprocessor`** — a drop-in for
  `llama_index.core.postprocessor.PIINodePostprocessor` that masks PII in
  retrieved nodes before the response synthesizer. No LLM call, no
  HuggingFace model; MaskFlow's local engine, so Indian identifiers
  (Aadhaar, PAN, GSTIN, UPI, IFSC, ABHA, Indian names / addresses) are
  covered alongside the generic PII.
- **`MaskflowIngestionTransform`** — a `TransformComponent` that masks node
  text at ingestion, so raw PII is never embedded or written to the vector
  store.
- **`unmask_response` / `MaskflowQueryEngine`** — restore the originals in
  the synthesized answer from the per-node maps.

MIT, no gates, no telemetry.

## Install

```bash
pip install maskflow-llamaindex
```

Pulls `llama-index-core`. The first detection run downloads a small spaCy
model for the name/address recognizers; pass `patterns_only=True` to skip
it.

## Query-time masking (index already built)

```python
from maskflow_llamaindex import MaskflowNodePostprocessor, unmask_response

query_engine = index.as_query_engine(node_postprocessors=[MaskflowNodePostprocessor()])
response = query_engine.query("What is Ramesh's PAN?")

# the synthesizer LLM saw "<PAN_1>"; restore the real value for the caller:
answer = unmask_response(str(response), response.source_nodes)
```

Or wrap the engine so you never forget the unmask step:

```python
from maskflow_llamaindex import MaskflowQueryEngine

engine = MaskflowQueryEngine(
    index.as_query_engine(node_postprocessors=[MaskflowNodePostprocessor()])
)
print(engine.query("What is Ramesh's PAN?"))  # already restored, streaming too
```

By default one MaskFlow session is shared across every node in a call, so
`<PERSON_NAME_1>` is the same person in every retrieved chunk.
`PIINodePostprocessor` numbers each node independently.

## Ingestion-time masking (PII never reaches the store)

```python
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from maskflow_llamaindex import MaskflowIngestionTransform

pipeline = IngestionPipeline(
    transformations=[
        SentenceSplitter(),
        MaskflowIngestionTransform(),  # default strategy: redact
        embed_model,
    ]
)
nodes = pipeline.run(documents=docs)
```

The default `strategy="redact"` (`[REDACTED_PAN]`) is **not reversible** —
there is no mapping, so nothing sensitive is stored. Other strategies:
`surrogate` (a plausible fake value) and `replace` (`<PAN_1>` tokens).
`store_mapping=True` writes a reverse map into node metadata; that then
lands in the vector store, so it warns.

## Migrating from `PIINodePostprocessor`

```python
# from llama_index.core.postprocessor import PIINodePostprocessor
from maskflow_llamaindex import MaskflowNodePostprocessor as PIINodePostprocessor
```

`mask_pii(text) -> (str, dict)`, `_postprocess_nodes`, the
`__pii_node_info__` metadata key, and the embed/LLM metadata exclusions are
all the same. `MaskflowNodePostprocessor` does not take an `llm=` argument
(it needs none); it adds `strategy`, `min_confidence`, `patterns_only`,
`consistent_across_nodes`, and `mask_query`.

## PII safety

Query-time maps live only for the query, travelling with
`response.source_nodes`; nothing is logged. The ingestion transform's
default is non-reversible, so it stores no map at all. See `docs/llamaindex.md`
in the MaskFlow repo for the design notes.
