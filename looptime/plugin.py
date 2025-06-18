"""
Integrations with pytest & pytest-asyncio (irrelevant for other frameworks).

The critical implementation details and the rationale (re-read before changes):


PROBLEM
=======

Pytest-asyncio>=1.0.0 has removed the ``event_loop`` fixture and fully switched
to the ``event_loop_policy`` (session-scoped) plus several independent fixtures:
session-, packages-, module-, class-, function-scoped. It means that a test
might use any of these fixtures.

As a result, our previous assumption that every test runs in its own event loop
is broken. As such, an instance of an event loop can be shared by many tests.

Time, by its nature, MUST be monotonic (always growing, never going backwards).
If we break this core assumption, all hell breaks loose. An anit-example:
the callbacks and other events triggering before they were set up (clock-wise),
the durations of activities being negative, so on. We simply do not do that.

Therefore, we cannot reset the time to zero for every test as we did before.
Therefore, the 2nd, 3rd, so on tests do not start at the loop time "zero",
but at the ever-increasing clock value.

The looptime library, however, is made to simplify the loop time measurements
within a single test (in assertions). This intention comes into a conflict
with the new concept of shared event loops.


SOLUTION
========

In order to solve the conceptual conflict, we abandon the assumption that time
of an event loop is zero-based per test (it can be zero-based per loop though).

Instead, we double-down on the assumption that the ``looptime`` fixture
measures the time on a per-test level and should be used in assertions
(previously, is was a synonym for ``asyncio.get_running_loop().time()``)::

    async def test_me(looptime):
        await asyncio.sleep(123)
        assert looptime == 123

This, in turn, brings a few consequences to the implementation:


CONSEQUENCE 1 — inverted code flow
==================================

It might seem that the easiest way to implement the ``looptime`` fixture is
to make it ``async def`` and get the running loop inside. This does NOT work.

When a function-scoped fixture is used in any higher-scoped test, it degrades
the test from its scope to the function scope and breaks the test design.
See an example at https://github.com/pytest-dev/pytest-asyncio/issues/1142.

As such, the fixture MUST be synchronous (simple ``def``). As a result,
the fixture CANNOT get a running loop, because there is no running loop.

However, the intended event loop is available in the test hook. But the tricky
part is that fixtures are set up _outside_ (i.e. before) the test hook. So,
the inner-nested hook should pass the data into the outer-nested fixture object.

For this, we use pytest stashes (any arbitrary mutable object/dict would work):

- The fixture, when created, remembers the stash.
- The hook populates the stash with the "proper" loop and/or start time.
- The fixture, when evaluated, looks into that stash and gets its value.

Note that the "proper" loop can be of any scope as designed by the test authors
and does not degrade the test to the function-scoped event loop anymore.

There is no easy way how this sophisticated design can be simplified.


CONSEQUENCE 2 — on-demand time compaction
=========================================

In order to make event loops compatible with looptime, they (the event loops)
MUST be patched at creation, not in the middle of a runtime when it hits
the looptime-enabled tests (consider a global session-scoped event loop here).

First of all, we now patch not the event loop, but the event loop policy, since
this is the only publicly documented fixture and the source of event loops.
The patched event loop policy simply produces the patched event loops.

However, tests may be designed either for the "true" time or the "fake" time,
intermixed in any order. We should compact the time only if and when requested.

So, even with the monkey-patched event loop and event loop policy, we toggle off
the time magic by default, and toggle it on for the tests marked for looptime.


RESULT
======

With these hack incapsulated in the looptime library, the time compaction works
as it was intended: only when and if requested, with the time measured per test,
while still supporting the new pytest-asyncio's multi-scoped event loops.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from looptime import loops, patchers, timeproxies, policies


def pytest_configure(config: Any) -> None:
    config.addinivalue_line('markers', "looptime: configure the fake fast-forwarding loop time.")


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("asyncio time contraction")
    group.addoption("--no-looptime", dest='looptime', action="store_const", const=False,
                    help="Force all (even marked) tests to the true loop time.")
    group.addoption("--looptime", dest='looptime', action="store_const", const=True,
                    help="Run unmarked tests with the fake loop time by default.")


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef: Any, request: Any) -> Any:
    # pytest-asyncio<1.0.0 exposed the specific "event_loop" fixture; deprecated since >=0.23.0.
    # But we still support for the older versions, or if some other plugins provide it.
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

    # pytest-asyncio>=1.0.0 exposes only the "event_loop_policy"; available since >=0.23.0.
    # Always patch the whole policy, always at creation. But toggle the magic on & off when needed.
    elif fixturedef.argname == "event_loop_policy":
        result = yield
        policy = cast(asyncio.AbstractEventLoopPolicy, result.get_result()) if result.excinfo is None else None
        if policy is not None and not isinstance(policy, policies.LoopTimeEventLoopPolicy):

            # True means implicitly on; False means explicitly off; None means "only if marked".
            option: bool | None = request.config.getoption('looptime')
            enabled = bool(option is not False)  # None means "maybe", so still patch it.
            if enabled:
                patched_policy = policies.patch_event_loop_policy(policy)
                result.force_result(patched_policy)

    else:
        yield


# NB: It MUST be sync! It CANNOT be async — see the module's docstring.
@pytest.fixture
def looptime(request: pytest.FixtureRequest) -> timeproxies.LoopTimeProxy:
    """
    Expose the time of the test run in the loop-clock time.

    The fixture's value is the number of seconds since the start of the test:

    - It can be used in assertions & comparisons (``==``, ``<=``, etc).
    - It can also be used in simple math (additions, substractions, etc).
    - It can be converted to ``int()`` or ``float()``.

    The assumption is that typical fixtures do not take the loop time,
    i.e. have no intentional sleeps or delays (the external i/o is not counted).
    The fixtures should prepare the environment, the test does the timed things.

    If fixtures do introduce delays, make sure they depend on this fixture,
    so that their time spent is counted towards the fixture's numeric value.

    To make it clear: the fixture assumes that the "time zero" is the moment
    when the test function was entered, as seen by the event loop's time.
    The event loop's time can be zero for the function-scoped event loops,
    but it can also be any arbitrary monotonic value for event loops shared
    by multiple tests with wider scopes (class, module, package, session).
    """
    # Note: the proper "time zero" is NOT yet set. This happens in the hook below — after this line.
    return timeproxies.LoopTimeProxy()


# This hook is the latest (deepest) possible entrypoint before diving into the test function itself,
# with all the fixtures executed earlier, so that their setup time is not taken into account.
# By design, the `looptime` fixture should indicate ONLY the runtime of the test itself.
# The alternatives to consider — the subtle differences are unclear for now:
# - pytest_pyfunc_call(pyfuncitem)
# - pytest_runtest_call(item)
# - pytest_runtest_setup(item), wrapped as @hookimpl(trylast=True)
# But only pytest_fixture_setup(fixturedef, request) has the documented `request` for used fixtures.
@pytest.hookimpl(wrapper=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> Any:

    # Get the policy from the pre-populated & pre-resolved fixture values (done in the setup stage).
    # This includes all the auto-used fixtures, but NOT the dynamic `getfixturevalue(…)` ones.
    # Alternatively, use the private `pyfuncitem._request.getfixturevalue(…)`, though this is hacky.
    funcargs: dict[str, Any] = pyfuncitem.funcargs

    # Not pytest-asyncio-enabled? Then let it run somehow as usual — not our business.
    if 'event_loop_policy' not in funcargs:
        return (yield)

    # Important: this can be ANY event loop of ANY declared scope of pytest-asyncio.
    # The hook itself has NO "running" loop (because it is sync, not async).
    policy: asyncio.AbstractEventLoopPolicy = funcargs['event_loop_policy']
    loop = policy.get_event_loop()
    print(f"HOOK {id(loop)=} {loop=}")  # TODO do not merge

    # The event loop is not patched, we are doomed to fail, so let it run somehow on its own.
    # This might happen if the custom event loop policy explicitly produces incompatible loops.
    if not isinstance(loop, loops.LoopTimeEventLoop):
        return (yield)

    # True means implicitly on; False means explicitly off; None means "only if marked".
    option: bool | None = pyfuncitem.config.getoption('looptime')
    globally_disabled = option is False  # but not None!
    globally_enforced = option is True

    # Decide on the test's intentions: looptime-enabled or now, which options, etc.
    markers = list(pyfuncitem.iter_markers('looptime'))
    enabled = bool((markers or globally_enforced) and not globally_disabled)
    options: dict[str, Any] = {}
    for marker in reversed(markers):
        options.update(marker.kwargs)
        enabled = bool(marker.args[0]) if marker.args else enabled

    # If not enabled/enforced for this test, even if the event loop is patched, let it run as usual.
    if not enabled:
        return (yield)

    # Finally, if enabled/enforced, configure and run the test in the compacted time mode.
    # Note: The loop's time cannot be moved backwards (see the module docstring).
    # So, peg it at the current time, but adjust the looptime fixture to reflect the start=… kwarg.
    # TODO: except start=? end=? or adjusted to the current values?
    desired_start = options.pop('start', None)
    desired_end = options.pop('end', None)
    loop_now = loop.time()

    # Adjust the start/end time to move the time monotonically as explained in the docstring.
    # Technically, we can reset it to zero on every test, but the consequences are unpredictable.
    options['start'] = loop_now
    options['end'] = loop_now + desired_end if desired_end is not None else None  # TODO: callables/clocks

    # Set the "time zero" in the ``looptime`` fixture (again). NB: Fixtures are set up outside
    # of the test/hook, some fixtures can take some time, so this hook's time is the most precise.
    if 'looptime' in funcargs:
        looptime: timeproxies.LoopTimeProxy = funcargs['looptime']
        looptime.zero = loop_now - (desired_start or 0)

    with loop.looptime_enabled():
        loop.setup_looptime(**options)
        return (yield)
