# indiapii-v1.0 benchmark results

2000 documents, 17 canonical entity types. F1 shown per entity per adapter. "0.0%" is a *measured* zero -- the adapter made predictions for this type but none matched a gold span. "—" means F1 is undefined: the adapter made no prediction for this type at all (its recognizer / label map doesn't cover it), or the corpus has no gold spans for it. "skipped" means the adapter's dependency/API key wasn't available in this environment.

### Strict-span F1

| entity_type | maskflow | presidio_oob | presidio_custom | mask_privacy | naive_regex | llm_detector |
|---|---|---|---|---|---|---|
| AADHAAR | 98.4% | — | 96.6% | — | 54.4% | skipped |
| AADHAAR_MASKED | 100.0% | — | — | — | — | skipped |
| ABHA_ADDRESS | 100.0% | — | — | — | — | skipped |
| ABHA_NUMBER | 93.3% | — | — | — | — | skipped |
| BANK_ACCOUNT_IN | 93.4% | — | — | 38.7% | — | skipped |
| DRIVING_LICENCE | 100.0% | — | — | — | — | skipped |
| GSTIN | 100.0% | — | — | — | — | skipped |
| IFSC | 100.0% | — | — | — | — | skipped |
| INDIAN_ADDRESS | 0.0% | 0.0% | 0.0% | 0.0% | — | skipped |
| INDIAN_MOBILE | 99.0% | 94.9% | 94.9% | 42.2% | 65.1% | skipped |
| INDIAN_PASSPORT | 100.0% | — | — | — | — | skipped |
| PAN | 100.0% | — | 100.0% | — | 94.1% | skipped |
| PERSON_NAME | 29.9% | 18.6% | 18.6% | 18.7% | — | skipped |
| PIN_CODE | 100.0% | — | — | — | 100.0% | skipped |
| UPI_VPA | 100.0% | — | — | — | — | skipped |
| VEHICLE_REG | 100.0% | — | — | — | — | skipped |
| VOTER_ID | 100.0% | — | — | — | — | skipped |

### Partial-overlap F1

| entity_type | maskflow | presidio_oob | presidio_custom | mask_privacy | naive_regex | llm_detector |
|---|---|---|---|---|---|---|
| AADHAAR | 98.4% | — | 96.6% | — | 54.4% | skipped |
| AADHAAR_MASKED | 100.0% | — | — | — | — | skipped |
| ABHA_ADDRESS | 100.0% | — | — | — | — | skipped |
| ABHA_NUMBER | 93.3% | — | — | — | — | skipped |
| BANK_ACCOUNT_IN | 93.4% | — | — | 38.7% | — | skipped |
| DRIVING_LICENCE | 100.0% | — | — | — | — | skipped |
| GSTIN | 100.0% | — | — | — | — | skipped |
| IFSC | 100.0% | — | — | — | — | skipped |
| INDIAN_ADDRESS | 43.3% | 48.2% | 48.2% | 50.7% | — | skipped |
| INDIAN_MOBILE | 99.0% | 94.9% | 94.9% | 42.2% | 83.7% | skipped |
| INDIAN_PASSPORT | 100.0% | — | — | — | — | skipped |
| PAN | 100.0% | — | 100.0% | — | 94.1% | skipped |
| PERSON_NAME | 52.4% | 30.4% | 30.4% | 30.4% | — | skipped |
| PIN_CODE | 100.0% | — | — | — | 100.0% | skipped |
| UPI_VPA | 100.0% | — | — | — | — | skipped |
| VEHICLE_REG | 100.0% | — | — | — | — | skipped |
| VOTER_ID | 100.0% | — | — | — | — | skipped |

### Latency & memory

| adapter | ms/KB | median ms/doc | p95 ms/doc | peak memory (MB) | doc errors |
|---|---|---|---|---|---|
| maskflow | 67.655 | 19.241 | 28.017 | 1.6 | 0 |
| presidio_oob | 57.170 | 14.857 | 27.958 | 0.3 | 0 |
| presidio_custom | 52.705 | 14.650 | 23.831 | 0.5 | 0 |
| mask_privacy | 46.699 | 13.165 | 19.020 | 10.4 | 0 |
| naive_regex | 0.089 | 0.024 | 0.041 | 0.1 | 0 |
| llm_detector | skipped (ANTHROPIC_API_KEY not set) | | | | |
