# indiapii-v1.0 benchmark results

2000 documents, 17 canonical entity types. F1 shown per entity per adapter; "—" means the adapter produced no matching predictions or the entity has no gold spans in this run; "skipped" means the adapter's dependency/API key wasn't available in this environment.

### Strict-span F1

| entity_type | maskflow | presidio_oob | presidio_custom | mask_privacy | naive_regex | llm_detector |
|---|---|---|---|---|---|---|
| AADHAAR | 98.4% | — | 96.6% | — | 54.4% | skipped |
| AADHAAR_MASKED | 100.0% | — | — | — | — | skipped |
| ABHA_ADDRESS | 100.0% | — | — | — | — | skipped |
| ABHA_NUMBER | 93.3% | — | — | — | — | skipped |
| BANK_ACCOUNT_IN | 93.4% | — | — | 37.7% | — | skipped |
| DRIVING_LICENCE | 100.0% | — | — | — | — | skipped |
| GSTIN | 100.0% | — | — | — | — | skipped |
| IFSC | 100.0% | — | — | — | — | skipped |
| INDIAN_ADDRESS | — | — | — | — | — | skipped |
| INDIAN_MOBILE | 99.0% | 94.9% | 94.9% | 41.9% | 65.1% | skipped |
| INDIAN_PASSPORT | 100.0% | — | — | — | — | skipped |
| PAN | 100.0% | — | 100.0% | — | 94.1% | skipped |
| PERSON_NAME | 27.0% | 18.6% | 18.6% | 31.9% | — | skipped |
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
| BANK_ACCOUNT_IN | 93.4% | — | — | 37.7% | — | skipped |
| DRIVING_LICENCE | 100.0% | — | — | — | — | skipped |
| GSTIN | 100.0% | — | — | — | — | skipped |
| IFSC | 100.0% | — | — | — | — | skipped |
| INDIAN_ADDRESS | 43.3% | 48.2% | 48.2% | 57.9% | — | skipped |
| INDIAN_MOBILE | 99.0% | 94.9% | 94.9% | 41.9% | 83.7% | skipped |
| INDIAN_PASSPORT | 100.0% | — | — | — | — | skipped |
| PAN | 100.0% | — | 100.0% | — | 94.1% | skipped |
| PERSON_NAME | 47.3% | 30.4% | 30.4% | 37.7% | — | skipped |
| PIN_CODE | 100.0% | — | — | — | 100.0% | skipped |
| UPI_VPA | 100.0% | — | — | — | — | skipped |
| VEHICLE_REG | 100.0% | — | — | — | — | skipped |
| VOTER_ID | 100.0% | — | — | — | — | skipped |

### Latency & memory

| adapter | ms/KB | median ms/doc | p95 ms/doc | peak memory (MB) | doc errors |
|---|---|---|---|---|---|
| maskflow | 70.073 | 20.194 | 28.206 | 1.6 | 0 |
| presidio_oob | 54.253 | 15.068 | 24.660 | 2.1 | 0 |
| presidio_custom | 56.265 | 15.767 | 24.658 | 0.6 | 0 |
| mask_privacy | 80.841 | 21.710 | 39.393 | 0.7 | 20 |
| naive_regex | 0.138 | 0.036 | 0.073 | 0.0 | 0 |
| llm_detector | skipped (ANTHROPIC_API_KEY not set) | | | | |
