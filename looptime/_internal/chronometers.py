from __future__ import annotations

import gc
import time
from collections.abc import Callable
from typing import Any, Self

from . import math


class Chronometer(math.Numeric):
    """
    A helper context manager to measure the time of the code-blocks.

    Usage:

    .. code-block:: python

        import time

        def test_chronometer():
            with Chronometer() as chronometer:
                time.sleep(1.23)  # do something slow
                print(f"Executing for {chronometer.seconds}s already.")
                time.sleep(2.34)  # do something slow again

            print(f"Executed in {chronometer.seconds}s.")
            assert chronometer.seconds < 5.0  # 3.57s or slightly more
    """

    def __init__(
            self,
            clock: Callable[[], float] = time.perf_counter,
            *,
            keep_gc: bool = False,
    ) -> None:
        super().__init__()
        self._clock = clock
        self._ts: float | None = None
        self._te: float | None = None
        self._keep_gc = keep_gc
        self.__preserved_gc: bool | None = None

    @property
    def _value(self) -> float:
        return float(self.seconds or 0)

    @property
    def seconds(self) -> float | None:
        """The elapsed time in seconds (fractional)."""
        if self._ts is None:
            return None
        elif self._te is None:
            return self._clock() - self._ts
        else:
            return self._te - self._ts

    def __repr__(self) -> str:
        status = 'new' if self._ts is None else 'running' if self._te is None else 'finished'
        return f'<Chronometer: {self.seconds}s ({status})>'

    def __enter__(self) -> Self:
        if not self._keep_gc:  # NB: outside of the measurement
            self.__preserved_gc = gc.isenabled()
            gc.disable()
        self._te = None
        self._ts = self._clock()  # NB: the innermost instruction
        return self

    def __exit__(self, *args: Any) -> None:
        self._te = self._clock()  # NB: the innermost instruction
        if self.__preserved_gc:  # NB: outside of the measurement
            self.__preserved_gc = None
            gc.enable()

    async def __aenter__(self) -> Self:
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
