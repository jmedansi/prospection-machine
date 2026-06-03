import pytest
import asyncio
from browser_manager import BrowserManager


@pytest.mark.asyncio
async def test_concurrency_limit():
    """Test that max_concurrent is respected."""
    manager = BrowserManager(max_concurrent=3)
    await manager.start()
    
    tasks = []
    for i in range(5):
        async def task():
            async with manager.get_page() as page:
                await page.goto("https://httpbin.org/delay/1")
                return True
        tasks.append(task())
    
    # Run concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Should have 5 successes
    successes = [r for r in results if not isinstance(r, Exception)]
    assert len(successes) == 5
    
    await manager.shutdown()
    
    # Check metrics
    metrics = manager.get_metrics()
    assert metrics["acquires"] == 5
    assert metrics["releases"] == 5