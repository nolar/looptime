from __future__ import annotations

import time
from typing import Any, Callable, TypeVar

from looptime import math

_SelfT = TypeVar('_SelfT', bound="Chronometer")


class Chronometer(math.Numeric):
    """
    A helper context manager to measure the time of the code-blocks.

    Usage:

        with Chronometer() as chronometer:
            do_something()
            print(f"Executing for {chronometer.seconds}s already.")
            do_something_else()

        print(f"Executed in {chronometer.seconds}s.")
        assert chronometer.seconds < 5.0
    """

    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        super().__init__()
        self._clock = clock
        self._ts: float | None = None
        self._te: float | None = None

    @property
    def _value(self) -> float:
        return float(self.seconds or 0)

    @property
    def seconds(self) -> float | None:
        if self._ts is None:
            return None
        elif self._te is None:
            return self._clock() - self._ts
        else:
            return self._te - self._ts

    def __repr__(self) -> str:
        status = 'new' if self._ts is None else 'running' if self._te is None else 'finished'
        return f'<Chronometer: {self.seconds}s ({status})>'

    def __enter__(self: _SelfT) -> _SelfT:
        self._ts = self._clock()
        self._te = None
        return self

    def __exit__(self, *args: Any) -> None:
        self._te = self._clock()

    async def __aenter__(self: _SelfT) -> _SelfT:
        return self.__enter__()

    async def __aexit__(self, *args: Any) -> None:
        return self.__exit__(*args)


try:
    import pytest
except ImportError:
    pass
else:
    @pytest.fixture()
    def chronometer() -> Chronometer:
        return Chronometer()
