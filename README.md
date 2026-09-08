# agent-content-negotiation

**Serve markdown to agents at the gateway, without touching the origin.**

Agents parse HTML badly and expensively. The usual answer is to make the site
emit markdown — add an `index.md` per page, publish an `llms.txt`, change the
build. That works if you own the site. It does not work for the docs site you
inherited, the vendor knowledge base, or the internal wiki nobody will
redeploy this quarter.

This demo puts the decision in the gateway instead. One origin that serves
HTML and only HTML, one 200-line shim, and a route that picks between them on
the `Accept` header. The origin is not modified and does not know any of this
happened.

It also shows the two things that go wrong, because both of them are the
reason a naive version of this quietly fails.

## Value proposition

Make an origin you do not control agent-readable at the traffic layer, and
find out what your agents are actually asking for while you do it.

## Quickstart

Requires Docker with Compose v2. Nothing else — the shim is Python stdlib.

```bash
docker compose up -d --build
./scripts/demo.sh
```

Five scenarios against one URL, changing only `Accept`. Expected result:

```
assertions: 15 passed, 0 failed
```

Tear down with `docker compose down`.

## What you get

Same page, same origin, two representations:

```bash
curl -s -H 'Accept: text/html'     http://localhost:3000/runbooks/rotate-keys
curl -s -H 'Accept: text/markdown' http://localhost:3000/runbooks/rotate-keys
```

The markdown variant, verbatim from the run above:

~~~~markdown
# Rotate provider keys

Rotate the upstream provider key *without* restarting the gateway.

## Steps

1. Mint the replacement key in the provider console.

2. Write it to the `provider-key` secret.

3. Send `SIGHUP` to the gateway.

## Verification

Confirm the gateway reports the new key fingerprint:

```
curl -s localhost:15000/api/keys | jq .fingerprint
```

See also the [node drain runbook](/runbooks/drain-node).
~~~~

894 bytes of HTML became 420 bytes of markdown, and the nav, footer,
stylesheet link and analytics script are gone. That gap is the part that
compounds: it is per page, per fetch, per agent, and it is all context window.

Response headers tell you which variant a client got:

```
x-content-negotiated-by: agentgateway
x-served-variant: markdown
vary: Accept
```

## The two things that go wrong

**1. `Accept: */*` gets HTML.** That is curl's default and it is what a
surprising number of agent HTTP clients send. `*/*` does not mention markdown,
so the markdown route does not match and the agent gets the HTML site — no
error, no warning, just a parsing problem it will blame on your docs.
Scenario 3 in `scripts/demo.sh` demonstrates it. The `x-served-variant`
header exists so you can see this in your own access logs before an agent
author reports it as a bug.

**2. This is a routing match, not RFC 9110 negotiation.** The route matches
`Accept` with the regex `.*text/markdown.*`. A regex cannot read quality
values, so `Accept: text/html, text/markdown;q=0.1` — a client saying it
would much rather have HTML — routes to markdown anyway. Scenario 4 proves
it. If you need real proactive negotiation with q-value ranking, the ranking
has to happen somewhere that parses the header properly, which means the shim
or an ext_proc filter, not a route match.

Neither of these is a reason not to do this. They are the reason to assert on
`x-served-variant` rather than assume.

## Architecture

```
client ──Accept──> agentgateway :3000
                        │
                        ├── Accept matches /text\/markdown/ ──> md-shim :8081 ──> origin :8080
                        └── everything else ─────────────────────────────────────> origin :8080
```

- **`origin/`** — the legacy site. HTML only, full page chrome, three runbook
  pages. Stands in for the thing you cannot change.
- **`md-shim/`** — fetches the origin's HTML and returns `text/markdown`.
  Python stdlib `HTMLParser`, no dependencies. It handles the tags this origin
  emits and is not a general-purpose converter.
- **`config/agentgateway.yaml`** — the negotiation. Two routes, a header
  match, and a `Vary` header.

Route order is load-bearing. agentgateway takes the first matching route, so
the markdown route must be declared before the catch-all. Reverse them and
every client gets HTML.

## Two things worth knowing if you extend this

- **`Vary: Accept` is not optional.** Two representations share one URL, so
  without it the first response through any shared cache is the one every
  later client gets, regardless of what they asked for. The gateway sets it on
  both routes and the shim sets it too, so the header is right even if a cache
  sits directly in front of the shim.
- **agentgateway lowercases injected response header names.** The config says
  `X-Served-Variant`; the wire says `x-served-variant`. Case-sensitive
  assertions on headers you add in config will fail for a reason that has
  nothing to do with your routing. `scripts/demo.sh` matches
  case-insensitively and says why.

## A bug worth repeating, because it is silent

The shim drops site chrome by opening a "skip" region on tags like `<script>`
and `<nav>` and closing it on the matching end tag. The first version put
`<link>` in that same set. `<link>` is a void element with no end tag, so the
skip region opened and never closed, and the converter returned an empty
document — HTTP 200, `Content-Type: text/markdown`, one newline of body.

Nothing about that looks like a failure from the gateway's side. If you write
your own converter, separate container tags from void elements
(`DROP_TAGS` vs `DROP_VOID` in `md-shim/server.py`) and assert on body
content, not just status and content type.

## Verified

Every command in this README was run against this stack on 2026-09-08:
agentgateway v1.5.0 (`cr.agentgateway.dev/agentgateway:v1.5.0`),
`python:3.12-slim`, Docker 29.7.2, Compose v5.4.0, on arm64 macOS.
`./scripts/demo.sh` reports 15 passed, 0 failed. The byte counts and the
markdown block above are copied from that run.

## Topics

`agentgateway` `mcp` `ai-agents` `kubernetes` `content-negotiation`
`llms-txt` `markdown` `api-gateway`

## License

Apache-2.0. See [LICENSE](LICENSE).
