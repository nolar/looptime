import looptime


def test_time_proxy_math():
    proxy = looptime.LoopTimeProxy(looptime.new_event_loop(start=123.456))

    assert str(proxy) == '123.456'
    assert int(proxy) == 123
    assert float(proxy) == 123.456

    assert proxy == 123.456
    assert not proxy == 456.123
    assert proxy != 456.123
    assert not proxy != 123.456

    assert proxy > 122
    assert proxy < 124
    assert proxy >= 122
    assert proxy <= 124

    assert not proxy < 122
    assert not proxy > 124
    assert not proxy <= 122
    assert not proxy >= 124

    assert not proxy > 123.456
    assert not proxy < 123.456
    assert proxy >= 123.456
    assert proxy <= 123.456

    assert proxy + 1.2 == 124.656
    assert proxy - 1.2 == 122.256
    assert proxy * 1.2 == 148.1472

    # The following values cause floating point precision errors if not adjusted:
    #   123.456 / 1.2 => 102.88000000000001
    #   123.456 % 1.2 => 1.0560000000000076
    # We also test for floating point resolution here:
    assert proxy / 1.2 == 102.88
    assert proxy // 1.2 == 102.0
    assert proxy % 1.2 == 1.056

    assert round(proxy ** 1.2, 6) == 323.455576  # approximately


def test_resolution_ignores_extra_precision():
    proxy = looptime.LoopTimeProxy(looptime.new_event_loop(start=123.456789), resolution=.001)
    assert str(proxy) == '123.457'
    assert int(proxy) == 123
    assert float(proxy) == 123.457
    assert proxy == 123.457
    assert proxy == 123.457111
    assert proxy == 123.456999
    # assume that other operations use the same rounding logic.


def test_loop_attachement():
    loop1 = looptime.new_event_loop(start=123.456)
    loop2 = looptime.new_event_loop(start=456.123)
    proxy = looptime.LoopTimeProxy(loop1)

    assert proxy == 123.456
    assert proxy @ loop1 == 123.456
    assert proxy @ loop2 == 456.123
