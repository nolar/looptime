from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from looptime import loops, patchers, timeproxies


@pytest.fixture()
def looptime() -> timeproxies.LoopTimeProxy:
    return timeproxies.LoopTimeProxy()


def pytest_configure(config: Any) -> None:
    config.addinivalue_line('markers', "looptime: configure the fake fast-forwarding loop time.")


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("asyncio time contraction")
    group.addoption("--no-looptime", dest='looptime', action="store_const", const=False,
                    help="Force all (even marked) tests to the true loop time.")
    group.addoption("--looptime", dest='looptime', action="store_const", const=True,
                    help="Run unmarked tests with the fake loop time by default.")


@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(fixturedef: Any, request: Any) -> Any:
    result = yield

    if fixturedef.argname == "event_loop":
        loop = cast(asyncio.BaseEventLoop, result)
        if not isinstance(loop, loops.LoopTimeEventLoop):

            # True means implicitly on; False means explicitly off; None means "only if marked".
            option: bool | None = request.config.getoption('looptime')

            markers = list(request.node.iter_markers('looptime'))
            enabled = bool((markers or option is True) and option is not False)  # but not None!
            options = {}
            for marker in reversed(markers):
                options.update(marker.kwargs)
                enabled = bool(marker.args[0]) if marker.args else enabled

            result = patched_loop = patchers.patch_event_loop(loop, _enabled=False)
            if enabled:
                patched_loop.setup_looptime(**options, _enabled=True)

    return result
