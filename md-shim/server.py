"""Markdown shim. Fetches the origin's HTML and returns text/markdown.

Deliberately small and stdlib-only. The interesting part of this demo is
where the negotiation decision is made, not the quality of the HTML-to-
markdown conversion, so the converter handles exactly the tags the origin
emits and says so.
"""
import os
import urllib.request
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ORIGIN = os.environ.get("ORIGIN_URL", "http://origin:8080")

# Site chrome an agent has no use for. Dropping it is the other half of the
# value: the markdown is not just a reformat, it is a smaller payload.
#
# These two sets have to stay separate. DROP_TAGS are containers, so they
# open a skip region that the matching close tag ends. DROP_VOID are void
# elements with no close tag at all -- putting `link` in DROP_TAGS opens a
# skip region that never closes and silently eats the entire document.
DROP_TAGS = {"script", "style", "nav", "footer", "head", "title"}
DROP_VOID = {"link", "meta", "base", "img", "br", "hr", "input", "source"}


class ToMarkdown(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out = []
        self.skip_depth = 0
        self.list_stack = []
        self.item_index = 0
        self.href = None
        self.in_pre = False
        self.pending = []

    # -- helpers ---------------------------------------------------------
    def _flush(self, prefix="", suffix=""):
        text = "".join(self.pending)
        self.pending = []
        # Boundary spaces from adjacent nodes can double up. Collapse them,
        # then trim the block edges.
        while "  " in text:
            text = text.replace("  ", " ")
        text = text.strip()
        if text:
            self.out.append(prefix + text + suffix)

    def handle_starttag(self, tag, attrs):
        if tag in DROP_VOID:
            return
        if tag in DROP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        a = dict(attrs)
        if tag in ("h1", "h2", "h3"):
            self._flush()
        elif tag == "p":
            self._flush()
        elif tag in ("ul", "ol"):
            self._flush()
            self.list_stack.append(tag)
            self.item_index = 0
        elif tag == "li":
            self._flush()
        elif tag == "a":
            self.href = a.get("href")
        elif tag == "pre":
            self._flush()
            self.in_pre = True
        elif tag in ("strong", "b"):
            self.pending.append("**")
        elif tag in ("em", "i"):
            self.pending.append("*")
        elif tag == "code" and not self.in_pre:
            self.pending.append("`")

    def handle_endtag(self, tag):
        if tag in DROP_VOID:
            return
        if tag in DROP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag == "h1":
            self._flush("# ")
        elif tag == "h2":
            self._flush("## ")
        elif tag == "h3":
            self._flush("### ")
        elif tag == "p":
            self._flush()
        elif tag == "li":
            if self.list_stack and self.list_stack[-1] == "ol":
                self.item_index += 1
                self._flush("%d. " % self.item_index)
            else:
                self._flush("- ")
        elif tag in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
            self.item_index = 0
        elif tag == "pre":
            text = "".join(self.pending).strip()
            self.pending = []
            if text:
                self.out.append("```\n%s\n```" % text)
            self.in_pre = False
        elif tag in ("strong", "b"):
            self.pending.append("**")
        elif tag in ("em", "i"):
            self.pending.append("*")
        elif tag == "code" and not self.in_pre:
            self.pending.append("`")
        elif tag == "a":
            self.href = None

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.in_pre:
            self.pending.append(data)
            return
        # Collapse runs of whitespace, but KEEP one space at each boundary if
        # the source had any. Stripping it turns "the <em>x</em> secret" into
        # "the*x*secret", which is not just ugly -- it is different markdown.
        lead = " " if data[:1].isspace() else ""
        trail = " " if data[-1:].isspace() else ""
        text = " ".join(data.split())
        if not text:
            # Whitespace-only node between two inline elements still separates
            # them, so emit a single space rather than nothing.
            if (lead or trail) and self.pending:
                self.pending.append(" ")
            return
        if self.href:
            self.pending.append("%s[%s](%s)%s" % (lead, text, self.href, trail))
            self.href = None
        else:
            self.pending.append(lead + text + trail)

    def result(self):
        self._flush()
        return "\n\n".join(self.out) + "\n"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        url = ORIGIN.rstrip("/") + self.path
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                html = r.read().decode("utf-8", "replace")
                status = r.status
        except urllib.error.HTTPError as e:
            status, html = e.code, e.read().decode("utf-8", "replace")
        except Exception as e:
            self._send(502, "text/plain; charset=utf-8",
                       ("shim could not reach origin: %s\n" % e).encode())
            return

        p = ToMarkdown()
        p.feed(html)
        body = p.result().encode()
        self._send(status, "text/markdown; charset=utf-8", body)

    def _send(self, status, ctype, payload):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        # The shim asserts what it varied on too, so the header is correct
        # even if someone puts a cache in front of the shim directly.
        self.send_header("Vary", "Accept")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        print("md-shim %s - %s" % (self.address_string(), fmt % args), flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("SHIM_PORT", "8081"))
    print("md-shim listening on %d (origin=%s)" % (port, ORIGIN), flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
