"""The tricky one: PII split across JSON fields, sent two calls deep.

Two things here are hard on purpose.

First, no single field looks like personal data. The Aadhaar arrives in
four chunks across a JSON body and is only reassembled on the way into the
prompt, so a scanner looking at the request payload sees nothing to flag.

Second, the provider call is two function calls away from the handler that
holds the data: `handle` -> `build_report` -> `ask_model`. This release
traces within one function only, so it is expected to find the flow and
classify it unmasked while reporting its *source* as untraced. That is the
honest result, and expected.json records it as such rather than pretending
otherwise -- inter-procedural tracing is M2 work.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from openai import OpenAI

app = FastAPI()
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def ask_model(text: str) -> str:
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": text}],
    )
    return completion.choices[0].message.content or ""


def build_report(payload: dict[str, str]) -> str:
    # Reassembled from four fields that are individually unremarkable.
    uid = "".join(
        (
            payload["uid_part_1"],
            payload["uid_part_2"],
            payload["uid_part_3"],
            payload["uid_part_4"],
        )
    )
    return ask_model(f"Applicant {payload['given_name']} {payload['surname']}, UID {uid}")


@app.post("/applications")
async def handle(request: Request) -> dict[str, str]:
    body = await request.json()
    return {"report": build_report(body)}
