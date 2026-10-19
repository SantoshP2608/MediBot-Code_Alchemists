import hmac
import os

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response

app = FastAPI()

PROXY_TOKEN = os.environ.get("OLLAMA_PROXY_TOKEN", "")
if not PROXY_TOKEN:
    raise RuntimeError(
        "OLLAMA_PROXY_TOKEN is missing. Set it in PowerShell before starting the proxy."
    )
OLLAMA_URL = "http://127.0.0.1:11434"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(
    request: Request,
    authorization: str | None = Header(default=None),
):
    expected = f"Bearer {PROXY_TOKEN}"

    if not authorization or not hmac.compare_digest(
        authorization, expected
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")

    body = await request.body()

    async with httpx.AsyncClient(timeout=300.0) as client:
        upstream = await client.post(
            f"{OLLAMA_URL}/api/chat",
            content=body,
            headers={"Content-Type": "application/json"},
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get(
            "content-type", "application/json"
        ),
    )