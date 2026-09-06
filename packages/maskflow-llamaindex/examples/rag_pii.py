"""Runnable example: a LlamaIndex RAG query with MaskFlow masking.

    pip install maskflow-llamaindex "llama-index"
    export OPENAI_API_KEY=sk-...
    python packages/maskflow-llamaindex/examples/rag_pii.py

Shows the reversible query-time flow: the index holds the real text, the
node postprocessor masks retrieved context before the synthesizer LLM, and
MaskflowQueryEngine restores the originals in the answer. With no API key it
uses a mock LLM that echoes the (masked) context.
"""

from __future__ import annotations

import os

from llama_index.core import Document, VectorStoreIndex
from llama_index.core.settings import Settings
from maskflow_llamaindex import (
    MaskflowNodePostprocessor,
    MaskflowQueryEngine,
    unmask_response,
)

DOCS = [
    Document(text="Ramesh Kumar (PAN ABCPE1234F) filed his return on 2024-07-15."),
    Document(text="For queries, Ramesh Kumar is at ramesh@example.com or +91 98765 43210."),
]


def _configure() -> None:
    if os.getenv("OPENAI_API_KEY"):
        from llama_index.embeddings.openai import OpenAIEmbedding
        from llama_index.llms.openai import OpenAI

        Settings.embed_model = OpenAIEmbedding()
        Settings.llm = OpenAI(model="gpt-4o-mini")
    else:
        from llama_index.core.embeddings import MockEmbedding
        from llama_index.core.llms import MockLLM

        Settings.embed_model = MockEmbedding(embed_dim=256)
        Settings.llm = MockLLM()


_configure()

index = VectorStoreIndex.from_documents(DOCS)
pp = MaskflowNodePostprocessor()
inner = index.as_query_engine(node_postprocessors=[pp])

raw = inner.query("What is Ramesh Kumar's PAN and email?")
# what the synthesizer LLM actually saw (context masked by the postprocessor):
print("LLM context    :", raw.source_nodes[0].node.get_content()[:70], "...")
# the raw answer still carries placeholders; restore them from the node maps:
print("restored answer:", unmask_response(str(raw), raw.source_nodes)[:120])

# MaskflowQueryEngine does that unmask step for you (streaming too):
engine = MaskflowQueryEngine(inner)
print("via wrapper    :", str(engine.query("Ramesh Kumar's email?"))[:120])
