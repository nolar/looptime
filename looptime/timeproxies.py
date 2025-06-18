from __future__ import annotations

import asyncio

from looptime import math


class LoopTimeProxy(math.Numeric):
    """
    A numeric-compatible proxy to the time of the current/specific event loop.
    """
    zero: float  # mutable! where our "time zero" is in the monotonic loop time.

    def __init__(
            self,
            loop: asyncio.AbstractEventLoop | None = None,
            *,
            resolution: float = 1e-9,
    ) -> None:
        super().__init__(resolution=resolution)
        self._loop = loop
        self.zero = 0

    def __repr__(self) -> str:
        return f"<Loop time: {self._value}>"

    def __matmul__(self, other: object) -> LoopTimeProxy:
        if isinstance(other, asyncio.AbstractEventLoop):
            return self.__class__(other)
        else:
            return NotImplemented

    @property
    def _value(self) -> float:
        loop = self._loop if self._loop is not None else asyncio.get_running_loop()
        return loop.time() - self.zero
