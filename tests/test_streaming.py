import pytest
from agent_mesh.streaming import stream_chat_completion


@pytest.mark.asyncio
async def test_streaming_sse_chunks():
    chunks = []
    async for chunk in stream_chat_completion(model="gpt-4o", content="Antigravity agentic systems", chunk_size=2, delay=0.001):
        chunks.append(chunk)

    assert len(chunks) >= 3
    assert any("Antigravity" in c for c in chunks)
    assert chunks[-1] == "data: [DONE]\n\n"
