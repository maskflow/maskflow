"""Runnable example: a LangChain LCEL chain with MaskFlow anonymization.

    pip install maskflow-langchain "langchain[openai]"
    export OPENAI_API_KEY=sk-...
    python packages/maskflow-langchain/examples/anonymized_chain.py

Swap the model line for any chat model. With no API key it falls back to a
fake model that echoes the (masked) prompt, so the round-trip is still
visible.
"""

from __future__ import annotations

import os

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from maskflow_langchain import MaskflowLeakGuardCallback, MaskflowReversibleAnonymizer


def _model():  # noqa: ANN202
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model="gpt-4o-mini", temperature=0)
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    return FakeMessagesListChatModel(
        responses=[AIMessage("Noted. I will reference the details you provided.")]
    )


anonymizer = MaskflowReversibleAnonymizer()
prompt = ChatPromptTemplate.from_template(
    "A user wrote: {question}\nAcknowledge and restate the identifiers you saw."
)

chain = (
    {"question": lambda x: anonymizer.anonymize(x["question"])}
    | prompt
    | _model()
    | StrOutputParser()
    | anonymizer.deanonymizer
)

question = "Please file the return for PAN ABCPE1234F, UPI ramesh@oksbi, email ramesh@example.com."

guard = MaskflowLeakGuardCallback()
print("you asked   :", question)
print("model saw   :", anonymizer.anonymize(question))
print("you get back:", chain.invoke({"question": question}, config={"callbacks": [guard]}))
print("streamed    :", end=" ")
for piece in chain.stream({"question": question}):
    print(piece, end="", flush=True)
print()
print("audit       :", guard.summary())
