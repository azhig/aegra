"""Worker CLI command for running task execution workers"""

import asyncio
import sys
from pathlib import Path

# Add project root to path for imports
current_dir = Path(__file__).parent.parent.parent.parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Add graphs directory to path
graphs_dir = current_dir / "graphs"
if str(graphs_dir) not in sys.path:
    sys.path.insert(0, str(graphs_dir))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Now import worker executor
from src.agent_server.worker.executor import main

if __name__ == "__main__":
    """
    Run Aegra worker for distributed task execution.

    Usage:
        python -m src.agent_server.cli.worker

    Environment Variables:
        REDIS_URL: Redis connection URL (default: redis://localhost:6379)
        DATABASE_URL: PostgreSQL connection URL
        WORKER_ID: Unique worker identifier (auto-generated if not set)
        WORKER_HEARTBEAT_INTERVAL: Seconds between heartbeat updates (default: 30)
        WORKER_HEARTBEAT_TTL: TTL for heartbeat keys in Redis (default: 60)
        OPENAI_API_KEY: OpenAI API key (required for graphs using OpenAI)

    Example:
        # Start a single worker
        python -m src.agent_server.cli.worker

        # Start with custom worker ID
        WORKER_ID=worker-1 python -m src.agent_server.cli.worker

        # Run multiple workers (in different terminals/processes)
        WORKER_ID=worker-1 python -m src.agent_server.cli.worker &
        WORKER_ID=worker-2 python -m src.agent_server.cli.worker &
        WORKER_ID=worker-3 python -m src.agent_server.cli.worker &
    """
    asyncio.run(main())
