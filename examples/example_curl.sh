#!/bin/bash
# Example: Create run and stream events using curl
# Usage: ./example_curl.sh

set -e  # Exit on error

AEGRA_URL="${AEGRA_URL:-http://localhost:8000}"
THREAD_ID="example-thread-$(date +%s)"
ASSISTANT_ID="agent"
USER_MESSAGE="What is the weather in San Francisco?"

echo "========================================"
echo "🚀 Aegra API Example - curl"
echo "========================================"
echo ""
echo "Configuration:"
echo "  URL: $AEGRA_URL"
echo "  Thread ID: $THREAD_ID"
echo "  Assistant: $ASSISTANT_ID"
echo ""

# Step 1: Create thread
echo "🧵 Step 1: Creating thread..."
echo ""

THREAD_RESPONSE=$(curl -s -X POST "$AEGRA_URL/threads" \
  -H "Content-Type: application/json" \
  -d "{\"thread_id\": \"$THREAD_ID\"}")

if command -v jq &> /dev/null; then
    ACTUAL_THREAD_ID=$(echo "$THREAD_RESPONSE" | jq -r '.thread_id')
else
    ACTUAL_THREAD_ID=$(echo "$THREAD_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['thread_id'])")
fi

echo "✅ Thread created: $ACTUAL_THREAD_ID"
echo ""

# Step 2: Create run
echo "📤 Step 2: Creating run..."
echo ""

RESPONSE=$(curl -s -X POST "$AEGRA_URL/threads/$ACTUAL_THREAD_ID/runs" \
  -H "Content-Type: application/json" \
  -d "{
    \"assistant_id\": \"$ASSISTANT_ID\",
    \"input\": {
      \"messages\": [
        {
          \"role\": \"user\",
          \"content\": \"$USER_MESSAGE\"
        }
      ]
    },
    \"stream_mode\": [\"values\", \"messages\"]
  }")

# Extract run_id using jq (or python if jq not available)
if command -v jq &> /dev/null; then
    RUN_ID=$(echo "$RESPONSE" | jq -r '.run_id')
    STATUS=$(echo "$RESPONSE" | jq -r '.status')
else
    # Fallback: use python
    RUN_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['run_id'])")
    STATUS=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])")
fi

echo "✅ Run created successfully!"
echo "   Run ID: $RUN_ID"
echo "   Status: $STATUS"
echo ""

# Step 2: Stream events
echo "🔌 Step 2: Connecting to stream..."
echo "   URL: $AEGRA_URL/threads/$THREAD_ID/runs/$RUN_ID/stream"
echo ""
echo "📡 Streaming events (press Ctrl+C to stop):"
echo "--------------------------------------------------------------------------------"

# Stream with curl (no buffering)
curl -N -s "$AEGRA_URL/threads/$THREAD_ID/runs/$RUN_ID/stream"

echo ""
echo "--------------------------------------------------------------------------------"
echo "⏹️  Stream ended"
echo ""

# Step 3: Get final status
echo "📊 Step 3: Fetching final status..."
echo ""

FINAL_STATUS=$(curl -s "$AEGRA_URL/threads/$THREAD_ID/runs/$RUN_ID")

if command -v jq &> /dev/null; then
    echo "$FINAL_STATUS" | jq '.'
else
    echo "$FINAL_STATUS" | python3 -m json.tool
fi

echo ""
echo "✅ Done!"
