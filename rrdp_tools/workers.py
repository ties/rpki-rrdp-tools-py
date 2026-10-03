import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


async def run_workers(
    items: Iterable[T],
    process: Callable[[T], Awaitable[R]],
    workers: int,
) -> tuple[list[R], list[tuple[T, Exception]]]:
    """Run `process` on `items` using at most `workers` concurrent workers.

    Only `workers` tasks are created, however many items there are. A failing
    item does not stop the others: returns the results and (item, exception)
    for the failures.
    """
    queue: asyncio.Queue[T] = asyncio.Queue()
    for item in items:
        queue.put_nowait(item)

    results: list[R] = []
    failures: list[tuple[T, Exception]] = []

    async def worker() -> None:
        while not queue.empty():
            item = queue.get_nowait()
            try:
                results.append(await process(item))
            except Exception as e:  # noqa: BLE001
                failures.append((item, e))

    await asyncio.gather(*(worker() for _ in range(min(workers, queue.qsize()))))
    return results, failures
