# scan-log-v1.0 benchmark results

2000 documents, 13 canonical entity types. F1 shown per entity per adapter; "—" means the adapter produced no matching predictions or the entity has no gold spans in this run; "skipped" means the adapter's dependency/API key wasn't available in this environment.

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
| maskflow_deep | 52.374 | 13.318 | 27.133 | 7.7 | 0 |
| maskflow_patterns | 1.842 | 0.465 | 0.762 | 0.0 | 0 |
| presidio_oob | 45.470 | 11.107 | 20.035 | 1.2 | 0 |
| naive_regex | 0.212 | 0.052 | 0.089 | 0.0 | 0 |

### Audit cost (false positives on log noise)

| adapter | false positives / 1000 records | total FPs | overall precision |
|---|---|---|---|
| maskflow_deep | 428.0 | 856 | 88.4% |
| maskflow_patterns | 298.0 | 596 | 91.6% |
| presidio_oob | 544.0 | 1088 | 72.7% |
| naive_regex | 433.0 | 866 | 79.1% |

### Scan-pipeline plumbing check

PASS — `run_pipeline(--deep)` over all 2000 records reproduced `detect()`'s per-entity counts exactly (7396 findings across 13 entity types); field extraction + streaming aggregation lose nothing.
