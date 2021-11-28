import asyncio
import socket
import threading
import time

import pytest

import looptime


def test_no_idle_configured(chronometer, looptime_loop):
    looptime_loop.setup_looptime(end=None, idle_timeout=None, idle_step=None)

    rsock, wsock = socket.socketpair()

    def sender():
        time.sleep(0.1)
        wsock.send(b'z')

    async def f():
        reader, writer = await asyncio.open_connection(sock=rsock)
        try:
            await reader.read(1)
        finally:
            writer.close()
            wsock.close()

    thread = threading.Thread(target=sender)
    thread.start()

    with chronometer:
        looptime_loop.run_until_complete(f())
    assert looptime_loop.time() == 0
    assert 0.1 <= chronometer.seconds < 0.12

    thread.join()


def test_stepping_with_no_limit(chronometer, looptime_loop):
    looptime_loop.setup_looptime(end=None, idle_timeout=None, idle_step=0.01)

    rsock, wsock = socket.socketpair()

    def sender():
        time.sleep(0.1)
        wsock.send(b'z')

    async def f():
        reader, writer = await asyncio.open_connection(sock=rsock)
        try:
            await reader.read(1)
        finally:
            writer.close()
            wsock.close()

    thread = threading.Thread(target=sender)
    thread.start()

    with chronometer:
        looptime_loop.run_until_complete(f())

    # TODO: FIXME: Sometimes, the code overhead eats 1-2 steps (if they are small).
    assert looptime_loop.time() in [0.1, 0.09]
    assert 0.1 <= chronometer.seconds < 0.12

    thread.join()


def test_end_of_idle(chronometer, looptime_loop):
    looptime_loop.setup_looptime(end=None, idle_timeout=1, idle_step=0.1)

    async def f():
        rsock, wsock = socket.socketpair()
        reader, writer = await asyncio.open_connection(sock=rsock)
        try:
            await reader.read(1)
        finally:
            writer.close()
            wsock.close()

    with chronometer:
        with pytest.raises(looptime.IdleTimeoutError):
            looptime_loop.run_until_complete(f())
    assert looptime_loop.time() == 1
    assert 1.0 <= chronometer.seconds < 1.02


def test_end_of_time(chronometer, looptime_loop):
    looptime_loop.setup_looptime(end=1, idle_timeout=None, idle_step=0.1)

    async def f():
        rsock, wsock = socket.socketpair()
        reader, writer = await asyncio.open_connection(sock=rsock)
        try:
            await reader.read(1)
        finally:
            writer.close()
            wsock.close()

    with chronometer:
        with pytest.raises(looptime.LoopTimeoutError):
            looptime_loop.run_until_complete(f())
    assert looptime_loop.time() == 1
    assert 1.0 <= chronometer.seconds < 1.01
