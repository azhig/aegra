"""Task queue system for distributed graph execution using Redis"""

import json
from typing import Any

import structlog
from redis.asyncio import Redis

logger = structlog.getLogger(__name__)


class TaskQueue:
    """Redis-based task queue for distributing graph execution across workers"""

    def __init__(self, redis_client: Redis, queue_name: str = "aegra:tasks"):
        self.redis_client = redis_client
        self.queue_name = queue_name
        self.heartbeat_prefix = "aegra:heartbeat:"
        self.cancel_prefix = "aegra:cancel:"

    async def enqueue(
        self,
        run_id: str,
        thread_id: str,
        graph_id: str,
        input_data: dict[str, Any],
        user_identity: str,
        config: dict[str, Any],
        context: dict[str, Any] | None = None,
        stream_mode: list[str] | None = None,
        checkpoint: str | None = None,
        command: dict[str, Any] | None = None,
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
        multitask_strategy: str | None = None,
        stream_subgraphs: bool = False,
    ) -> None:
        """Enqueue a task for worker execution.

        Args:
            run_id: Unique run identifier
            thread_id: Thread identifier
            graph_id: Graph/assistant identifier
            input_data: Input data for the graph
            user_identity: User who initiated the run
            config: Configuration dict
            context: Optional context dict
            stream_mode: Stream modes
            checkpoint: Optional checkpoint ID
            command: Optional command dict
            interrupt_before: Optional list of nodes to interrupt before
            interrupt_after: Optional list of nodes to interrupt after
            multitask_strategy: Optional multitasking strategy
            stream_subgraphs: Whether to stream subgraphs
        """
        task = {
            "run_id": run_id,
            "thread_id": thread_id,
            "graph_id": graph_id,
            "input": input_data,
            "user_identity": user_identity,
            "config": config,
            "context": context,
            "stream_mode": stream_mode,
            "checkpoint": checkpoint,
            "command": command,
            "interrupt_before": interrupt_before,
            "interrupt_after": interrupt_after,
            "multitask_strategy": multitask_strategy,
            "stream_subgraphs": stream_subgraphs,
        }

        try:
            # Push task to Redis list (FIFO queue via RPUSH/BLPOP)
            task_json = json.dumps(task, default=str)
            await self.redis_client.lpush(self.queue_name, task_json)
            logger.info(
                f"✅ Task enqueued for run {run_id}",
                run_id=run_id,
                queue=self.queue_name,
            )
        except Exception as e:
            logger.error(
                f"❌ Failed to enqueue task for run {run_id}: {e}",
                run_id=run_id,
                exc_info=e,
            )
            raise

    async def dequeue(self, timeout: int = 30) -> dict[str, Any] | None:
        """Dequeue a task from the queue (blocking operation).

        Args:
            timeout: Blocking timeout in seconds

        Returns:
            Task dict or None if timeout
        """
        try:
            # BRPOP - blocking right pop (FIFO with LPUSH)
            result = await self.redis_client.brpop(self.queue_name, timeout=timeout)

            if result is None:
                return None

            _queue_name, task_json = result
            task = json.loads(task_json)
            logger.debug(
                "📥 Task dequeued",
                run_id=task.get("run_id"),
                queue=self.queue_name,
            )
            return task

        except Exception as e:
            logger.error(f"Error dequeuing task: {e}", exc_info=e)
            return None

    async def set_heartbeat(self, run_id: str, worker_id: str, ttl: int = 60) -> None:
        """Set heartbeat timestamp for a running task.

        Args:
            run_id: Run identifier
            worker_id: Worker identifier
            ttl: Time-to-live in seconds
        """
        try:
            key = f"{self.heartbeat_prefix}{run_id}"
            value = json.dumps({"worker_id": worker_id, "run_id": run_id})
            await self.redis_client.setex(key, ttl, value)
        except Exception as e:
            logger.warning(f"Failed to set heartbeat for run {run_id}: {e}")

    async def get_heartbeat(self, run_id: str) -> dict[str, str] | None:
        """Get heartbeat info for a run.

        Args:
            run_id: Run identifier

        Returns:
            Heartbeat dict or None if expired
        """
        try:
            key = f"{self.heartbeat_prefix}{run_id}"
            value = await self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(f"Failed to get heartbeat for run {run_id}: {e}")
            return None

    async def publish_cancel(self, run_id: str) -> None:
        """Publish cancellation signal for a run.

        Args:
            run_id: Run identifier to cancel
        """
        try:
            channel = f"{self.cancel_prefix}{run_id}"
            await self.redis_client.publish(channel, "cancel")
            logger.info(f"🛑 Published cancel signal for run {run_id}")
        except Exception as e:
            logger.error(f"Failed to publish cancel signal for run {run_id}: {e}")

    async def subscribe_cancel(self, run_id: str):
        """Subscribe to cancellation signals for a run.

        Args:
            run_id: Run identifier

        Returns:
            PubSub instance (must be closed by caller)
        """
        try:
            channel = f"{self.cancel_prefix}{run_id}"
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe(channel)
            return pubsub
        except Exception as e:
            logger.error(f"Failed to subscribe to cancel channel for run {run_id}: {e}")
            raise

    async def queue_size(self) -> int:
        """Get current queue size.

        Returns:
            Number of tasks in queue
        """
        try:
            return await self.redis_client.llen(self.queue_name)
        except Exception as e:
            logger.error(f"Failed to get queue size: {e}")
            return 0


# Global task queue instance (initialized with Redis client)
_task_queue: TaskQueue | None = None


async def get_task_queue() -> TaskQueue:
    """Get or create global task queue instance.

    Returns:
        TaskQueue instance
    """
    global _task_queue

    if _task_queue is None:
        from ..core.database import db_manager

        redis_client = await db_manager.get_redis_client()
        _task_queue = TaskQueue(redis_client)
        logger.info("✅ Task queue initialized")

    return _task_queue
