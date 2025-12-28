===============
Tools & Helpers
===============

Chronometers
============

For convenience, the library also provides a class and a fixture
to measure the duration of arbitrary code blocks in real-world time:

* :class:`looptime.Chronometer` (a context manager class).
* ``chronometer`` (a pytest fixture).

It can be used as a sync or async context manager:

.. code-block:: python

    import asyncio
    import pytest

    @pytest.mark.asyncio
    @pytest.mark.looptime
    async def test_me(chronometer):
        with chronometer:
            await asyncio.sleep(1)
            await asyncio.sleep(1)
        assert chronometer.seconds < 0.01  # random code overhead

Usually, the loop-time duration is not needed or can be retrieved via
``asyncio.get_running_loop().time()``. If needed, it can be measured using
the provided context manager class with the event loop's clock:

.. code-block:: python

    import asyncio
    import looptime
    import pytest

    @pytest.mark.asyncio
    @pytest.mark.looptime(start=100)
    async def test_me(chronometer, event_loop):
        with chronometer, looptime.Chronometer(event_loop.time) as loopometer:
            await asyncio.sleep(1)
            await asyncio.sleep(1)
        assert chronometer.seconds < 0.01  # random code overhead
        assert loopometer.seconds == 2  # precise timing, no code overhead
        assert event_loop.time() == 102


Assertions
==========

The ``looptime`` **fixture** is syntactic sugar for easy loop time assertions:

.. code-block:: python

    import asyncio
    import pytest

    @pytest.mark.asyncio
    @pytest.mark.looptime(start=100)
    async def test_me(looptime):
        await asyncio.sleep(1.23)
        assert looptime == 101.23

Technically, it is a proxy object for ``asyncio.get_running_loop().time()``.
The proxy object supports direct comparison with numbers (integers/floats),
as well as some basic arithmetic (addition, subtraction, multiplication, etc.).
However, it adjusts to a time precision of 1 nanosecond (1e-9): every digit
beyond that precision is ignored — so you do not need to be afraid of
``123.456/1.2`` suddenly becoming ``102.88000000000001`` and not equal to ``102.88``
(as long as the time proxy object is used and not converted to a native float).

The proxy object can be used to create a new proxy that is bound
to a specific event loop with the ``@`` operation
(it works for loops with both fake and real-world time):

.. code-block:: python

    import asyncio
    from looptime import patch_event_loop

    def test_me(looptime):
        new_loop = patch_event_loop(asyncio.new_event_loop(), start=100)
        new_loop.run_until_complete(asyncio.sleep(1.23))
        assert looptime @ new_loop == 101.23

Keep in mind that it is not the same as :class:`Chronometer` for the whole test.
The time proxy reflects the time of the loop, not the duration of the test:
the loop time can start at a non-zero point; even if it starts at zero,
the loop time also includes the time of all fixture setups.


Custom event loops & mixins
===========================

Do you use a custom event loop? No problem! Create a test-specific descendant
with the provided mixin — and it will work the same as the default event loop.

For ``pytest-asyncio<1.0.0``, use the ``event_loop`` fixture:

.. code-block:: python

    import looptime
    import pytest
    from wherever import CustomEventLoop


    class LooptimeCustomEventLoop(looptime.LoopTimeEventLoop, CustomEventLoop):
      pass


    @pytest.fixture
    def event_loop():
        return LooptimeCustomEventLoop()

For ``pytest-asyncio>=1.0.0``, use the ``event_loop_policy``:

.. code-block:: python

    import asyncio
    import looptime
    import pytest
    from wherever import CustomEventLoop


    class LooptimeCustomEventLoop(looptime.LoopTimeEventLoop, CustomEventLoop):
        pass


    class LooptimeCustomEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
        def new_event_loop(self):
            return LooptimeCustomEventLoop()


    @pytest.fixture(scope='session')
    def event_loop_policy():
        return LooptimeCustomEventLoopPolicy()

Only selector-based event loops are supported: the event loop must rely on
``self._selector.select(timeout)`` to sleep for ``timeout`` true-time seconds.
Everything that inherits from ``asyncio.BaseEventLoop`` should work,
but a more generic ``asyncio.AbstractEventLoop`` might be a problem.

You can also patch almost any event loop class or event loop object
the same way as ``looptime`` does (via some dirty hackery):

For ``pytest-asyncio<1.0.0`` and the ``even_loop`` fixture:

.. code-block:: python

    import asyncio
    import looptime
    import pytest


    @pytest.fixture
    def event_loop():
        loop = asyncio.new_event_loop()
        return looptime.patch_event_loop(loop)

For ``pytest-asyncio>=1.0.0`` and the ``event_loop_policy`` fixture:

.. code-block:: python

    import asyncio
    import looptime
    import pytest


    class LooptimeEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
        def new_event_loop(self):
            loop = super().new_event_loop()
            return looptime.patch_event_loop(loop)


    @pytest.fixture(scope='session')
    def event_loop_policy():
        return LooptimeEventLoopPolicy()

``looptime.make_event_loop_class(cls)`` constructs a new class that inherits
from the referenced class and the specialized event loop class mentioned above.
The resulting classes are cached, so it can be safely called multiple times.

``looptime.patch_event_loop()`` replaces the event loop's class with the newly
constructed one. For those who care, it is an equivalent of the following hack
(some restrictions apply to the derived class).

In general, patching the existing event loop instance is done by this hack:

.. code-block:: python

    loop.__class__ = looptime.make_event_loop_class(loop.__class__)
