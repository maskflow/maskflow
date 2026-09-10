# scan-log-v1.0 benchmark results

2000 documents, 13 canonical entity types. F1 shown per entity per adapter. "0.0%" is a *measured* zero -- the adapter made predictions for this type but none matched a gold span. "—" means F1 is undefined: the adapter made no prediction for this type at all (its recognizer / label map doesn't cover it), or the corpus has no gold spans for it. "skipped" means the adapter's dependency/API key wasn't available in this environment.

### Strict-span F1

| entity_type | maskflow_deep | maskflow_patterns | presidio_oob | naive_regex |
|---|---|---|---|---|
| AADHAAR | 100.0% | 100.0% | — | 67.4% |
| API_KEY | 98.0% | 98.0% | — | — |
| AWS_KEY | 100.0% | 100.0% | — | 100.0% |
| CREDIT_CARD | 97.8% | 97.8% | 100.0% | 86.2% |
| EMAIL | 100.0% | 100.0% | 79.0% | 100.0% |
| GSTIN | 100.0% | 100.0% | — | — |
| IFSC | 100.0% | 100.0% | — | — |
| INDIAN_MOBILE | 100.0% | 100.0% | 85.0% | 95.0% |
| IP_ADDRESS | 66.7% | 66.7% | 66.7% | 59.6% |
| JWT | 99.3% | 99.3% | — | 99.3% |
| PAN | 100.0% | 100.0% | — | 100.0% |
| PERSON_NAME | 87.9% | 94.7% | 47.9% | — |
| UPI_VPA | 100.0% | 100.0% | — | — |

### Partial-overlap F1

| entity_type | maskflow_deep | maskflow_patterns | presidio_oob | naive_regex |
|---|---|---|---|---|
| AADHAAR | 100.0% | 100.0% | — | 67.4% |
| API_KEY | 99.7% | 99.7% | — | — |
| AWS_KEY | 100.0% | 100.0% | — | 100.0% |
| CREDIT_CARD | 97.8% | 97.8% | 100.0% | 86.2% |
| EMAIL | 100.0% | 100.0% | 79.0% | 100.0% |
| GSTIN | 100.0% | 100.0% | — | — |
| IFSC | 100.0% | 100.0% | — | — |
| INDIAN_MOBILE | 100.0% | 100.0% | 85.0% | 95.0% |
| IP_ADDRESS | 66.7% | 66.7% | 66.7% | 59.6% |
| JWT | 100.0% | 100.0% | — | 100.0% |
| PAN | 100.0% | 100.0% | — | 100.0% |
| PERSON_NAME | 87.9% | 94.7% | 57.6% | — |
| UPI_VPA | 100.0% | 100.0% | — | — |

### Latency & memory

| adapter | ms/KB | median ms/doc | p95 ms/doc | peak memory (MB) | doc errors |
|---|---|---|---|---|---|
| maskflow_deep | 52.360 | 13.228 | 27.334 | 6.8 | 0 |
| maskflow_patterns | 1.825 | 0.459 | 0.746 | 0.0 | 0 |
| presidio_oob | 45.927 | 11.289 | 20.190 | 2.3 | 0 |
| naive_regex | 0.216 | 0.053 | 0.091 | 0.0 | 0 |

### Audit cost (false positives on log noise)

| adapter | false positives / 1000 records | total FPs | overall precision |
|---|---|---|---|
| maskflow_deep | 428.0 | 856 | 88.4% |
| maskflow_patterns | 298.0 | 596 | 91.6% |
| presidio_oob | 544.0 | 1088 | 72.7% |
| naive_regex | 433.0 | 866 | 79.1% |

### Scan-pipeline plumbing check

PASS — `run_pipeline(--deep)` over all 2000 records reproduced `detect()`'s per-entity counts exactly (7396 findings across 13 entity types); field extraction + streaming aggregation lose nothing.
