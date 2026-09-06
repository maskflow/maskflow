# Runnable example

`anonymized_chain.py` builds an LCEL chain that masks PII before the model
and restores it after, and attaches the leak-guard callback.

```bash
pip install maskflow-langchain
python packages/maskflow-langchain/examples/anonymized_chain.py
```

With `OPENAI_API_KEY` set it calls `gpt-4o-mini`; without one it uses a fake
chat model so the mask/restore round-trip is still visible:

```
you asked   : Please file the return for PAN ABCPE1234F, UPI ramesh@oksbi, email ramesh@example.com.
model saw   : Please file the return for PAN <PAN_1>, UPI <UPI_VPA_1>, email <EMAIL_1>.
you get back: ...
```

`chain.stream(...)` deanonymizes incrementally through
`anonymizer.deanonymizer`; `guard.summary()` reports detected entity types
and counts, never values.
