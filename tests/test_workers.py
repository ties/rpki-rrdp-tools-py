import asyncio

import pytest

from rrdp_tools.workers import run_workers


@pytest.mark.asyncio
async def test_run_workers_bounds_concurrency():
    active = max_active = 0

    async def process(item: int) -> int:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        active -= 1
        return item * 2

    results, failures = await run_workers(range(20), process, workers=3)

    assert sorted(results) == [i * 2 for i in range(20)]
    assert failures == []
    assert max_active == 3


@pytest.mark.asyncio
async def test_run_workers_collects_failures_and_continues():
    async def process(item: int) -> int:
        if item % 5 == 0:
            raise ValueError(f"bad {item}")
        return item

    results, failures = await run_workers(range(20), process, workers=2)

    assert sorted(results) == [i for i in range(20) if i % 5 != 0]
    assert [item for item, _ in failures] == [0, 5, 10, 15]
    assert all(isinstance(e, ValueError) for _, e in failures)


@pytest.mark.asyncio
async def test_run_workers_no_items():
    async def process(item: int) -> int:
        raise AssertionError("not called")

    assert await run_workers([], process, workers=4) == ([], [])
