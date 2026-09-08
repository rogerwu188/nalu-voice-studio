"""Read bounded public HTTPS source text without credentials or internal access."""

import http.client
import ipaddress
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

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


class SourceLinksParser(HTMLParser):
    """Keep document order for chapter discovery; never execute page instructions."""

    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.links = []
        self.title_parts = []
        self.in_title = False
        self.anchor = None
        self.seen = set()

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        if tag == "a":
            values = dict(attrs)
            href = values.get("href")
            self.anchor = [href, [], values.get("rel") or ""] if href else None

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if self.anchor:
            self.anchor[1].append(data)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag != "a" or self.anchor is None:
            return
        href, parts, rel = self.anchor
        self.anchor = None
        try:
            url = urldefrag(urljoin(self.base_url, href))[0]
            parsed = urlsplit(url)
            valid = (parsed.scheme == "https" and parsed.hostname
                     and not parsed.username and not parsed.password
                     and parsed.port in {None, 443} and len(url) <= 4000)
        except ValueError:
            return
        if valid and url not in self.seen:
            self.seen.add(url)
            self.links.append({"url": url, "title": "".join(parts).strip(), "rel": rel})


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
    return _read_public_source(url, complete=False)


def read_public_chapter(url):
    """Read a complete bounded text page plus candidate chapter links.

    Oversized pages fail explicitly; never silently label an excerpt as a chapter.
    Every fetched page and redirect still passes the pinned-IP public target check.
    """
    return _read_public_source(url, complete=True)


def _read_public_source(url, *, complete):
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
            metadata = SourceLinksParser(url)
            if content_type == "text/html":
                if complete:
                    metadata.feed(text)
                parser = SourceTextParser()
                parser.feed(text)
                text = "\n".join(parser.parts)
            if not text.strip():
                raise SourceReadError("source has no readable text")
            if complete:
                return {"requested_url": original, "url": url, "text": text,
                        "title": "".join(metadata.title_parts).strip(),
                        "links": metadata.links, "truncated": False,
                        "scope": "complete_text_page"}
            return {"requested_url": original, "url": url, "text": text[:24000],
                    "truncated": len(text) > 24000, "scope": "single_page_excerpt"}
        except http.client.HTTPException as exc:
            raise SourceReadError("source returned an invalid HTTP response") from exc
        finally:
            connection.close()
    raise SourceReadError("too many source redirects")
