# scan-log-v1.0

Synthetic **log-shaped** PII corpus for `maskflow scan`. Records are nginx access lines, structured JSON app logs, multi-line stack traces, LLM request dumps, and worker-task logs. PII values are synthetic and checksum-valid where a checksum exists (Aadhaar, PAN, GSTIN, IFSC, UPI VPA, Indian mobile, credit card), cross-checked against the packs' own validators by `generator/generate.py`'s `self_check()`. The hard negatives are the PII-lookalike noise real logs carry -- request/trace ids, UUIDs, git SHAs, epoch-millis timestamps, internal `10./172.16./192.168.` IPs in log position, base64/`sk_test_` blobs, `File.java:142` frames. **None of these values belong to any real person, account, or credential.**

- License: CC-BY-4.0
- Seed: 20260910
- Records: 2000
- Gold PII spans: 6542
- Decoy spans (log noise, never gold): 6122

## Records per shape

- access_log: 400
- app_json: 400
- llm_traffic: 400
- stack_trace: 400
- worker_log: 400

## Spans per label

- AADHAAR: 348
- API_KEY: 176
- AWS_KEY: 130
- CREDIT_CARD: 400
- DOTTED_CLASSPATH: 1802
- EMAIL: 931
- EPOCH_MS: 118
- FILE_FRAME: 1002
- GSTIN: 400
- IFSC: 400
- INDIAN_MOBILE: 651
- INTERNAL_IP: 400
- IP_ADDRESS: 400
- JWT: 135
- OPAQUE_KEYISH: 400
- PAN: 400
- PERSON_NAME: 1600
- REQUEST_ID: 1200
- TRACE_ID: 400
- UPI_VPA: 571
- USER_AGENT: 400
- UUID4: 400

## Gold entity taxonomy

- AADHAAR
- API_KEY
- AWS_KEY
- CREDIT_CARD
- EMAIL
- GSTIN
- IFSC
- INDIAN_MOBILE
- IP_ADDRESS
- JWT
- PAN
- PERSON_NAME
- UPI_VPA

## Known limitations

- English only; the shapes are hand-authored templates, not sampled from real production logs.
- `PERSON_NAME` depends on the spaCy NER pass (`--deep`); recall on it reflects `en_core_web_sm`.
- Internal `10./172.16./192.168.` IPs are scored as decoys: for a PII-exposure audit a private-range IP is not personal data. MaskFlow has no private-IP suppression today, so `IP_ADDRESS` precision here is a real measured property, not a corpus artifact.
