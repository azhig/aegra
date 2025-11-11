"""Tests for Redis broker implementation"""

import pytest


@pytest.mark.asyncio
async def test_redis_broker_basic():
    """Test basic Redis broker functionality"""
    # This is a placeholder test - actual testing requires Redis connection
    # In real environment, this would connect to test Redis instance

    from src.agent_server.services.redis_broker import RedisRunBroker

    # Mock test - just verify imports work
    assert RedisRunBroker is not None


@pytest.mark.asyncio
async def test_broker_factory():
    """Test broker factory can create brokers"""
    from src.agent_server.services.broker_factory import create_broker_manager

    # Test that factory can create manager (will use in-memory fallback without Redis)
    manager = await create_broker_manager()
    assert manager is not None

    # Test getting a broker
    broker = manager.get_or_create_broker("test-run-123")
    assert broker is not None
    assert broker.run_id == "test-run-123"


@pytest.mark.asyncio
async def test_in_memory_broker():
    """Test in-memory broker (default fallback)"""
    from src.agent_server.services.broker import BrokerManager

    manager = BrokerManager()
    broker = manager.get_or_create_broker("test-run")

    # Test put and retrieve
    await broker.put("event1", ("values", {"test": "data"}))
    broker.mark_finished()

    # Verify broker is finished
    assert broker.is_finished()
