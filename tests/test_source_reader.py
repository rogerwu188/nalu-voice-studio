import socket
import ssl
from email.message import Message

import pytest
from fastapi.testclient import TestClient
from nalu_runtime import source_reader
from nalu_runtime.app import create_app


def test_chapter_links_keep_directory_order_and_reject_unsafe_targets():
    parser = source_reader.SourceLinksParser("https://example.com/book/index.html")
    parser.feed('''<title>故事目录</title>
        <a href="2.html">第二章 <b>归来</b></a>
        <a href="1.html#text">第一章</a><a href="1.html">重复</a>
        <a href="javascript:alert(1)">脚本</a><a href="https://u:p@example.com/a">凭证</a>
        <a href="3.html" rel="next">下一章</a>''')
    assert "".join(parser.title_parts) == "故事目录"
    assert [item["url"] for item in parser.links] == [
        "https://example.com/book/2.html", "https://example.com/book/1.html",
        "https://example.com/book/3.html",
    ]
    assert parser.links[0]["title"] == "第二章 归来"
    assert parser.links[-1]["rel"] == "next"


def fake_source_transport(monkeypatch, body):
    class Response:
        status = 200
        headers = Message()
        headers["Content-Type"] = "text/html; charset=utf-8"

        def getheader(self, name, default=None):
            return self.headers.get(name, default)

        def read(self, limit):
            return body[:limit]

    class Connection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    class Context:
        def wrap_socket(self, raw, **kwargs):
            return raw

    monkeypatch.setattr(source_reader.http.client, "HTTPSConnection", Connection)
    monkeypatch.setattr(source_reader.socket, "create_connection", lambda *a, **k: object())
    monkeypatch.setattr(source_reader, "source_tls_context", Context)
    monkeypatch.setattr(source_reader.socket, "getaddrinfo",
                        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])


def test_chapter_read_does_not_silently_truncate_at_excerpt_limit(monkeypatch):
    story = "海边的故事。" * 5000
    fake_source_transport(monkeypatch, f"<title>第一章</title><p>{story}</p>".encode())
    page = source_reader.read_public_chapter("https://example.com/ch1")
    assert story in page["text"] and not page["truncated"]
    assert page["scope"] == "complete_text_page"
    excerpt = source_reader.read_public_source("https://example.com/ch1")
    assert len(excerpt["text"]) == 24000 and excerpt["truncated"]


def test_oversize_chapter_is_error_not_incomplete_success(monkeypatch):
    fake_source_transport(monkeypatch, b"x" * 1_000_001)
    with pytest.raises(source_reader.SourceReadError, match="reading limit"):
        source_reader.read_public_chapter("https://example.com/ch1")


def test_chapter_body_excludes_navigation_ads_and_footer(monkeypatch):
    html = '''<title>网站名 第一章</title><header>登录注册</header>
    <article>推荐阅读<div id="content"><p>爷爷回到故乡。</p><br/>
    <p>他看见了那棵树。</p><div class="ads">立即购买</div>
    <span hidden>隐藏文字</span><script>广告代码</script>
    <nav><a href="2.html">下一章</a></nav></div></article><footer>网站声明</footer>'''
    fake_source_transport(monkeypatch, html.encode())
    result = source_reader.read_public_chapter("https://example.com/1.html")
    assert result["text"] == "爷爷回到故乡。\n他看见了那棵树。"
    assert result["body_extraction"] == "reading_container"
    assert result["links"][0]["url"] == "https://example.com/2.html"
    assert result["title"] == "网站名 第一章"


def test_unknown_page_structure_is_explicitly_unverified(monkeypatch):
    fake_source_transport(monkeypatch, "<div>无法判断是目录还是正文</div>".encode())
    result = source_reader.read_public_chapter("https://example.com/page")
    assert result["body_extraction"] == "page_text_unverified"
    assert result["text"] == "无法判断是目录还是正文"


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
