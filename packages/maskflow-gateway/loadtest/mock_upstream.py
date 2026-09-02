"""A zero-latency stand-in for the LLM provider, so a load test measures
the *gateway's* mask/unmask cost and nothing else.

    uvicorn loadtest.mock_upstream:app --port 9001

Then point the gateway at it:
    MASKFLOW_GATEWAY_OPENAI_BASE_URL=http://127.0.0.1:9001/v1
"""

from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()

_REPLY = "Here is a summary. Contact details noted: {echo}"


@app.post("/v1/chat/completions", response_model=None)
async def chat(request: Request) -> JSONResponse | StreamingResponse:
    body = await request.json()
    echo = body["messages"][-1]["content"]
    if isinstance(echo, list):
        echo = " ".join(p.get("text", "") for p in echo if isinstance(p, dict))

    if body.get("stream"):

        async def gen():
            text = _REPLY.format(echo=echo)
            for i in range(0, len(text), 8):
                delta = {"content": text[i : i + 8]}
                chunk = {
                    "id": "mock",
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk)}\n\n".encode()
            done = {"id": "mock", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            yield f"data: {json.dumps(done)}\n\n".encode()
            yield b"data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    return JSONResponse(
        {
            "id": "mock",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": _REPLY.format(echo=echo)},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 20, "total_tokens": 40},
        }
    )


@app.post("/v1/embeddings")
async def embeddings(request: Request) -> JSONResponse:
    body = await request.json()
    n = len(body["input"]) if isinstance(body.get("input"), list) else 1
    return JSONResponse({"object": "list", "data": [{"embedding": [0.0] * 8} for _ in range(n)]})
