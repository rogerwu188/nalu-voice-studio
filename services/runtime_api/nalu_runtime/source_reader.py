"""Read bounded public HTTPS source text without credentials or internal access."""

import http.client
import ipaddress
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import certifi


class SourceReadError(ValueError):
    pass


def source_tls_context():
    # Bundle roots explicitly: a CI interpreter's compiled CA path need not
    # exist on the recipient Mac. Never disable certificate/hostname checks.
    return ssl.create_default_context(cafile=certifi.where())


def source_failure_code(error):
    if isinstance(error, ssl.SSLCertVerificationError):
        return "source_tls_verification_failed"
    if isinstance(error, socket.gaierror):
        return "source_dns_failed"
    if isinstance(error, TimeoutError):
        return "source_timeout"
    return "source_unavailable"


class SourceTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.suppressed = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "noscript", "svg"}:
            self.suppressed.append(tag)

    def handle_endtag(self, tag):
        if self.suppressed and self.suppressed[-1] == tag:
            self.suppressed.pop()

    def handle_data(self, data):
        if not self.suppressed and data.strip():
            self.parts.append(data.strip())


def public_target(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in {None, 443} or len(url) > 4000):
        raise SourceReadError("only public HTTPS source URLs are supported")
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    ips = [entry[4][0] for entry in addresses]
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise SourceReadError("private or reserved source address is not allowed")
    return parsed, ips[0]


def read_public_source(url):
    original = url
    for _ in range(4):
        parsed, ip = public_target(url)
        connection = http.client.HTTPSConnection(parsed.hostname, timeout=12)
        try:
            # Pin the validated IP, keeping original SNI/certificate/Host checks.
            # A second DNS resolution must not enable a rebinding to localhost.
            raw_socket = socket.create_connection((ip, 443), timeout=12)
            try:
                connection.sock = source_tls_context().wrap_socket(
                    raw_socket, server_hostname=parsed.hostname
                )
            except Exception:
                raw_socket.close()
                raise
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            connection.request("GET", path, headers={
                "Accept": "text/html,text/plain", "User-Agent": "Nalu-SourceReader/1.0",
                "Accept-Encoding": "identity",
            })
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise SourceReadError("source redirect has no location")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise SourceReadError("source could not be read")
            content_type = response.getheader("Content-Type", "").split(";")[0].strip()
            if content_type not in {"text/html", "text/plain"}:
                raise SourceReadError("source is not a supported text page")
            body = response.read(1_000_001)
            if len(body) > 1_000_000:
                raise SourceReadError("source page exceeds reading limit")
            text = body.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            if content_type == "text/html":
                parser = SourceTextParser()
                parser.feed(text)
                text = "\n".join(parser.parts)
            if not text.strip():
                raise SourceReadError("source has no readable text")
            return {"requested_url": original, "url": url, "text": text[:24000],
                    "truncated": len(text) > 24000, "scope": "single_page_excerpt"}
        except http.client.HTTPException as exc:
            raise SourceReadError("source returned an invalid HTTP response") from exc
        finally:
            connection.close()
    raise SourceReadError("too many source redirects")
