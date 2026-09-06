# maskflow-langchain

MaskFlow for [LangChain](https://github.com/langchain-ai/langchain): a
reversible PII anonymizer / deanonymizer pair that drops in for
`langchain-experimental`'s Presidio anonymizer, plus a leak-guard callback.

It runs MaskFlow's detection engine, so alongside the usual PII (email,
phone, card numbers, ...) it covers the **Indian identifiers** most tools
miss: Aadhaar, PAN, GSTIN, UPI VPA, IFSC, ABHA, Indian mobile / PIN code /
voter ID / passport / driving licence / vehicle registration, and Indian
names and addresses.

- **Drop-in.** Same method names and mapping shapes as
  `PresidioReversibleAnonymizer`, so migrating a chain is one import line.
- **Streaming.** `anonymizer.deanonymizer` is a streaming-aware `Runnable`;
  a placeholder split across two streamed chunks is stitched back before
  the caller sees it. (Presidio's `RunnableLambda(deanonymize)` only fires
  on the final string.)
- **Leak guard.** An optional callback that fails a call closed if a prompt
  still contains PII.
- **MIT, no gates, no telemetry.**

## Install

```bash
pip install maskflow-langchain
pip install "maskflow-langchain[yaml]"   # if you save/load mappings as .yaml
```

`langchain-core` is a real dependency (`>=0.3,<2`). The first detection run
downloads a small spaCy model for the name/address recognizers; pass
`patterns_only=True` to skip it.

## Migrating from the Presidio anonymizer

```python
# from langchain_experimental.data_anonymizer import PresidioReversibleAnonymizer
from maskflow_langchain import MaskflowReversibleAnonymizer as PresidioReversibleAnonymizer
```

Everything a chain touches keeps working: `.anonymize(text, language=None,
allow_list=None)`, `.deanonymize(text, strategy=exact_matching_strategy)`,
`.reset_deanonymizer_mapping()`, `.deanonymizer_mapping`,
`.anonymizer_mapping`, `.save_deanonymizer_mapping(path)`,
`.load_deanonymizer_mapping(path)`.

Two methods differ, because Presidio recognizer and operator objects have
no MaskFlow equivalent:

| Presidio | maskflow-langchain |
|---|---|
| `add_recognizer(recognizer_obj)` | `add_recognizer(entity_type=..., regex=..., base_confidence=0.6)` |
| `add_operators({e: OperatorConfig(...)})` | `add_operators({e: "replace"\|"redact"\|"mask"\|"hash"\|"surrogate"})` |

`allow_list` is passed to the **constructor** on the reversible anonymizer
(the session is built once); a differing per-call `allow_list` raises.

## Use it in a chain

```python
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from maskflow_langchain import MaskflowReversibleAnonymizer

anonymizer = MaskflowReversibleAnonymizer()
prompt = ChatPromptTemplate.from_template("Answer: {question}")

chain = (
    {"question": lambda x: anonymizer.anonymize(x["question"])}
    | prompt
    | llm
    | StrOutputParser()
    | anonymizer.deanonymizer  # streaming-aware
)

chain.invoke({"question": "Is PAN ABCPE1234F valid for a salaried filer?"})
# the LLM sees "<PAN_1>"; you get "ABCPE1234F" back
for piece in chain.stream({"question": "Confirm receipt of PAN ABCPE1234F"}):
    print(piece, end="")  # deanonymized incrementally
```

## Leak-guard callback

```python
from maskflow_langchain import MaskflowLeakGuardCallback

guard = MaskflowLeakGuardCallback(raise_on_prompt_pii=True)
chain.invoke(x, config={"callbacks": [guard]})
# raises MaskflowPIILeakError if a prompt reaching the LLM still has PII

guard.summary()  # {"prompt": {"PAN": 0}, "completion": {...}} -- counts only, never values
```

Callbacks cannot rewrite prompts, so this does not mask; it audits (entity
types and counts, never values) and, with `raise_on_prompt_pii=True`, aborts
a call that would leak.

## PII safety

No original value is written to logs, `repr`, callback state, or a saved
mapping's structure beyond what you explicitly persist with
`save_deanonymizer_mapping` (which, like Presidio's, contains the real
values -- treat that file as sensitive).

See `docs/langchain.md` in the MaskFlow repo for design notes.
