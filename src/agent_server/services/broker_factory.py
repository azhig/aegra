"""Factory for creating appropriate broker based on configuration"""

import os

import structlog

from .base_broker import BaseBrokerManager
from .broker import BrokerManager
from .redis_broker import RedisBrokerManager

logger = structlog.getLogger(__name__)


async def create_broker_manager() -> BaseBrokerManager:
    """Create and return appropriate broker manager based on configuration.

    Returns:
        BaseBrokerManager: Either RedisBrokerManager or in-memory BrokerManager

    Environment Variables:
        STREAMING_BACKEND: "redis" or "memory" (default: "redis")
        REDIS_URL: Redis connection URL (default: "redis://localhost:6379")
    """
    streaming_backend = os.getenv("STREAMING_BACKEND", "redis").lower()

    if streaming_backend == "redis":
        try:
            from ..core.database import db_manager

            redis_client = await db_manager.get_redis_client()
            manager = RedisBrokerManager(redis_client)
            logger.info("✅ Using Redis broker for streaming")
            return manager

        except Exception as e:
            logger.warning(
                f"⚠️ Failed to initialize Redis broker: {e}. Falling back to in-memory broker"
            )
            # Fallback to in-memory
            manager = BrokerManager()
            logger.info("✅ Using in-memory broker for streaming (fallback)")
            return manager
    else:
        # Explicitly configured for in-memory
        manager = BrokerManager()
        logger.info("✅ Using in-memory broker for streaming")
        return manager


# Global broker manager instance
# Note: This will be initialized during app startup
_broker_manager_instance: BaseBrokerManager | None = None


async def get_broker_manager() -> BaseBrokerManager:
    """Get the global broker manager instance.

    This function should be called after the app has started and
    initialize_broker_manager() has been called.
    """
    global _broker_manager_instance

    if _broker_manager_instance is None:
        # Lazy initialization
        _broker_manager_instance = await create_broker_manager()
        await _broker_manager_instance.start_cleanup_task()

    return _broker_manager_instance


async def initialize_broker_manager() -> BaseBrokerManager:
    """Initialize the global broker manager instance during app startup.

    Returns:
        BaseBrokerManager: The initialized broker manager
    """
    global _broker_manager_instance

    if _broker_manager_instance is None:
        _broker_manager_instance = await create_broker_manager()
        await _broker_manager_instance.start_cleanup_task()
        logger.info("✅ Broker manager initialized")

    return _broker_manager_instance


async def shutdown_broker_manager() -> None:
    """Shutdown the global broker manager instance during app shutdown."""
    global _broker_manager_instance

    if _broker_manager_instance is not None:
        await _broker_manager_instance.stop_cleanup_task()
        _broker_manager_instance = None
        logger.info("✅ Broker manager shut down")
