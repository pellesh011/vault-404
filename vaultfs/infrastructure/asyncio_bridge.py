import asyncio
import threading
from concurrent.futures import Future

import trio


class AsyncioBridge:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._session_lock = asyncio.Lock()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="asyncio-bridge")
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def run(self, coro):  # type: ignore[no-untyped-def]
        async def _locked() -> object:
            async with self._session_lock:
                return await coro

        future: Future = asyncio.run_coroutine_threadsafe(_locked(), self._loop)
        return await trio.to_thread.run_sync(future.result)

    def run_sync(self, coro):  # type: ignore[no-untyped-def]
        async def _locked() -> object:
            async with self._session_lock:
                return await coro

        future: Future = asyncio.run_coroutine_threadsafe(_locked(), self._loop)
        return future.result()

    def close(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
