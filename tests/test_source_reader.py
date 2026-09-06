import socket
import ssl

import pytest
from fastapi.testclient import TestClient
from nalu_runtime import source_reader
from nalu_runtime.app import create_app


def test_source_tls_keeps_verification_with_bundled_trust_roots():
    context = source_reader.source_tls_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.cert_store_stats()["x509_ca"] > 0
    assert source_reader.source_failure_code(ssl.SSLCertVerificationError()) == "source_tls_verification_failed"
    assert source_reader.source_failure_code(socket.gaierror()) == "source_dns_failed"


def test_public_target_blocks_internal_dns_and_credentials(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    for url in ["https://example.com", "https://user:pass@example.com", "http://example.com", "https://example.com:8443"]:
        with pytest.raises(source_reader.SourceReadError):
            source_reader.public_target(url)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    assert source_reader.public_target("https://example.com/chapter")[1] == "93.184.216.34"


def test_html_extraction_keeps_story_not_scripts():
    parser = source_reader.SourceTextParser()
    parser.feed("<nav>购买</nav><h1>童年</h1><p>外婆牵着我的手。</p><script>secret()</script><style>body{}</style>")
    assert parser.parts == ["童年", "外婆牵着我的手。"]


def test_source_endpoint_is_project_bound_and_handles_failure(tmp_path, monkeypatch):
    calls = []
    def read(url):
        calls.append(url)
        if url.endswith("bad"):
            raise source_reader.SourceReadError("fixture failure")
        return {"url": url, "text": "海边童年", "truncated": False, "scope": "single_page_excerpt"}
    monkeypatch.setattr("nalu_runtime.app.read_public_source", read)
    with TestClient(create_app(tmp_path / "db", tmp_path / "data")) as client:
        assert client.get("/v1/projects/missing/source-text", params={"url": "https://example.com"}).status_code == 404
        assert calls == []
        project = client.post("/v1/projects", json={"title": "来源"}).json()["id"]
        path = f"/v1/projects/{project}/source-text"
        assert client.get(path, params={"url": "https://example.com"}).json()["text"] == "海边童年"
        assert client.get(path, params={"url": "https://example.com/bad"}).status_code == 422


@pytest.mark.parametrize("error,code", [
    (ssl.SSLCertVerificationError("private diagnostic"), "source_tls_verification_failed"),
    (socket.gaierror("private diagnostic"), "source_dns_failed"),
    (TimeoutError("private diagnostic"), "source_timeout"),
])
def test_source_failure_is_diagnostic_without_leaking_details(tmp_path, monkeypatch, error, code):
    def fail(_):
        raise error
    monkeypatch.setattr("nalu_runtime.app.read_public_source", fail)
    with TestClient(create_app(tmp_path / "db", tmp_path / "data")) as client:
        project = client.post("/v1/projects", json={"title": "原有故事"}).json()["id"]
        before = client.get(f"/v1/projects/{project}").json()
        result = client.get(f"/v1/projects/{project}/source-text",
                            params={"url": "https://example.com"})
        assert result.status_code == 422
        assert result.json()["detail"]["code"] == code
        assert "private diagnostic" not in result.text
        assert client.get(f"/v1/projects/{project}").json() == before
