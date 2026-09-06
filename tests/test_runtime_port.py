import pytest
from nalu_runtime.__main__ import main, runtime_port


def test_runtime_port_defaults_to_existing_port(monkeypatch):
    monkeypatch.delenv("NALU_RUNTIME_PORT", raising=False)
    assert runtime_port() == 8765


@pytest.mark.parametrize("raw", ["0", "80", "65536", "", "08765", "+18765", " 18765", "１８７６５"])
def test_runtime_rejects_invalid_ports(monkeypatch, raw):
    monkeypatch.setenv("NALU_RUNTIME_PORT", raw)
    with pytest.raises(ValueError):
        runtime_port()


def test_alternate_port_remains_loopback_only(monkeypatch):
    monkeypatch.setenv("NALU_RUNTIME_PORT", "18766")
    calls = []
    monkeypatch.setattr("nalu_runtime.__main__.uvicorn.run", lambda *a, **kw: calls.append(kw))
    main()
    assert calls == [{"host": "127.0.0.1", "port": 18766, "reload": False}]
