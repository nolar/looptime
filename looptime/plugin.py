from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from looptime import loops, patchers


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef: Any, request: Any) -> Any:
    if fixturedef.argname == "event_loop":
        result = yield
        loop = cast(asyncio.BaseEventLoop, result.get_result()) if result.excinfo is None else None
        if loop is not None and not isinstance(loop, loops.LoopTimeEventLoop):

            # True means implicitly on; False means explicitly off; None means "only if marked".
            option: bool | None = request.config.getoption('looptime')

            markers = list(request.node.iter_markers('looptime'))
            enabled = bool((markers or option is True) and option is not False)  # but not None!
            options = {}
            for marker in reversed(markers):
                options.update(marker.kwargs)
                enabled = bool(marker.args[0]) if marker.args else enabled

            if enabled:
                patched_loop = patchers.patch_event_loop(loop)
                patched_loop.setup_looptime(**options)
                result.force_result(patched_loop)
    else:
        yield


def pytest_configure(config: Any) -> None:
    config.addinivalue_line('markers', "looptime: configure the fake fast-forwarding loop time.")


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("asyncio time contraction")
    group.addoption("--no-looptime", dest='looptime', action="store_const", const=False,
                    help="Force all (even marked) tests to the true loop time.")
    group.addoption("--looptime", dest='looptime', action="store_const", const=True,
                    help="Run unmarked tests with the fake loop time by default.")
