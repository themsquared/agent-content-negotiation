"""The legacy origin. Serves HTML and nothing else.

The premise of the demo is that this service cannot be changed: it is the
docs site, the knowledge base, the product pages. It has no idea agents
exist and it is never going to grow an `index.md`.
"""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGES = {
    "/": ("Runbook index", """
<h1>Runbook index</h1>
<p>Operational runbooks for the <strong>payments</strong> platform.</p>
<ul>
  <li><a href="/runbooks/rotate-keys">Rotate provider keys</a></li>
  <li><a href="/runbooks/drain-node">Drain a node</a></li>
</ul>
"""),
    "/runbooks/rotate-keys": ("Rotate provider keys", """
<h1>Rotate provider keys</h1>
<p>Rotate the upstream provider key <em>without</em> restarting the gateway.</p>
<h2>Steps</h2>
<ol>
  <li>Mint the replacement key in the provider console.</li>
  <li>Write it to the <code>provider-key</code> secret.</li>
  <li>Send <code>SIGHUP</code> to the gateway.</li>
</ol>
<h2>Verification</h2>
<p>Confirm the gateway reports the new key fingerprint:</p>
<pre>curl -s localhost:15000/api/keys | jq .fingerprint</pre>
<p>See also the <a href="/runbooks/drain-node">node drain runbook</a>.</p>
"""),
    "/runbooks/drain-node": ("Drain a node", """
<h1>Drain a node</h1>
<p>Move agent workloads off a node before maintenance.</p>
<ol>
  <li>Cordon the node.</li>
  <li>Wait for in-flight agent sessions to settle.</li>
  <li>Drain, ignoring daemonsets.</li>
</ol>
"""),
}

SHELL = """<!doctype html>
<html><head><title>{title}</title>
<link rel="stylesheet" href="/static/site.css">
<script src="/static/analytics.js"></script>
<nav class="site-chrome"><a href="/">home</a> | <a href="/search">search</a></nav>
</head><body><div class="wrapper">{body}</div>
<footer class="site-chrome">(c) 2026 example platform team</footer>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path not in PAGES:
            self._send(404, "text/html; charset=utf-8",
                       b"<!doctype html><html><body><h1>404</h1></body></html>")
            return
        title, body = PAGES[path]
        html = SHELL.format(title=title, body=body).encode()
        self._send(200, "text/html; charset=utf-8", html)

    def _send(self, status, ctype, payload):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        print("origin %s - %s" % (self.address_string(), fmt % args), flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("ORIGIN_PORT", "8080"))
    print("origin listening on %d (HTML only)" % port, flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
