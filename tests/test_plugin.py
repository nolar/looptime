pytest_plugins = ["pytester"]


def test_cli_default_mode(testdir):
    testdir.makepyfile("""
        import asyncio
        import looptime
        import pytest

        @pytest.mark.asyncio
        async def test_normal():
            event_loop = asyncio.get_running_loop()
            assert isinstance(event_loop, looptime.LoopTimeEventLoop)
            assert not event_loop.looptime_on

        @pytest.mark.asyncio
        @pytest.mark.looptime
        async def test_marked():
            event_loop = asyncio.get_running_loop()
            assert isinstance(event_loop, looptime.LoopTimeEventLoop)
            assert event_loop.looptime_on
            assert event_loop.time() == 0

        @pytest.mark.asyncio
        @pytest.mark.looptime(start=123)
        async def test_configured():
            event_loop = asyncio.get_running_loop()
            assert isinstance(event_loop, looptime.LoopTimeEventLoop)
            assert event_loop.looptime_on
            assert event_loop.time() == 123

        @pytest.mark.asyncio
        @pytest.mark.looptime(False)
        async def test_disabled():
            event_loop = asyncio.get_running_loop()
            assert isinstance(event_loop, looptime.LoopTimeEventLoop)
            assert not event_loop.looptime_on
    """)
    result = testdir.runpytest()
    result.assert_outcomes(passed=4)


def test_cli_option_enabled(testdir):
    testdir.makepyfile("""
        import asyncio
        import looptime
        import pytest

        @pytest.mark.asyncio
        async def test_normal():
            event_loop = asyncio.get_running_loop()
            assert isinstance(event_loop, looptime.LoopTimeEventLoop)
            assert event_loop.looptime_on
            assert event_loop.time() == 0

        @pytest.mark.asyncio
        @pytest.mark.looptime
        async def test_marked():
            event_loop = asyncio.get_running_loop()
            assert isinstance(event_loop, looptime.LoopTimeEventLoop)
            assert event_loop.looptime_on
            assert event_loop.time() == 0

        @pytest.mark.asyncio
        @pytest.mark.looptime(start=123)
        async def test_configured():
            event_loop = asyncio.get_running_loop()
            assert isinstance(event_loop, looptime.LoopTimeEventLoop)
            assert event_loop.looptime_on
            assert event_loop.time() == 123

        @pytest.mark.asyncio
        @pytest.mark.looptime(False)
        async def test_disabled():
            event_loop = asyncio.get_running_loop()
            assert isinstance(event_loop, looptime.LoopTimeEventLoop)
            assert not event_loop.looptime_on
    """)
    result = testdir.runpytest("--looptime")
    result.assert_outcomes(passed=4)


def test_cli_option_disabled(testdir):
    testdir.makepyfile("""
        import asyncio
        import looptime
        import pytest

        @pytest.mark.asyncio
        async def test_normal():
            event_loop = asyncio.get_running_loop()
            assert isinstance(event_loop, looptime.LoopTimeEventLoop)
            assert not event_loop.looptime_on

        @pytest.mark.asyncio
        @pytest.mark.looptime
        async def test_marked():
            event_loop = asyncio.get_running_loop()
            assert isinstance(event_loop, looptime.LoopTimeEventLoop)
            assert not event_loop.looptime_on

        @pytest.mark.asyncio
        @pytest.mark.looptime(start=123)
        async def test_configured():
            event_loop = asyncio.get_running_loop()
            assert isinstance(event_loop, looptime.LoopTimeEventLoop)
            assert not event_loop.looptime_on

        @pytest.mark.asyncio
        @pytest.mark.looptime(False)
        async def test_disabled():
            event_loop = asyncio.get_running_loop()
            assert isinstance(event_loop, looptime.LoopTimeEventLoop)
            assert not event_loop.looptime_on
    """)
    result = testdir.runpytest("--no-looptime")
    result.assert_outcomes(passed=4)


def test_fixture_chronometer(testdir):
    testdir.makepyfile("""
        import time
        import pytest

        @pytest.mark.asyncio
        async def test_me(chronometer):
            with chronometer:
                time.sleep(0.1)
            assert 0.1 <= chronometer.seconds < 0.2
    """)
    result = testdir.runpytest()
    result.assert_outcomes(passed=1)


def test_fixture_timeloop(testdir):
    testdir.makepyfile("""
        import time
        import pytest

        @pytest.mark.asyncio
        @pytest.mark.looptime(start=123)
        async def test_me(looptime):
            assert looptime == 123
    """)
    result = testdir.runpytest()
    result.assert_outcomes(passed=1)
