from reflector import run


def test_stub_returns_noop():
    assert run()["status"] == "noop"
