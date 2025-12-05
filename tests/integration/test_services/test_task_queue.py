"""Tests for task queue system"""

import pytest


@pytest.mark.asyncio
async def test_task_queue_import():
    """Test that task queue module can be imported"""
    from src.agent_server.services.task_queue import TaskQueue

    assert TaskQueue is not None


@pytest.mark.asyncio
async def test_worker_executor_import():
    """Test that worker executor module can be imported"""
    from src.agent_server.worker.executor import WorkerExecutor

    assert WorkerExecutor is not None


@pytest.mark.asyncio
async def test_sweeper_import():
    """Test that sweeper module can be imported"""
    from src.agent_server.services.sweeper import RunSweeper

    assert RunSweeper is not None
