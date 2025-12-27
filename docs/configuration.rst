=============
Configuration
=============

Markers
=======

``@pytest.mark.looptime`` configures the test's options if and when it is
executed with the timeline replaced to fast-forwarding time.
In normal mode with no configs/CLI options specified,
it marks the test to be executed with the time replaced.

``@pytest.mark.looptime(False)`` (with the positional argument)
excludes the test from the time fast-forwarding under any circumstances.
The test will be executed with the loop time aligned with the real-world time.
Use it only for the tests that are designed to be true-time-based.

Note that markers can be applied not only to individual tests,
but also to whole test suites (classes, modules, packages):

.. code-block:: python

    import asyncio
    import pytest

    pytestmark = [
      pytest.mark.asyncio,
      pytest.mark.looptime(end=60),
    ]


    async def test_me():
        await asyncio.sleep(100)

The markers can also be artificially injected by plugins/hooks if needed:

.. code-block:: python

    import inspect
    import pytest

    @pytest.hookimpl(hookwrapper=True)
    def pytest_pycollect_makeitem(collector, name, obj):
        if collector.funcnamefilter(name) and inspect.iscoroutinefunction(obj):
            pytest.mark.asyncio(obj)
            pytest.mark.looptime(end=60)(obj)
        yield

All in all, the ``looptime`` plugin uses the most specific (the "closest") value
for each setting separately (i.e. not the closest marker as a whole).


Options
=======

``--looptime`` enables time fast-forwarding for all tests that are not explicitly
marked as using the fake loop time —including those not marked at all—
as if all tests were implicitly marked.

``--no-looptime`` runs all tests —both marked and unmarked— with the real time.
This flag effectively disables the plugin.


Settings
========

The marker accepts several settings for the test. The closest to the test
function applies. This lets you define the test-suite defaults
and override them on the directory, module, class, function, or test level:

.. code-block:: python

    import asyncio
    import pytest

    pytestmark = pytest.mark.looptime(end=10, idle_timeout=1)

    @pytest.mark.asyncio
    @pytest.mark.looptime(end=101)
    async def test_me():
        await asyncio.sleep(100)
        assert asyncio.get_running_loop().time() == 100


The time zero
-------------

``start`` (``float`` or ``None``, or a no-argument callable that returns the same)
is the initial time of the event loop.

If it is a callable, it is invoked once per event loop to get the value:
e.g. ``start=time.monotonic`` to align with the true time,
or ``start=lambda: random.random() * 100`` to add some unpredictability.

``None`` is treated the same as ``0.0``.

The default is ``0.0``. For reusable event loops, the default is to keep
the time untouched, which means ``0.0`` or the explicit value for the first test,
but then an ever-increasing value for the 2nd, 3rd, and further tests.

.. note::
    pytest-asyncio 1.0.0+ introduced event loops with higher scopes,
    e.g. class-, module-, packages-, session-scoped event loops used in tests.
    Such event loops are reused, so their time continues growing through many tests.
    However, if the test is explicitly configured with the start time,
    that time is enforced to the event loop when the test function starts —
    to satisfy the clearly declared intentions — even if the time moves backwards,
    which goes against the nature of the time itself (monotonically growing).
    This might lead to surprises in time measurements outside of the test,
    e.g. in fixtures: the code durations can become negative, or the events can
    happen (falsely) before they are scheduled (loop-clock-wise). Be careful.


The end of time
---------------

``end`` (``float`` or ``None``, or a no-argument callable that returns the same)
is the final time in the event loop (the internal fake time).
If it is reached, all tasks get terminated and the test is supposed to fail.
The injected exception is :class:`looptime.LoopTimeoutError`,
a subclass of :class:`asyncio.TimeoutError`.

All test-/fixture-finalizing routines will have their fair chance to execute
as long as they do not move the loop time forward, i.e. they take zero time:
e.g. with ``asyncio.sleep(0)``, simple ``await`` statements, etc.

If set to ``None``, there is no end of time, and the event loop runs
as long as needed. Note: ``0`` means ending the time immediately on start.
Be careful with the explicit ending time in higher-scoped event loops
of pytest-asyncio>=1.0.0, since they time increases through many tests.

If it is a callable, it is called once per event loop to get the value:
e.g. ``end=lambda: time.monotonic() + 10``.

The end of time is not the same as timeouts — see :doc:`nuances`
on differences with ``async-timeout``.
