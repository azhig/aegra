import asyncio

from langgraph_sdk import get_client


async def main():
    # Connect to your self-hosted Aegra instance
    client = get_client(url="http://localhost:8000")

    # Create assistant (same API as LangGraph Platform)
    assistant = await client.assistants.create(
        graph_id="agent",
        if_exists="do_nothing",
        config={},
    )
    assistant_id = assistant["assistant_id"]

    # Create thread
    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    # Stream responses (identical to LangGraph Platform)
    stream = client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={
            "messages": [
                {"type": "human", "content": [{"type": "text", "text": "hello"}]}
            ]
        },
        stream_mode=["values", "messages-tuple", "custom"],
        on_disconnect="cancel",
    )

    async for chunk in stream:
        print(
            f"event: {getattr(chunk, 'event', None)}, data: {getattr(chunk, 'data', None)}"
        )


asyncio.run(main())
