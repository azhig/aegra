"""
Example script for testing Aegra API using direct HTTP requests:
1. Create a thread via POST /threads
2. Create a run via POST /threads/{thread_id}/runs
3. Get the run_id from response
4. Connect to streaming via GET /threads/{thread_id}/runs/{run_id}/stream

This example uses httpx (pure HTTP) instead of langgraph-sdk.

Usage:
    python example_http.py

Environment Variables:
    AEGRA_URL: Base URL for Aegra API (default: http://localhost:8000)
    OPENAI_API_KEY: Required for agent execution
"""

import asyncio
import os
import sys

import httpx


async def create_thread(base_url: str, thread_id: str | None = None) -> dict:
    """Create a new thread via POST /threads

    Args:
        base_url: Base URL of Aegra API
        thread_id: Optional thread identifier (auto-generated if not provided)

    Returns:
        Thread object with thread_id
    """
    url = f"{base_url}/threads"

    payload = {}
    if thread_id:
        payload["thread_id"] = thread_id

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=10.0)
        response.raise_for_status()
        thread = response.json()

    return thread


async def create_run(
    base_url: str,
    thread_id: str,
    assistant_id: str,
    user_message: str,
) -> dict:
    """Create a new run via POST /threads/{thread_id}/runs

    Args:
        base_url: Base URL of Aegra API
        thread_id: Thread identifier (can be any string)
        assistant_id: Assistant/graph ID (e.g., "agent")
        user_message: User's message to send to the agent

    Returns:
        Run object with run_id and status
    """
    url = f"{base_url}/threads/{thread_id}/runs"

    payload = {
        "assistant_id": assistant_id,
        "input": {"messages": [{"role": "user", "content": user_message}]},
        "stream_mode": ["values", "messages"],  # Request both values and messages
    }

    print("📤 Creating run...")
    print(f"   URL: {url}")
    print(f"   Thread ID: {thread_id}")
    print(f"   Assistant: {assistant_id}")
    print(f"   Message: {user_message}")
    print()

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=10.0)
        response.raise_for_status()
        run = response.json()

    print("✅ Run created successfully!")
    print(f"   Run ID: {run['run_id']}")
    print(f"   Status: {run['status']}")
    print()
    await asyncio.sleep(10)
    return run


async def stream_run(
    base_url: str,
    thread_id: str,
    run_id: str,
) -> None:
    """Connect to run streaming via GET /threads/{thread_id}/runs/{run_id}/stream

    Args:
        base_url: Base URL of Aegra API
        thread_id: Thread identifier
        run_id: Run identifier from create_run()

    Streams events via Server-Sent Events (SSE) and prints them to console.
    """
    url = f"{base_url}/threads/{thread_id}/runs/{run_id}/stream"

    print("🔌 Connecting to stream...")
    print(f"   URL: {url}")
    print(f"   Run ID: {run_id}")
    print()
    print("📡 Streaming events (press Ctrl+C to stop):")
    print("-" * 80)

    async with (
        httpx.AsyncClient() as client,
        client.stream("GET", url, timeout=None) as response,
    ):
        response.raise_for_status()

        async for line in response.aiter_lines():
            # SSE format: "event: <type>\n" or "data: <json>\n"
            if line.startswith("event:"):
                event_type = line.split(":", 1)[1].strip()
                print(f"\n🔖 Event: {event_type}")

            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()

                # Pretty print JSON data
                try:
                    import json

                    parsed = json.loads(data)
                    formatted = json.dumps(parsed, indent=2)
                    print(f"📦 Data:\n{formatted}")
                except json.JSONDecodeError:
                    print(f"📦 Data: {data}")

            elif line.startswith("id:"):
                event_id = line.split(":", 1)[1].strip()
                print(f"🆔 ID: {event_id}")

            elif line == "":
                # Empty line separates events
                print("-" * 80)


async def get_run_status(
    base_url: str,
    thread_id: str,
    run_id: str,
) -> dict:
    """Get current run status via GET /threads/{thread_id}/runs/{run_id}

    Args:
        base_url: Base URL of Aegra API
        thread_id: Thread identifier
        run_id: Run identifier

    Returns:
        Run object with current status
    """
    url = f"{base_url}/threads/{thread_id}/runs/{run_id}"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        run = response.json()

    return run


async def main():
    """Main execution flow"""
    # Configuration
    base_url = os.getenv("AEGRA_URL", "http://localhost:8000")
    thread_id = "example-thread-123"
    assistant_id = "agent"  # Default assistant from aegra.json
    user_message = "What is the weather in San Francisco?"

    # Check if OPENAI_API_KEY is set
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not set. The agent may fail to execute.")
        print("   Set it via: export OPENAI_API_KEY=sk-...")
        print()

    try:
        # Step 1: Create thread
        print("🧵 Step 1: Creating thread...")
        thread = await create_thread(base_url=base_url, thread_id=thread_id)
        print(f"✅ Thread created: {thread['thread_id']}")
        print()

        # Step 2: Create run
        run = await create_run(
            base_url=base_url,
            thread_id=thread["thread_id"],
            assistant_id=assistant_id,
            user_message=user_message,
        )

        run_id = run["run_id"]

        # Step 3: Stream events
        print("💡 Tip: The run is executing in the background (async)")
        print("         Events will appear as they are generated by the agent/workers.")
        print()

        await stream_run(
            base_url=base_url,
            thread_id=thread["thread_id"],
            run_id=run_id,
        )

    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP Error: {e.response.status_code}")
        print(f"   Response: {e.response.text}")
        sys.exit(1)

    except httpx.RequestError as e:
        print(f"❌ Request Error: {e}")
        print(f"   Is Aegra running at {base_url}?")
        print("   Try: docker compose up aegra")
        sys.exit(1)

    except KeyboardInterrupt:
        print()
        print("⏹️  Streaming stopped by user")
        print()

        # Step 4: Check final status
        try:
            final_run = await get_run_status(
                base_url=base_url, thread_id=thread["thread_id"], run_id=run_id
            )
            print("📊 Final Run Status:")
            print(f"   Status: {final_run['status']}")
            print(f"   Run ID: {final_run['run_id']}")

            if final_run.get("output"):
                print(f"   Output: {final_run['output']}")

            if final_run.get("error_message"):
                print(f"   Error: {final_run['error_message']}")

        except Exception as e:
            print(f"⚠️  Could not fetch final status: {e}")

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print("=" * 80)
    print("🚀 Aegra API Example - Create Run & Stream Events")
    print("=" * 80)
    print()

    asyncio.run(main())
