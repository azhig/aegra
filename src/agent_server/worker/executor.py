"""Worker executor for processing tasks from Redis queue"""

import asyncio
import os
import signal
import uuid
from typing import Any

import structlog

from ..core.database import db_manager
from ..services.langgraph_service import get_langgraph_service
from ..services.task_queue import get_task_queue

logger = structlog.getLogger(__name__)


class WorkerExecutor:
    """Executor that processes graph execution tasks from Redis queue"""

    def __init__(
        self,
        worker_id: str | None = None,
        heartbeat_interval: int = 30,
        heartbeat_ttl: int = 60,
    ):
        """Initialize worker executor.

        Args:
            worker_id: Unique worker identifier (auto-generated if not provided)
            heartbeat_interval: Seconds between heartbeat updates
            heartbeat_ttl: TTL for heartbeat keys in Redis
        """
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_ttl = heartbeat_ttl
        self.shutdown_event = asyncio.Event()
        self.current_task: dict[str, Any] | None = None

    async def initialize(self) -> None:
        """Initialize worker dependencies"""
        # Initialize database and LangGraph service
        await db_manager.initialize()
        langgraph_service = get_langgraph_service()
        await langgraph_service.initialize()
        logger.info(f"✅ Worker {self.worker_id} initialized")

    async def shutdown(self) -> None:
        """Graceful shutdown"""
        self.shutdown_event.set()
        logger.info(f"🛑 Worker {self.worker_id} shutting down")

        # Cancel current task if any
        if self.current_task:
            run_id = self.current_task.get("run_id")
            logger.warning(
                f"⚠️ Cancelling current task {run_id} during shutdown",
                run_id=run_id,
            )

        await db_manager.close()

    async def run(self) -> None:
        """Main worker loop - dequeue and execute tasks"""
        task_queue = await get_task_queue()
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info(
            f"🚀 Worker {self.worker_id} started, waiting for tasks...",
            worker_id=self.worker_id,
        )

        try:
            while not self.shutdown_event.is_set():
                try:
                    # Dequeue task (blocking with timeout)
                    task = await task_queue.dequeue(timeout=5)

                    if task is None:
                        # Timeout - check for shutdown and continue
                        continue

                    self.current_task = task
                    run_id = task["run_id"]

                    logger.info(
                        "📦 Processing task",
                        run_id=run_id,
                        worker_id=self.worker_id,
                    )

                    # Set initial heartbeat
                    await task_queue.set_heartbeat(
                        run_id, self.worker_id, self.heartbeat_ttl
                    )

                    # Subscribe to cancel channel
                    cancel_pubsub = await task_queue.subscribe_cancel(run_id)
                    cancel_task = asyncio.create_task(
                        self._listen_for_cancel(cancel_pubsub, run_id)
                    )

                    # Execute the task
                    execute_task = asyncio.create_task(self._execute_task(task))

                    # Wait for either execution or cancellation
                    done, pending = await asyncio.wait(
                        [execute_task, cancel_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    # Cancel the other task
                    for t in pending:
                        t.cancel()
                        try:
                            await t
                        except asyncio.CancelledError:
                            pass

                    # Check if execution succeeded
                    if execute_task in done:
                        try:
                            await execute_task
                        except Exception as e:
                            logger.error(
                                "❌ Task execution failed",
                                run_id=run_id,
                                error=str(e),
                                exc_info=e,
                            )

                    # Clean up cancel subscription
                    await cancel_pubsub.unsubscribe()
                    await cancel_pubsub.aclose()

                    self.current_task = None

                except asyncio.CancelledError:
                    logger.info(f"Worker {self.worker_id} cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error in worker loop: {e}", exc_info=e)
                    await asyncio.sleep(1)  # Brief pause before retrying

        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            logger.info(f"✅ Worker {self.worker_id} stopped")

    async def _execute_task(self, task: dict[str, Any]) -> None:
        """Execute a single task"""
        run_id = task["run_id"]
        thread_id = task["thread_id"]
        graph_id = task["graph_id"]

        try:
            # Import here to avoid circular dependency
            from ..api.runs import execute_run_async
            from ..core.auth_middleware import User

            # Reconstruct User object
            user = User(
                identity=task["user_identity"],
                metadata={"worker_id": self.worker_id},
            )

            # Execute the run
            await execute_run_async(
                run_id=run_id,
                thread_id=thread_id,
                graph_id=graph_id,
                input_data=task["input"],
                user=user,
                config=task.get("config"),
                context=task.get("context"),
                stream_mode=task.get("stream_mode"),
                session=None,  # Worker creates its own session
                checkpoint=task.get("checkpoint"),
                command=task.get("command"),
                interrupt_before=task.get("interrupt_before"),
                interrupt_after=task.get("interrupt_after"),
                _multitask_strategy=task.get("multitask_strategy"),
                subgraphs=task.get("stream_subgraphs", False),
            )

            logger.info("✅ Task completed", run_id=run_id, worker_id=self.worker_id)

        except asyncio.CancelledError:
            logger.warning("⚠️ Task cancelled", run_id=run_id)
            raise
        except Exception as e:
            logger.error(
                "❌ Task execution error",
                run_id=run_id,
                error=str(e),
                exc_info=e,
            )
            raise

    async def _heartbeat_loop(self) -> None:
        """Background task to update heartbeat"""
        task_queue = await get_task_queue()

        while not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(self.heartbeat_interval)

                if self.current_task:
                    run_id = self.current_task["run_id"]
                    await task_queue.set_heartbeat(
                        run_id, self.worker_id, self.heartbeat_ttl
                    )
                    logger.debug(
                        "💓 Heartbeat updated", run_id=run_id, worker_id=self.worker_id
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error updating heartbeat: {e}")

    async def _listen_for_cancel(self, pubsub, run_id: str) -> None:
        """Listen for cancellation signals"""
        try:
            async for message in pubsub.listen():
                if message["type"] == "message" and message["data"] == "cancel":
                    logger.warning(
                        "🛑 Received cancel signal",
                        run_id=run_id,
                        worker_id=self.worker_id,
                    )
                    raise asyncio.CancelledError()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error listening for cancel: {e}")


async def main():
    """Main entry point for worker process"""
    from ..utils.setup_logging import setup_logging

    setup_logging()

    # Get configuration from environment
    worker_id = os.getenv("WORKER_ID")
    heartbeat_interval = int(os.getenv("WORKER_HEARTBEAT_INTERVAL", "30"))
    heartbeat_ttl = int(os.getenv("WORKER_HEARTBEAT_TTL", "60"))

    # Create executor
    executor = WorkerExecutor(
        worker_id=worker_id,
        heartbeat_interval=heartbeat_interval,
        heartbeat_ttl=heartbeat_ttl,
    )

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler(sig):
        logger.info(f"Received signal {sig}, initiating shutdown...")
        asyncio.create_task(executor.shutdown())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    # Initialize and run
    try:
        await executor.initialize()
        await executor.run()
    except Exception as e:
        logger.error(f"Worker error: {e}", exc_info=e)
        raise
    finally:
        await executor.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
