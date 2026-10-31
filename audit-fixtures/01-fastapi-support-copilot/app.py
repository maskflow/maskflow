"""A support copilot that summarises tickets with an LLM.

The shape this fixture exists to represent: personal data is pulled out of
a database by a handler and handed straight to a provider. Nobody wrote
anything careless -- there is simply no masking step anywhere in the path.
"""

from __future__ import annotations

import os

import psycopg
from fastapi import FastAPI
from openai import OpenAI

app = FastAPI()
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

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
