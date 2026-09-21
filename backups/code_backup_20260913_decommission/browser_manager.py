import asyncio
from typing import AsyncGenerator, Optional, Set, Tuple
import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager

try:
    from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page
    from playwright.async_api import Error as PlaywrightError
except Exception:  # pragma: no cover - handled at runtime if Playwright isn't installed
    async_playwright = None  # type: ignore
    Playwright = Browser = BrowserContext = Page = object  # type: ignore
    PlaywrightError = Exception

try:
    import greenlet
    GreenletError = greenlet.error
except Exception:
    GreenletError = Exception


class BrowserManager:
    """Async browser manager with a simple concurrency pool.

    Features:
    - `acquire_page()` / `release_context()` to obtain and free pages/contexts
    - concurrency limit via an asyncio.Semaphore
    - `shutdown()` to close contexts and browser cleanly
    - defensive handling for Playwright errors and greenlet errors
    - metrics, logging, watchdog, env config
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        browser_type: str = "chromium",
        headless: bool = True,
        launch_args: Optional[dict] = None,
        context_kwargs: Optional[dict] = None,
    ):
        # Config from env
        self._max_concurrent = int(os.getenv("BROWSER_POOL_MAX", max_concurrent))
        self._acquire_timeout = float(os.getenv("BROWSER_ACQUIRE_TIMEOUT_S", 30.0))
        self._watchdog_timeout = float(os.getenv("BROWSER_WATCHDOG_TIMEOUT_S", 300.0))  # 5 min default

        self._browser_type = browser_type
        self._headless = headless
        self._launch_args = launch_args or {}
        self._context_kwargs = context_kwargs or {}

        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._contexts: Set[BrowserContext] = set()
        self._shared_context: Optional[BrowserContext] = None

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._started = False
        self._lock = asyncio.Lock()

        # Metrics
        self._metrics = {
            "open_contexts": 0,
            "acquires": 0,
            "releases": 0,
            "acquire_timeouts": 0,
            "errors": defaultdict(int),
        }

        # Watchdog: context -> acquire_time
        self._context_times: dict[BrowserContext, float] = {}

        # Logger
        self._logger = logging.getLogger(__name__)

    async def start(self) -> None:
        """Start Playwright and launch a browser instance."""
        if self._started:
            return
        async with self._lock:
            if self._started:
                return
            if async_playwright is None:
                raise RuntimeError("playwright is not installed. Install with `pip install playwright`.")
            self._playwright = await async_playwright().start()  # type: ignore
            browser_launcher = getattr(self._playwright, self._browser_type)
            self._browser = await browser_launcher.launch(headless=self._headless, **self._launch_args)  # type: ignore
            self._started = True

    async def acquire_page(self, timeout: Optional[float] = None) -> Tuple[BrowserContext, Page]:
        """Acquire a fresh BrowserContext and Page.

        Use `release_context(context)` when finished.
        """
        await self.start()
        if timeout is None:
            timeout = self._acquire_timeout
        try:
            start_time = time.time()
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
            except asyncio.TimeoutError as e:
                self._metrics["acquire_timeouts"] += 1
                self._logger.warning(f"Timeout acquiring browser slot after {timeout}s")
                raise TimeoutError("Timeout acquiring browser slot") from e

            acquire_time = time.time() - start_time
            self._logger.debug(f"Acquired browser slot in {acquire_time:.2f}s")

            # create a new context and page
            context = await self._browser.new_context(**self._context_kwargs)  # type: ignore
            page = await context.new_page()
            self._contexts.add(context)
            self._context_times[context] = time.time()
            self._metrics["open_contexts"] += 1
            self._metrics["acquires"] += 1
            return context, page
        except GreenletError as e:
            # defensively catch greenlet thread-switch errors if they bubble up
            self._metrics["errors"]["greenlet"] += 1
            self._logger.error(f"Greenlet error in acquire_page: {e}")
            try:
                self._semaphore.release()
            except Exception:
                pass
            raise
        except PlaywrightError as e:
            # ensure we release the slot on playwright errors
            self._metrics["errors"]["playwright"] += 1
            self._logger.error(f"Playwright error in acquire_page: {e}")
            try:
                self._semaphore.release()
            except Exception:
                pass
            raise
        except Exception as e:
            self._metrics["errors"]["other"] += 1
            self._logger.error(f"Unexpected error in acquire_page: {e}")
            try:
                self._semaphore.release()
            except Exception:
                pass
            raise

    async def release_context(self, context: BrowserContext) -> None:
        """Close a BrowserContext and release the semaphore slot."""
        if context is None:
            return
        try:
            # remove from set first to avoid double-close races
            if context in self._contexts:
                self._contexts.discard(context)
                self._metrics["open_contexts"] -= 1
            if context in self._context_times:
                del self._context_times[context]
            await context.close()
            self._metrics["releases"] += 1
        except Exception as e:
            # ignore individual close errors; continue cleaning
            self._metrics["errors"]["close"] += 1
            self._logger.warning(f"Error closing context: {e}")
            pass
        finally:
            try:
                self._semaphore.release()
            except Exception:
                pass

    async def _watchdog_check(self) -> None:
        """Check for contexts open longer than watchdog timeout and log warnings."""
        now = time.time()
        to_close = []
        for ctx, start_time in self._context_times.items():
            if now - start_time > self._watchdog_timeout:
                self._logger.warning(f"Context open for {now - start_time:.2f}s, exceeding {self._watchdog_timeout}s")
                to_close.append(ctx)
        for ctx in to_close:
            try:
                await self.release_context(ctx)
                self._logger.info("Force-closed long-open context")
            except Exception as e:
                self._logger.error(f"Failed to force-close context: {e}")

    def get_metrics(self) -> dict:
        """Return current metrics."""
        return dict(self._metrics)

    async def acquire_shared_context(self) -> BrowserContext:
        """Create (or return) a single shared BrowserContext for scrapers that reuse one context."""
        await self.start()
        if self._shared_context:
            return self._shared_context
        # create a dedicated shared context
        ctx = await self._browser.new_context(**self._context_kwargs)  # type: ignore
        self._shared_context = ctx
        self._contexts.add(ctx)
        return ctx

    async def release_shared_context(self) -> None:
        """Close the shared context if present."""
        if not self._shared_context:
            return
        try:
            ctx = self._shared_context
            self._shared_context = None
            if ctx in self._contexts:
                self._contexts.discard(ctx)
            await ctx.close()
        except Exception:
            pass

    async def page_from_shared(self) -> AsyncGenerator[Page, None]:
        """Acquire a `Page` created from the shared context, guarded by the semaphore.

        Usage:
            async with manager.page_from_shared() as page:
                await page.goto(...)
        """
        ctx = await self.acquire_shared_context()
        try:
            await self._semaphore.acquire()
            page = await ctx.new_page()
            try:
                yield page
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
                try:
                    self._semaphore.release()
                except Exception:
                    pass
        except Exception:
            try:
                self._semaphore.release()
            except Exception:
                pass
            raise

    @asynccontextmanager
    async def get_page(self):
        """Async context manager to use a page with `async with manager.get_page() as page:`"""
        context, page = await self.acquire_page()
        try:
            yield page
        finally:
            await self.release_context(context)

    async def shutdown(self) -> None:
        """Close all contexts, the browser and stop Playwright."""
        # Close open contexts
        contexts = list(self._contexts)
        for ctx in contexts:
            try:
                await ctx.close()
                self._metrics["open_contexts"] -= 1
            except Exception:
                pass
        self._contexts.clear()

        # Close browser
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass

        # Stop playwright
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass

        self._started = False


__all__ = ["BrowserManager"]
