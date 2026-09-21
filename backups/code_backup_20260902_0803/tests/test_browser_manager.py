import pytest
import asyncio
from browser_manager import BrowserManager


@pytest.mark.asyncio
async def test_acquire_release():
    """Test acquire/release with semaphore."""
    manager = BrowserManager(max_concurrent=2)
    await manager.start()
    
    # Acquire up to max
    ctx1, page1 = await manager.acquire_page()
    ctx2, page2 = await manager.acquire_page()
    
    # Should block or timeout for third
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(manager.acquire_page(), timeout=1.0)
    
    # Release one
    await manager.release_context(ctx1)
    
    # Now can acquire again
    ctx3, page3 = await manager.acquire_page()
    
    await manager.release_context(ctx2)
    await manager.release_context(ctx3)
    
    await manager.shutdown()
    assert manager.get_metrics()["acquires"] == 3
    assert manager.get_metrics()["releases"] == 3


@pytest.mark.asyncio
async def test_exception_releases():
    """Test that exceptions release semaphore."""
    manager = BrowserManager(max_concurrent=1)
    await manager.start()
    
    try:
        async with manager.get_page() as page:
            await page.goto("https://httpbin.org/status/200")
            # Simulate exception
            raise ValueError("test")
    except ValueError:
        pass
    
    # Should be able to acquire again
    async with manager.get_page() as page:
        await page.goto("https://httpbin.org/status/200")
    
    await manager.shutdown()


@pytest.mark.asyncio
async def test_shutdown_cleans():
    """Test shutdown closes all contexts."""
    manager = BrowserManager(max_concurrent=2)
    await manager.start()
    
    ctx1, page1 = await manager.acquire_page()
    ctx2, page2 = await manager.acquire_page()
    
    assert len(manager._contexts) == 2
    
    await manager.shutdown()
    
    assert len(manager._contexts) == 0
    assert manager.get_metrics()["open_contexts"] == 0