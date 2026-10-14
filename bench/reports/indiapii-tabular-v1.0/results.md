# indiapii-tabular-v1.0 benchmark results

300 documents, 8 canonical entity types. F1 shown per entity per adapter. "0.0%" is a *measured* zero -- the adapter made predictions for this type but none matched a gold span. "—" means F1 is undefined: the adapter made no prediction for this type at all (its recognizer / label map doesn't cover it), or the corpus has no gold spans for it. "skipped" means the adapter's dependency/API key wasn't available in this environment.

### Strict-span F1

| entity_type | maskflow |
|---|---|
| AADHAAR | 99.4% |
| BANK_ACCOUNT_IN | 96.0% |
| IFSC | 100.0% |
| INDIAN_MOBILE | 100.0% |
| PAN | 100.0% |
| PERSON_NAME | 98.3% |
| PIN_CODE | 100.0% |
| UPI_VPA | 100.0% |

### Partial-overlap F1

| entity_type | maskflow |
|---|---|
| AADHAAR | 99.4% |
| BANK_ACCOUNT_IN | 96.0% |
| IFSC | 100.0% |
| INDIAN_MOBILE | 100.0% |
| PAN | 100.0% |
| PERSON_NAME | 98.3% |
| PIN_CODE | 100.0% |
| UPI_VPA | 100.0% |

### Latency & memory

| adapter | ms/KB | median ms/doc | p95 ms/doc | peak memory (MB) | doc errors |
|---|---|---|---|---|---|
| maskflow | 69.616 | 50.187 | 678.668 | 183.5 | 0 |
