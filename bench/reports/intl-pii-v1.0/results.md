# intl-pii-v1.0 benchmark results

1800 documents, 12 canonical entity types. F1 shown per entity per adapter. "0.0%" is a *measured* zero -- the adapter made predictions for this type but none matched a gold span. "—" means F1 is undefined: the adapter made no prediction for this type at all (its recognizer / label map doesn't cover it), or the corpus has no gold spans for it. "skipped" means the adapter's dependency/API key wasn't available in this environment.

### Strict-span F1

| entity_type | maskflow | presidio_oob | mask_privacy | naive_regex | llm_detector |
|---|---|---|---|---|---|
| ADDRESS | 99.8% | 0.0% | 56.4% | — | skipped |
| API_KEY | 98.9% | — | — | — | skipped |
| AWS_KEY | 100.0% | — | — | 100.0% | skipped |
| CREDIT_CARD | 99.4% | 100.0% | 78.2% | 60.1% | skipped |
| DATE_OF_BIRTH | 40.9% | 28.9% | 79.8% | — | skipped |
| EMAIL | 100.0% | 100.0% | 100.0% | 100.0% | skipped |
| IBAN | 99.4% | 76.3% | 100.0% | — | skipped |
| IP_ADDRESS | 100.0% | 100.0% | 100.0% | 93.3% | skipped |
| JWT | 98.4% | — | — | 98.4% | skipped |
| PERSON_NAME | 23.3% | 76.9% | 78.8% | — | skipped |
| PHONE | 100.0% | 86.7% | 64.1% | 100.0% | skipped |
| SSN | 100.0% | 100.0% | — | 100.0% | skipped |

### Partial-overlap F1

| entity_type | maskflow | presidio_oob | mask_privacy | naive_regex | llm_detector |
|---|---|---|---|---|---|
| ADDRESS | 99.8% | 6.5% | 81.1% | — | skipped |
| API_KEY | 100.0% | — | — | — | skipped |
| AWS_KEY | 100.0% | — | — | 100.0% | skipped |
| CREDIT_CARD | 99.4% | 100.0% | 78.2% | 60.1% | skipped |
| DATE_OF_BIRTH | 63.6% | 29.5% | 79.8% | — | skipped |
| EMAIL | 100.0% | 100.0% | 100.0% | 100.0% | skipped |
| IBAN | 99.4% | 76.3% | 100.0% | — | skipped |
| IP_ADDRESS | 100.0% | 100.0% | 100.0% | 93.3% | skipped |
| JWT | 100.0% | — | — | 100.0% | skipped |
| PERSON_NAME | 74.0% | 84.1% | 86.1% | — | skipped |
| PHONE | 100.0% | 86.7% | 64.1% | 100.0% | skipped |
| SSN | 100.0% | 100.0% | — | 100.0% | skipped |

### Latency & memory

| adapter | ms/KB | median ms/doc | p95 ms/doc | peak memory (MB) | doc errors |
|---|---|---|---|---|---|
| maskflow | 69.318 | 17.631 | 39.654 | 1.8 | 0 |
| presidio_oob | 45.692 | 12.934 | 18.690 | 3.1 | 0 |
| mask_privacy | 34.485 | 9.848 | 13.717 | 0.5 | 0 |
| naive_regex | 0.248 | 0.068 | 0.123 | 0.0 | 0 |
| llm_detector | skipped (ANTHROPIC_API_KEY not set) | | | | |
