"""Fixture 01, corrected: the same copilot with mask()/unmask() around it.

The audit must classify this clean, and must do so without being told --
the only difference from 01 is the two MaskFlow calls. A tool that cannot
tell 01 from 04 is useless, because every real repository is a mixture of
the two.
"""

from __future__ import annotations

import os

import psycopg
from fastapi import FastAPI
from maskflow import mask, unmask
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

    masked_prompt, mapping = mask(prompt)

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": masked_prompt}],
    )

    # The agent reading this needs the real name back, so the round trip
    # matters as much as the masking.
    return {"summary": unmask(completion.choices[0].message.content or "", mapping)}
