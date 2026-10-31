"""KYC document ingestion into a vector store.

Two sinks, one pipeline: the embedding call ships the document text to a
provider, and the Chroma write persists that same text as the document
payload. Teams often guard the chat path and forget the ingestion path
entirely, which is why this fixture has no chat call at all.
"""

from __future__ import annotations

import os
import pathlib

import chromadb
from openai import OpenAI
from pypdf import PdfReader

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
chroma = chromadb.PersistentClient(path="./kyc-index")
collection = chroma.get_or_create_collection("kyc")

KYC_DIR = pathlib.Path(os.environ.get("KYC_DIR", "./kyc-docs"))


def extract(pdf_path: pathlib.Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def ingest_one(pdf_path: pathlib.Path) -> None:
    document_text = extract(pdf_path)

    embedding = client.embeddings.create(
        model="text-embedding-3-small",
        input=document_text,
    )

    collection.add(
        ids=[pdf_path.stem],
        embeddings=[embedding.data[0].embedding],
        documents=[document_text],
        metadatas=[{"source": pdf_path.name}],
    )


def ingest_all() -> None:
    for pdf_path in sorted(KYC_DIR.glob("*.pdf")):
        ingest_one(pdf_path)
