"""A LangChain chain whose model call is masked and whose tracer is not.

This is the leak nobody looks for. The prompt handed to the model goes
through `mask()`, so a reviewer reading the model call concludes the path
is safe -- while the Langfuse callback ships the unmasked input and output
to a second vendor on every single invocation.
"""

from __future__ import annotations

import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langfuse import Langfuse
from maskflow import mask

langfuse = Langfuse(
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    host="https://cloud.langfuse.com",
)

llm = ChatOpenAI(model="gpt-4o-mini")
prompt_template = ChatPromptTemplate.from_template("Draft a reply to this grievance:\n{grievance}")


def draft_reply(grievance_text: str, applicant_name: str) -> str:
    masked_grievance, mapping = mask(grievance_text)

    rendered = prompt_template.format(grievance=masked_grievance)
    answer = llm.invoke(rendered)

    # The tracer receives the ORIGINAL text, not the masked one.
    langfuse.generation(
        name="draft_reply",
        input=grievance_text,
        output=answer.content,
        metadata={"applicant_name": applicant_name},
    )
    return str(answer.content)
