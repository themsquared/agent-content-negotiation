#!/usr/bin/env bash
# Five scenarios against one URL. The only thing that changes is Accept.
set -uo pipefail

GW="${GW:-http://localhost:3000}"
PAGE="${PAGE:-/runbooks/rotate-keys}"
PASS=0; FAIL=0

hr() { printf '%s\n' "----------------------------------------------------------------"; }

# assert <label> <expected-substring> <actual>
assert() {
  local label="$1" want="$2" got="$3"
  # -i because agentgateway emits injected response header names in
  # lowercase (x-served-variant, vary), not the case written in the config.
  if printf '%s' "$got" | grep -qiF -- "$want"; then
    printf '  PASS  %s\n' "$label"; PASS=$((PASS+1))
  else
    printf '  FAIL  %s (wanted %s)\n' "$label" "$want"; FAIL=$((FAIL+1))
  fi
}

# probe <accept-header>  -> prints headers, sets BODY
probe() {
  local accept="$1"
  HEADERS=$(curl -sS -D - -o /tmp/acn-body.$$ -H "Accept: ${accept}" "${GW}${PAGE}")
  BODY=$(cat /tmp/acn-body.$$); rm -f /tmp/acn-body.$$
}

hr; echo "SCENARIO 1  a browser  ->  Accept: text/html,application/xhtml+xml"
probe 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
assert "served the HTML variant"   "X-Served-Variant: html"        "$HEADERS"
assert "content-type is text/html" "Content-Type: text/html"       "$HEADERS"
assert "body carries the doctype"  "<!doctype html>"               "$BODY"
assert "Vary: Accept is set"       "Vary: Accept"                  "$HEADERS"

hr; echo "SCENARIO 2  an agent that asks  ->  Accept: text/markdown"
probe 'text/markdown'
assert "served the markdown variant"   "X-Served-Variant: markdown"  "$HEADERS"
assert "content-type is text/markdown" "Content-Type: text/markdown" "$HEADERS"
assert "body is a markdown heading"    "# Rotate provider keys"      "$BODY"
assert "code fence survived"           '```'                         "$BODY"
assert "link became a markdown link"   "[node drain runbook](/runbooks/drain-node)" "$BODY"
assert "no HTML doctype leaked"        ""                            "$HEADERS"
if printf '%s' "$BODY" | grep -qF '<!doctype'; then
  echo "  FAIL  markdown body still contains HTML"; FAIL=$((FAIL+1))
else
  echo "  PASS  markdown body contains no HTML"; PASS=$((PASS+1))
fi
if printf '%s' "$BODY" | grep -qF 'analytics.js'; then
  echo "  FAIL  site chrome leaked into the markdown"; FAIL=$((FAIL+1))
else
  echo "  PASS  site chrome (nav/script/footer) was dropped"; PASS=$((PASS+1))
fi

hr; echo "SCENARIO 3  THE GOTCHA  ->  Accept: */*   (curl's default, and a lot of agent HTTP clients)"
probe '*/*'
assert "served the HTML variant" "X-Served-Variant: html" "$HEADERS"
echo "  NOTE  '*/*' does not mention markdown, so the agent route does not match."
echo "        An agent that does not set Accept gets the HTML site and a"
echo "        parsing problem it will blame on your docs."

hr; echo "SCENARIO 4  THE LIMITATION  ->  Accept: text/html, text/markdown;q=0.1"
probe 'text/html, text/markdown;q=0.1'
assert "served the markdown variant anyway" "X-Served-Variant: markdown" "$HEADERS"
echo "  NOTE  The client said it would much rather have HTML (q=0.1 on"
echo "        markdown). A header regex cannot read that. This is a routing"
echo "        match, not RFC 9110 negotiation. See README 'What this is not'."

hr; echo "SCENARIO 5  payload size, same page, same origin"
probe 'text/html,application/xhtml+xml'; H_LEN=${#BODY}
probe 'text/markdown';                   M_LEN=${#BODY}
printf '  html     %5d bytes\n' "$H_LEN"
printf '  markdown %5d bytes\n' "$M_LEN"
if [ "$M_LEN" -lt "$H_LEN" ]; then
  printf '  PASS  markdown variant is smaller (%d bytes less)\n' "$((H_LEN-M_LEN))"; PASS=$((PASS+1))
else
  echo "  FAIL  markdown variant was not smaller"; FAIL=$((FAIL+1))
fi

hr
printf 'assertions: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
