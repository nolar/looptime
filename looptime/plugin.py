"""
Integrations with pytest & pytest-asyncio (irrelevant for other frameworks).


IMPLEMENTATION DETAIL - reverse time movement
=============================================

Problem
-------

Pytest-asyncio>=1.0.0 has removed the ``event_loop`` fixture and fully switched
to the ``event_loop_policy`` (session-scoped) plus several independent fixtures:
session-, package-, module-, class-, function-scoped. It means that a test
might use any of these fixtures or several or all of them at the same time.

As a result, our previous assumption that every test & all its fixtures run
in its own isolated short-lived event loop, is now broken:

- A single event loop can be shared by multiple (but not all) tests.
- A single test can be spread over multiple (but not all) event loops.

An classic example:

- A session-scoped fixture ``server`` starts a port listener & an HTTP server.
- A module-scoped fixture ``data`` populates the server via POST requests.
- A few function-scoped tests access & assert these data via GET requests.
- Other tests verify the database and do not touch the event loops.

Looptime suggests setting the start time of the event loop or expect it to be 0.
This simplifies assertions, scheduling of events, callbacks, and other triggers.

As a result, a long-living event loop might see the time set/reset by tests,
and in most cases, it will be moving the time backwards.

Time, by its nature, is supposed to be monotonic (but can be non-linear),
specifically positively monotonic — always growing, never going backwards.


Solution
--------

We sacrifice this core property of time for the sake of simplicity of tests.

So we should be prepared for the consequences when all hell breaks loose. E.g.:
the callbacks and other events triggering before they were set up (clock-wise);
the durations of activities being negative; so on.

Either way, we set the loop time as requested, but with a few nuances:

1. If the start time is NOT explicitly defined, for higher-scoped event loops,
   we keep the time as is for every test and let it flow monotonically.
   Previously, the higher-scoped fixtures did not exist, so nothing breaks.

2. If the start time is explicitly defined and is in the future, move the time
   forwards as specified — indistinguishable from the previous behaviour
   (except there could be artifacts from the previous tests in the loop).

3. If the start time is explicitly defined and is in the past, issue a warning
   of class ``looptime.TimeWarning``, which inherits from ``UserWarning``,
   indicating a user-side misbehaviour & broken test-suite design.
   It can be configured to raise an error (strict mode), or be ignored.

This ensures the most possible backwards compatibility with the old behavior
with a few truthworthy assumptions in mind:

- Fixtures do not measure time and do not rely on time. Their purpose should be
  preparing the environment, filling the data. Only the tests can move the time.
  As such, they will not suffer much from the backward time movements.

- Old-style tests typically use the function scope & the function-scoped loop,
  which has the time set at 0 by default. No changes to the previous behaviour.

- New-style tests that run in higher-scoped loops (a new pytest-asyncio feature)
  should not rely on an isolated event loop and the time starting with 0,
  and should be clearly prepared for the backward time movements
  if they express the intention to reset the start time of the event loop.
  Such tests should measure the "since" and "till" and assert on the difference.


IMPLEMENTATION DETAIL — patching always, activating on-demand
=============================================================

In order to make event loops compatible with looptime, they (the event loops)
MUST be patched at creation, not in the middle of a runtime when it reaches
the looptime-enabled tests (consider a global session-scoped event loop here).

Therefore, we patch ALL the implicit event loops of pytest-asyncio, regardless
of whether they are supposed to be used or not. They are disabled (inactive)
initally, i.e. their time flows normally, using the wall-clock (true) time.

We then activate the looptime magic on demand for those tests & those scopes
that need it, and only when needed (i.e. when requested/configured/marked).

Previously, the event loops remained unpatched if looptime was not enabled
on a test.

Even for the lowest "function" scope, we cannot patch-and-activate it only once
at creation, since at the time of the event loop setup (creation),
we do not know which event loop will be the running loop of the test.
This affects which options to apply:

- One of the named scoped (session-package-module-class-function);
- ``None`` as the pseudo-scope for the running loop.

We only know this when we reach the test. We then combine the options, apply,
and activate the patched event loop.


"""
from __future__ import annotations

import asyncio
import warnings
from typing import Any

import _pytest.nodes
import pytest

from looptime import loops, patchers, timeproxies


# Critical implementation details: It MUST be sync! It CANNOT be async!
# It might seem that the easiest way to implement the ``looptime`` fixture is
# to make it ``async def`` and get the running loop inside. This does NOT work.
# When a function-scoped fixture is used in any higher-scoped test, it degrades
# the test from its scope to the function scope and breaks the test design.
# See an example at https://github.com/pytest-dev/pytest-asyncio/issues/1142.
# As such, the fixture MUST be synchronous (simple ``def``). As a result,
# the fixture CANNOT get a running loop, because there is no running loop.
# We take the running loop inside the time-measuring proxy at runtime.
@pytest.fixture
def looptime(request: pytest.FixtureRequest) -> timeproxies.LoopTimeProxy:
    """
    The event loop time for assertions.

    The fixture's numeric value is the loop time as a number of seconds
    since the "time zero", which is usuaully the creation time
    of the event loop, but can be adjusted by the ``start=…`` option.

    - It can be used in assertions & comparisons (``==``, ``<=``, etc).
    - It can also be used in simple math (additions, substractions, etc).
    - It can be converted to ``int()`` or ``float()``.

    It is an equivalent of a more wordy ``asyncio.get_running_loop().time()``.
    """
    return timeproxies.LoopTimeProxy()


def pytest_configure(config: Any) -> None:
    config.addinivalue_line('markers', "looptime: configure the fake fast-forwarding loop time.")


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("asyncio time contraction")
    group.addoption("--no-looptime", dest='looptime', action="store_const", const=False,
                    help="Force all (even marked) tests to the true loop time.")
    group.addoption("--looptime", dest='looptime', action="store_const", const=True,
                    help="Run unmarked tests with the fake loop time by default.")


EventLoopScopes = dict[str, list[str]]  # {fixture_name -> [outer_scopes, …, innermost_scope]}
EVENT_LOOP_SCOPES = pytest.StashKey[EventLoopScopes]()


@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(fixturedef: pytest.FixtureDef[Any], request: pytest.FixtureRequest) -> Any:
    # Setup as usual. We do the magic only afterwards, when we have the event loop created.
    result = yield

    # Only do the magic if in the area of our interest & only for fixtures making the event loops.
    if _should_patch(fixturedef, request) and isinstance(result, asyncio.BaseEventLoop):

        # Populate the helper mapper of names-to-scopes, as used in the test hook below.
        if EVENT_LOOP_SCOPES not in request.session.stash:
            request.session.stash[EVENT_LOOP_SCOPES] = {}
        event_loop_scopes: EventLoopScopes = request.session.stash[EVENT_LOOP_SCOPES]
        event_loop_scopes.setdefault(fixturedef.argname, []).append(fixturedef.scope)

        # Patch the event loop at creation — even if unused and not enabled. We cannot patch later
        # in the middle of the run: e.g. for a session-scoped loop used in a few tests out of many.
        # NB: For the lowest "function" scope, we still cannot decide which options to use, since
        # we do not know yet if it will be the running loop or not — so we cannot optimize here
        # in order to patch-and-configure only once; we must patch here & configure+activate later.
        result = patchers.patch_event_loop(result, _enabled=False)

    return result


@pytest.hookimpl(wrapper=True)
def pytest_fixture_post_finalizer(fixturedef: pytest.FixtureDef[Any], request: pytest.FixtureRequest) -> Any:
    # Cleanup the helper mapper of the fixture's names-to-scopes, as used in the test-running hook.
    # Internal consistency check: some cases should not happen, but we do not fail if they do.
    if EVENT_LOOP_SCOPES in request.session.stash:
        event_loop_scopes: EventLoopScopes = request.session.stash[EVENT_LOOP_SCOPES]
        if fixturedef.argname not in event_loop_scopes:
            warnings.warn(
                f"Fixture {fixturedef.argname!r} not found in the cache of scopes."
                f" Report as a bug, please add a reproducible snippet.",
                RuntimeWarning,
            )
        elif not event_loop_scopes[fixturedef.argname]:
            warnings.warn(
                f"Fixture {fixturedef.argname!r} has the empty cache of scopes."
                f" Report as a bug, please add a reproducible snippet.",
                RuntimeWarning,
            )
        elif event_loop_scopes[fixturedef.argname][-1] != fixturedef.scope:
            warnings.warn(
                f"Fixture {fixturedef.argname!r} has the broken cache of scopes:"
                f" {event_loop_scopes[fixturedef.argname]!r}, expecting {fixturedef.scope!r}"
                f" Report as a bug, please add a reproducible snippet.",
                RuntimeWarning,
            )
        else:
            event_loop_scopes[fixturedef.argname][-1:] = []

    # Go as usual.
    return (yield)


# This hook is the latest (deepest) possible entrypoint before diving into the test function itself,
# with all the fixtures executed earlier, so that their setup time is not taken into account.
# Here, we know the actual running loop (out of many) chosen by pytest-asyncio & its marks/configs.
# The alternatives to consider — the subtle differences are unclear to me for now:
# - pytest_pyfunc_call(pyfuncitem)
# - pytest_runtest_call(item)
# - pytest_runtest_setup(item), wrapped as @hookimpl(trylast=True)
@pytest.hookimpl(wrapper=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> Any:

    # Get the running loop from the pre-populated & pre-resolved fixtures (done in the setup stage).
    # This includes all the auto-used fixtures, but NOT the dynamic `getfixturevalue(…)` ones.
    # Alternatively, use the private `pyfuncitem._request.getfixturevalue(…)`, though this is hacky.
    funcargs: dict[str, Any] = pyfuncitem.funcargs
    if 'event_loop_policy' in funcargs:  # pytest-asyncio>=1.0.0
        # This can be ANY event loop of ANY declared scope of pytest-asyncio.
        policy: asyncio.AbstractEventLoopPolicy = funcargs['event_loop_policy']
        running_loop = policy.get_event_loop()
    elif 'event_loop' in funcargs:  # pytest-asyncio<1.0.0
        # The hook itself has NO "running" loop — because it is sync, not async.
        running_loop = funcargs['event_loop']
    else: # not pytest-asyncio? not our business!
        return (yield)

    # TODO: take the global flags into account? do not activate with --no-looptime!
    #           but do activate with --looptime or looptime=true.
    #       in this code, we activate regardless of global options — not good.
    # For ALL involved fixtures (incl. hidden & auto-used), apply or re-apply their scoped options.
    # The scopes of fixtures are remembered in the session stash when the fixtures are set up.
    # (There is `pyfuncitem._fixtureinfo.name2fixturedefs`, but it holds no FixtureDefs or scopes.)
    # NB: function-scoped event loops will be set up twice; this is fine — to make the code generic:
    # - First, in the fixture hook — with no options, when patched at creation.
    # - Second, here, in the test hook – with specific options.
    # This might be the 2nd setup of a function-scoped fixture, now with specific options.
    # For higher-scoped fixtures, this step can be repeated for every test again and again.
    scoped_options: dict[str | None, dict[str, Any]] = _get_options(pyfuncitem)
    event_loop_fixture_scopes: EventLoopScopes = pyfuncitem.session.stash.get(EVENT_LOOP_SCOPES, {})
    for fixture_name, fixture_value in funcargs.items():
        if isinstance(fixture_value, loops.LoopTimeEventLoop):
            if fixture_name in event_loop_fixture_scopes:
                scope: str = event_loop_fixture_scopes[fixture_name][-1]
                options: dict[str, Any] = {}
                if scope in scoped_options:
                    options.update(scoped_options[scope])
                if None in scoped_options and fixture_value is running_loop:
                    options.update(scoped_options[None])
                fixture_value.setup_looptime(**options)

    # The event loop is not patched? We are doomed to fail, so let it run somehow on its own.
    # This might happen if the custom event loop policy was set not by pytest-asyncio.
    if not isinstance(running_loop, loops.LoopTimeEventLoop):
        return (yield)

    # If not enabled/enforced for this test, even if the event loop is patched, let it run as usual.
    enabled = None in scoped_options
    if not enabled:
        return (yield)

    # Finally, if enabled/enforced, activate the magic and run the test in the compacted time mode.
    # We only activate the running loop for the test, not the other event loops used in fixtures.
    running_loop.setup_looptime(**scoped_options[None])
    with running_loop.looptime_enabled():
        return (yield)


def _should_patch(fixturedef: pytest.FixtureDef[Any], request: pytest.FixtureRequest) -> bool:
    """
    Check if the fixture should be patched (in case it is an event loop).

    Only patch the implicit (hidden) event loops and their user-side overrides.
    They are declared as internal with underscored names, but nevertheless.
    Example implicit names: ``_session_event_loop`` … ``_function_event_loop``.

    We do not intercept arbitrary fixtures or event loops of unknown plugins.
    Custom event loops can be patched explicitly if needed.
    """
    # pytest-asyncio<1.0.0 exposed the specific fixture; deprecated since >=0.23.0, removed >=1.0.0.
    if fixturedef.argname == "event_loop":
        return True

    # pytest-asyncio>=1.0.0 exposes several event loops, one per scope, all hidden in the module.
    asyncio_plugin = request.config.pluginmanager.getplugin("asyncio")  # a module object
    asyncio_names: set[str] = {
        name for name in dir(asyncio_plugin) if _is_fixture(getattr(asyncio_plugin, name))
    }
    asyncio_module = asyncio_plugin.__name__
    fixture_module = fixturedef.func.__module__
    should_patch = fixture_module == asyncio_module or fixturedef.argname in asyncio_names
    return should_patch


def _is_fixture(obj: Any) -> bool:
    # Any of these internal names can be moved or renamed any time. Do our best to guess.
    import _pytest.fixtures

    try:
        if isinstance(obj, _pytest.fixtures.FixtureFunctionDefinition):
            return True
    except AttributeError:
        pass
    try:
        if isinstance(obj, _pytest.fixtures.FixtureFunctionMarker):
            return True
    except AttributeError:
        pass
    return False


def _get_options(node: _pytest.nodes.Node) -> dict[str | None, dict[str, Any]]:
    """
    Combine all the declared looptime options, grouped by loop scope.

    The loop scope ``None`` is used when the loop scope is not defined,
    and this means the running event loop — regardless of which scope it is
    (typically equal to pytest-asyncio's ``loop_scope`` of the test).
    """
    markers = list(node.iter_markers('looptime'))
    enabled: dict[str | None, bool] = {}
    options: dict[str | None, dict[str, Any]] = {}
    for marker in reversed(markers):
        # Accumulate the scope-related options separately, override with the closest markers.
        # The loop scope None means the running loop, which can vary, and is interpreted separately.
        loop_scope: str | None = marker.kwargs.pop('loop_scope', None)
        if loop_scope not in options:
            options[loop_scope] = {}
        options[loop_scope].update(marker.kwargs)

        # Positional args enable/disable that loop scope, but do not reset the accumulated options.
        if marker.args:
            enabled[loop_scope] = bool(marker.args[0])

    # True means implicitly on; False means explicitly off; None means "only if marked".
    flag: bool | None = node.config.getoption('looptime')

    # Drop the options for scopes that are disabled with the markers, as if there are no markers.
    # Ensure the scopes that are not marked if there is a global flag to auto-enable looptime.
    scopes = ['session', 'package', 'module', 'class', 'function', None]
    options = {
        scope: options.get(scope, {})
        for scope in scopes
        if enabled.get(scope, (scope in options or flag is True) and flag is not False)
    }

    return options
