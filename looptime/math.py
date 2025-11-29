from __future__ import annotations

import abc
from typing import Any


class Numeric(metaclass=abc.ABCMeta):
    """A base class for objects that support direct comparison & arithmetics."""

    def __init__(self, *, resolution: float = 1e-9) -> None:
        super().__init__()
        self.__rr: int = round(1 / resolution)  # rr == resolution reciprocal

    @property
    @abc.abstractmethod
    def _value(self) -> float:
        raise NotImplementedError

    #
    # Type conversion:
    #

    def __str__(self) -> str:
        return str(float(self))

    def __int__(self) -> int:
        return int(float(self))

    def __float__(self) -> float:
        return round(self._value * self.__rr) / self.__rr

    #
    # Comparison:
    #

    def __eq__(self, other: object) -> bool:
        match other:
            case int() | float():
                return round(self._value * self.__rr) == round(other * self.__rr)
            case _:
                return NotImplemented

    def __ne__(self, other: object) -> bool:
        match other:
            case int() | float():
                return round(self._value * self.__rr) != round(other * self.__rr)
            case _:
                return NotImplemented

    def __ge__(self, other: object) -> bool:
        match other:
            case int() | float():
                return round(self._value * self.__rr) >= round(other * self.__rr)
            case _:
                return NotImplemented

    def __gt__(self, other: object) -> bool:
        match other:
            case int() | float():
                return round(self._value * self.__rr) > round(other * self.__rr)
            case _:
                return NotImplemented

    def __le__(self, other: object) -> bool:
        match other:
            case int() | float():
                return round(self._value * self.__rr) <= round(other * self.__rr)
            case _:
                return NotImplemented

    def __lt__(self, other: object) -> bool:
        match other:
            case int() | float():
                return round(self._value * self.__rr) < round(other * self.__rr)
            case _:
                return NotImplemented

    #
    # Arithmetics:
    #

    def __add__(self, other: object) -> float:
        match other:
            case int() | float():
                return (round(self._value * self.__rr) + round(other * self.__rr)) / self.__rr
            case _:
                return NotImplemented

    def __sub__(self, other: object) -> float:
        match other:
            case int() | float():
                return (round(self._value * self.__rr) - round(other * self.__rr)) / self.__rr
            case _:
                return NotImplemented

    def __mul__(self, other: object) -> float:
        match other:
            case int() | float():
                return (round(self._value * self.__rr) * round(other * self.__rr)) / (self.__rr ** 2)
            case _:
                return NotImplemented

    def __floordiv__(self, other: object) -> float:
        match other:
            case int() | float():
                return (round(self._value * self.__rr) // round(other * self.__rr))
            case _:
                return NotImplemented

    def __truediv__(self, other: object) -> float:
        match other:
            case int() | float():
                return (round(self._value * self.__rr) / round(other * self.__rr))
            case _:
                return NotImplemented

    def __mod__(self, other: object) -> float:
        match other:
            case int() | float():
                return (round(self._value * self.__rr) % round(other * self.__rr)) / (self.__rr)
            case _:
                return NotImplemented

    # See the StdLib's comments on pow() on why it is Any, not float.
    def __pow__(self, power: float, modulo: None = None) -> Any:
        return pow(round(self._value * self.__rr), power, modulo) / pow(self.__rr, power, modulo)
