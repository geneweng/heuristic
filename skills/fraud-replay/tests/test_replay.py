from replay import run


def test_stub_returns_ok():
    assert run()["status"] == "ok"
