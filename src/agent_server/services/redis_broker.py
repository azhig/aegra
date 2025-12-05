"""Redis-based broker for distributed streaming via PubSub"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import structlog
from redis.asyncio import Redis

from .base_broker import BaseBrokerManager, BaseRunBroker

logger = structlog.getLogger(__name__)


class RedisRunBroker(BaseRunBroker):
    """Redis PubSub-based event broker for a specific run"""

    def __init__(self, run_id: str, redis_client: Redis):
        self.run_id = run_id
        self.redis_client = redis_client
        self.channel = f"run:{run_id}:events"
        self._finished = False
        self._created_at = asyncio.get_event_loop().time()

    async def put(self, event_id: str, payload: Any) -> None:
        """Publish event to Redis channel"""
        if self._finished:
            logger.warning(
                f"Attempted to put event {event_id} into finished broker for run {self.run_id}"
            )
            return

        try:
            event_data = {"event_id": event_id, "payload": payload}
            # Serialize payload - handle tuples and complex types
            serialized = json.dumps(event_data, default=str)
            await self.redis_client.publish(self.channel, serialized)

            # Check if this is an end event
            if isinstance(payload, tuple) and len(payload) >= 1 and payload[0] == "end":
                self.mark_finished()

        except Exception as e:
            logger.error(
                f"Failed to publish event to Redis channel {self.channel}: {e}",
                exc_info=e,
            )
            raise

    async def aiter(self) -> AsyncIterator[tuple[str, Any]]:
        """Subscribe to Redis channel and yield events"""
        pubsub = self.redis_client.pubsub()

        try:
            await pubsub.subscribe(self.channel)
            logger.debug(f"Subscribed to Redis channel {self.channel}")

            # Listen for messages
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        event_id = data["event_id"]
                        payload = data["payload"]

                        # Reconstruct tuple if needed
                        if isinstance(payload, list):
                            payload = tuple(payload)

                        yield event_id, payload

                        # Check if this is an end event
                        if (
                            isinstance(payload, tuple)
                            and len(payload) >= 1
                            and payload[0] == "end"
                        ):
                            break

                    except Exception as e:
                        logger.error(f"Error processing Redis message: {e}", exc_info=e)
                        continue

        except asyncio.CancelledError:
            logger.debug(f"Redis subscription cancelled for {self.channel}")
            raise
        finally:
            await pubsub.unsubscribe(self.channel)
            await pubsub.aclose()
            logger.debug(f"Unsubscribed from Redis channel {self.channel}")

    def mark_finished(self) -> None:
        """Mark this broker as finished"""
        self._finished = True
        logger.debug(f"Broker for run {self.run_id} marked as finished")

    def is_finished(self) -> bool:
        """Check if this broker is finished"""
        return self._finished

    def is_empty(self) -> bool:
        """Redis PubSub doesn't have queue - always return True"""
        return True

    def get_age(self) -> float:
        """Get the age of this broker in seconds"""
        return asyncio.get_event_loop().time() - self._created_at


class RedisBrokerManager(BaseBrokerManager):
    """Manages multiple RedisRunBroker instances"""

    def __init__(self, redis_client: Redis):
        self.redis_client = redis_client
        self._brokers: dict[str, RedisRunBroker] = {}
        self._cleanup_task: asyncio.Task | None = None

    def get_or_create_broker(self, run_id: str) -> RedisRunBroker:
        """Get or create a broker for a run"""
        if run_id not in self._brokers:
            self._brokers[run_id] = RedisRunBroker(run_id, self.redis_client)
            logger.debug(f"Created new Redis broker for run {run_id}")
        return self._brokers[run_id]

    def get_broker(self, run_id: str) -> RedisRunBroker | None:
        """Get an existing broker or None"""
        return self._brokers.get(run_id)

    def cleanup_broker(self, run_id: str) -> None:
        """Clean up a broker for a run"""
        if run_id in self._brokers:
            self._brokers[run_id].mark_finished()
            logger.debug(f"Marked Redis broker for run {run_id} for cleanup")

    def remove_broker(self, run_id: str) -> None:
        """Remove a broker completely"""
        if run_id in self._brokers:
            self._brokers[run_id].mark_finished()
            del self._brokers[run_id]
            logger.debug(f"Removed Redis broker for run {run_id}")

    async def start_cleanup_task(self) -> None:
        """Start background cleanup task for old brokers"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_old_brokers())

    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_old_brokers(self) -> None:
        """Background task to clean up old finished brokers"""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes

                to_remove = []

                for run_id, broker in self._brokers.items():
                    # Remove brokers that are finished and older than 1 hour
                    if broker.is_finished() and broker.get_age() > 3600:
                        to_remove.append(run_id)

                for run_id in to_remove:
                    self.remove_broker(run_id)
                    logger.info(f"Cleaned up old Redis broker for run {run_id}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Redis broker cleanup task: {e}")
