"""Load profile for the gateway. Each task sends a prompt containing a mix
of Indian + generic PII, so the detection path is actually exercised.

    # terminal 1 -- zero-latency upstream
    uvicorn loadtest.mock_upstream:app --port 9001

    # terminal 2 -- the gateway under test (pattern-only)
    MASKFLOW_GATEWAY_OPENAI_BASE_URL=http://127.0.0.1:9001/v1 \
    MASKFLOW_GATEWAY_NER=0 maskflow-gateway --port 8000

    # terminal 3
    locust -f loadtest/locustfile.py --host http://127.0.0.1:8000 \
      --headless -u 100 -r 20 -t 60s

Re-run terminal 2 with MASKFLOW_GATEWAY_NER=1 for the NER-enabled number.
"""

from __future__ import annotations

import random

from locust import HttpUser, between, task

_PROMPTS = [
    "Please summarise this. My name is Rahul Sharma, Aadhaar 2341 2345 6789, "
    "PAN ABCPE1234F, email rahul.sharma@example.com, phone +91 98765 43210.",
    "Draft a reply to Priya Nair (priya.nair@example.in). Her UPI is priya@okhdfc "
    "and her account IFSC is HDFC0001234.",
    "Note for the file: customer at 12 MG Road, Bengaluru 560001 called about "
    "GSTIN 29ABCDE1234F1Z5.",
    "No PII in this one, just asking for a haiku about the monsoon.",
]

_HEADERS = {"authorization": "Bearer sk-loadtest", "content-type": "application/json"}


class ChatUser(HttpUser):
    wait_time = between(0.0, 0.1)

    @task(5)
    def chat_non_streaming(self) -> None:
        self.client.post(
            "/v1/chat/completions",
            headers=_HEADERS,
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": random.choice(_PROMPTS)}],
            },
            name="/v1/chat/completions",
        )

    @task(3)
    def chat_streaming(self) -> None:
        with self.client.post(
            "/v1/chat/completions",
            headers=_HEADERS,
            json={
                "model": "gpt-4o-mini",
                "stream": True,
                "messages": [{"role": "user", "content": random.choice(_PROMPTS)}],
            },
            name="/v1/chat/completions [stream]",
            stream=True,
            catch_response=True,
        ) as resp:
            for _ in resp.iter_lines():
                pass
            resp.success()

    @task(2)
    def embeddings(self) -> None:
        self.client.post(
            "/v1/embeddings",
            headers=_HEADERS,
            json={"model": "text-embedding-3-small", "input": random.choice(_PROMPTS)},
            name="/v1/embeddings",
        )

    @task(1)
    def session_multi_turn(self) -> None:
        sid = f"load-{random.randint(0, 999)}"
        h = {**_HEADERS, "x-maskflow-session": sid}
        self.client.post(
            "/v1/mask", headers=h, json={"text": random.choice(_PROMPTS)}, name="/v1/mask [session]"
        )
        self.client.post(
            "/v1/unmask",
            headers=h,
            json={"text": "ok <EMAIL_1>"},
            name="/v1/unmask [session]",
        )
