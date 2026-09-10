# integration-parity-v1 benchmark results

300 documents from `indiapii-v1.0`, routed through each framework integration's masking layer and compared to `maskflow.mask()` / `maskflow.unmask()` (the `core` reference). Detection parity = the `(entity_type, value)` set the wrapper masks equals core's, per document. Round-trip = the wrapper's own unmask restores the document byte-exact. Streaming = the masked text fed back through the shared `StreamingUnmasker` at 1-byte and random chunk splits reassembles exactly. Every column should be 100% — a divergence is a wrapper bug.

| integration | detection parity | round-trip | streaming | divergences |
|---|---|---|---|---|
| litellm | 100.0% | 100.0% | 100.0% | — |
| langchain | 100.0% | 100.0% | 100.0% | — |
| llamaindex | 100.0% | 100.0% | 100.0% | — |
| mcp | 100.0% | 100.0% | 100.0% | — |
