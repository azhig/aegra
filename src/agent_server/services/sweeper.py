"""Run sweeper for detecting and recovering failed/stale runs"""

import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update

from ..core.orm import Run as RunORM
from ..core.orm import _get_session_maker
from ..services.task_queue import get_task_queue

logger = structlog.getLogger(__name__)


class RunSweeper:
    """Detects and recovers runs that lost their worker (heartbeat timeout)"""

    def __init__(self, sweep_interval: int = 120, heartbeat_timeout: int = 120):
        """Initialize run sweeper.

        Args:
            sweep_interval: Seconds between sweep cycles
            heartbeat_timeout: Seconds before considering a run stale
        """
        self.sweep_interval = sweep_interval
        self.heartbeat_timeout = heartbeat_timeout
        self._task: asyncio.Task | None = None
        self._shutdown = asyncio.Event()

    async def start(self) -> None:
        """Start the sweeper background task"""
        if self._task is None or self._task.done():
            self._shutdown.clear()
            self._task = asyncio.create_task(self._sweep_loop())
            logger.info(
                "✅ Run sweeper started",
                sweep_interval=self.sweep_interval,
                heartbeat_timeout=self.heartbeat_timeout,
            )

    async def stop(self) -> None:
        """Stop the sweeper background task"""
        if self._task and not self._task.done():
            self._shutdown.set()
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("✅ Run sweeper stopped")

    async def _sweep_loop(self) -> None:
        """Main sweeper loop"""
        while not self._shutdown.is_set():
            try:
                await asyncio.sleep(self.sweep_interval)
                await self._sweep_stale_runs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in sweeper loop: {e}", exc_info=e)

    async def _sweep_stale_runs(self) -> None:
        """Check for stale runs and recover them"""
        try:
            task_queue = await get_task_queue()
            session_maker = _get_session_maker()

            async with session_maker() as session:
                # Find runs in 'running' or 'pending' status that might be stale
                stmt = select(RunORM).where(RunORM.status.in_(["running", "pending"]))
                result = await session.execute(stmt)
                runs = result.scalars().all()

                recovered_count = 0
                failed_count = 0

                for run in runs:
                    run_id = run.run_id

                    # Check heartbeat
                    heartbeat = await task_queue.get_heartbeat(run_id)

                    if heartbeat is None:
                        # No heartbeat found - could be:
                        # 1. Task not picked up yet (pending)
                        # 2. Worker crashed (running without heartbeat)

                        if run.status == "pending":
                            # Check if task has been waiting too long
                            time_since_created = (
                                datetime.now(UTC) - run.created_at
                            ).total_seconds()

                            if time_since_created > self.heartbeat_timeout:
                                logger.warning(
                                    "⚠️ Pending run timed out, marking as failed",
                                    run_id=run_id,
                                    age_seconds=time_since_created,
                                )
                                await self._mark_run_failed(
                                    session,
                                    run,
                                    "Task timeout - no worker picked up task",
                                )
                                failed_count += 1

                        elif run.status == "running":
                            # Running but no heartbeat - worker likely crashed
                            time_since_updated = (
                                datetime.now(UTC) - run.updated_at
                            ).total_seconds()

                            if time_since_updated > self.heartbeat_timeout:
                                logger.warning(
                                    "⚠️ Running task lost heartbeat, re-queuing",
                                    run_id=run_id,
                                    age_seconds=time_since_updated,
                                )

                                # Re-queue the task
                                await self._requeue_run(session, run)
                                recovered_count += 1

                if recovered_count > 0 or failed_count > 0:
                    logger.info(
                        "🔄 Sweep complete",
                        recovered=recovered_count,
                        failed=failed_count,
                    )

        except Exception as e:
            logger.error(f"Error sweeping stale runs: {e}", exc_info=e)

    async def _requeue_run(self, session, run: RunORM) -> None:
        """Re-queue a stale run"""
        try:
            task_queue = await get_task_queue()

            # Enqueue task again
            await task_queue.enqueue(
                run_id=run.run_id,
                thread_id=run.thread_id,
                graph_id=run.assistant_id,  # assistant_id is the graph_id
                input_data=run.input or {},
                user_identity=run.user_id,
                config=run.config or {},
                context=run.context,
            )

            # Update status back to pending
            stmt = (
                update(RunORM)
                .where(RunORM.run_id == run.run_id)
                .values(status="pending", updated_at=datetime.now(UTC))
            )
            await session.execute(stmt)
            await session.commit()

            logger.info("✅ Re-queued stale run", run_id=run.run_id)

        except Exception as e:
            logger.error(f"Failed to re-queue run {run.run_id}: {e}", exc_info=e)

    async def _mark_run_failed(self, session, run: RunORM, error_message: str) -> None:
        """Mark a run as failed"""
        try:
            stmt = (
                update(RunORM)
                .where(RunORM.run_id == run.run_id)
                .values(
                    status="failed",
                    error_message=error_message,
                    updated_at=datetime.now(UTC),
                    output={},  # Empty output for failed runs
                )
            )
            await session.execute(stmt)
            await session.commit()

            logger.info(
                "✅ Marked run as failed", run_id=run.run_id, reason=error_message
            )

        except Exception as e:
            logger.error(f"Failed to mark run {run.run_id} as failed: {e}", exc_info=e)


# Global sweeper instance
_sweeper: RunSweeper | None = None


async def get_sweeper() -> RunSweeper:
    """Get or create global sweeper instance"""
    global _sweeper

    if _sweeper is None:
        import os

        sweep_interval = int(os.getenv("SWEEPER_INTERVAL", "120"))
        heartbeat_timeout = int(os.getenv("WORKER_HEARTBEAT_TTL", "60")) * 2

        _sweeper = RunSweeper(
            sweep_interval=sweep_interval, heartbeat_timeout=heartbeat_timeout
        )

    return _sweeper


async def start_sweeper() -> None:
    """Start the global sweeper"""
    sweeper = await get_sweeper()
    await sweeper.start()


async def stop_sweeper() -> None:
    """Stop the global sweeper"""
    global _sweeper
    if _sweeper:
        await _sweeper.stop()
        _sweeper = None
