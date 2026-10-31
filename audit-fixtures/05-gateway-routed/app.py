"""Fixture 01, corrected the other way: no code change but a base_url.

The gateway is a drop-in OpenAI-compatible proxy, so adoption is one line
and the application keeps its original shape. The audit has to recognise
that line.

Note what makes this recognisable. MaskFlow's gateway has no reserved
hostname -- it is deliberately path-compatible with OpenAI's API -- so a
bare `base_url="http://localhost:8000/v1"` is indistinguishable from any
other local proxy by reading source alone, and the audit reports that case
`unknown` rather than assuming a guard. Here the host is the Compose/Helm
service name and the session header is set, which is corroboration.
"""

from __future__ import annotations

import os

import psycopg
from fastapi import FastAPI
from openai import OpenAI

app = FastAPI()

# The only difference from fixture 01.
client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url="http://maskflow-gateway:8000/v1",
    default_headers={"X-Maskflow-Session": os.environ.get("SESSION_ID", "support")},
)

DSN = os.environ.get("TICKETS_DSN", "postgresql:///support")


@app.get("/tickets/{ticket_id}/summary")
def summarize_ticket(ticket_id: int) -> dict[str, str]:
    with psycopg.connect(DSN) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT customer_name, aadhaar, pan, mobile, body FROM tickets WHERE id = %s",
            (ticket_id,),
        )
        row = cursor.fetchone()

    prompt = (
        f"Summarise this support ticket for an agent.\n"
        f"Customer: {row['customer_name']} (Aadhaar {row['aadhaar']}, PAN {row['pan']}, "
        f"mobile {row['mobile']})\n"
        f"Ticket: {row['body']}"
    )

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return {"summary": completion.choices[0].message.content or ""}
