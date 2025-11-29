from __future__ import annotations

import asyncio

from looptime import math


class LoopTimeProxy(math.Numeric):
    """
    A numeric-compatible proxy to the time of the current/specific event loop.
    """

    def __init__(
            self,
            loop: asyncio.AbstractEventLoop | None = None,
            *,
            resolution: float = 1e-9,
    ) -> None:
        super().__init__(resolution=resolution)
        self._loop = loop

    def __repr__(self) -> str:
        return f"<Loop time: {self._value}>"

    def __matmul__(self, other: object) -> LoopTimeProxy:
        match other:
            case asyncio.AbstractEventLoop():
                return self.__class__(other)
            case _:
                return NotImplemented

    @property
    def _value(self) -> float:
        return self._loop.time() if self._loop is not None else asyncio.get_running_loop().time()
