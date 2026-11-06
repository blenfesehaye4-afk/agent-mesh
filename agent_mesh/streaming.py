"""Streaming Server-Sent Events (SSE) generator for chunked LLM responses."""

import asyncio
import json
import uuid
from typing import AsyncGenerator


async def stream_chat_completion(
    model: str,
    content: str,
    chunk_size: int = 4,
    delay: float = 0.01,
) -> AsyncGenerator[str, None]:
    """Simulate or proxy streaming tokens as standard OpenAI SSE chunks."""
    req_id = f"chatcmpl-stream-{uuid.uuid4().hex[:8]}"
    words = content.split(" ")

    for i in range(0, len(words), chunk_size):
        chunk_text = " ".join(words[i:i + chunk_size])
        if i > 0:
            chunk_text = " " + chunk_text

        chunk = {
            "id": req_id,
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": chunk_text},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(delay)

    # Final termination chunk
    final_chunk = {
        "id": req_id,
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"
