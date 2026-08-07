---
id: DF-072-6
type: known-issue
status: open
opened_at: 2026-08-07
category: security
severity: SEV-3
slug: df-072-6-ssrf-guard-residuals-proxy-and-fake-ip
---

# The SSRF guard shipped in P1b has **two residuals that re-open address pinning** — an ambient proxy and a fake-IP resolver. Neither is a defect in the guard; both mean *"rebinding is closed"* must never be claimed unqualified

TASK 072 P1b routed both of `wiki-import`'s egress call sites (`_download_pdf`,
`_download_raw_html`) through the external `html` skill's guarded ladder
(resolve → pin → assert-public → bounded read, every hop). That closed the unguarded `urlopen`
hole. It did **not** make DNS rebinding universally impossible, and this issue exists so nobody
writes that sentence into a doc later.

## Residual 1 — an ambient proxy makes the pin decorative

`_pin_host_addrs` binds the resolved address for the connection. If an HTTP proxy is in play, the
client connects to the **proxy**, which resolves the target itself — the pin binds nothing that
matters.

- **Fixed once already, and the fix is the reason this is only SEV-3.** The ladder used to build
  `httpx.Client` with the default `trust_env=True`, so *any* ambient proxy silently applied —
  including a **macOS System Configuration proxy that `env | grep -i proxy` does not show**. This
  machine has one at `127.0.0.1:1082`. Measured at the time: pinning `example.com` to a blackholed
  `192.0.2.1` returned **HTTP 200** through the proxy versus `ConnectTimeout` direct — i.e. the pin
  was provably decorative. The skill now sets `trust_env=False` and requires an explicit
  `$HTML_PROXY` opt-in with a one-time stderr notice.
- **What remains**: setting `HTML_PROXY` re-opens it **by construction**. That is the correct
  trade — an operator who needs a proxy needs it — but it is a real condition, not a theoretical
  one.

## Residual 2 — a fake-IP resolver makes the pin bind a synthetic address

This machine runs a resolver that maps real hosts into `198.18.x.x` (RFC 2544 benchmarking space).
That is why `HTML_SSRF_ALLOW_NETS=198.18.0.0/15` is the skill's **shipped default** — without it
every ordinary fetch would be refused as "private".

The consequence: the guard pins the **synthetic** address, and the synthetic→real mapping is owned
by the proxy tool, outside the guard's view. The allow-net is doing exactly what it says, but a
reader who sees "addresses are pinned" will over-read it.

## Why this is SEV-3, stated honestly

The guard closes the class that actually mattered here: an attacker-controlled **redirect** to a
private/link-local host, which the old `urlopen` followed silently. That is proved by execution
(`tests/test_import_ssrf.py::test_redirect_to_a_private_host_is_refused`). Both residuals require
an operator-configured network intermediary already present on the machine. Neither is reachable
by a hostile *page*.

## What to do — and what NOT to do

- **Do NOT** write "DNS rebinding is closed" or "all egress is pinned" into `security.md`,
  `SKILL.md`, or a task record. The A10 section already carries the qualified version; keep it.
- **Do** re-read the residual list in the `html` skill's own `SKILL.md` §5 before making any
  stronger claim — that skill owns the guard, and it is the authority on what its ladder does.
- If a stronger guarantee is ever needed, the shape is: pin at the socket layer and re-verify the
  peer address *after* connect, refusing on mismatch — which closes rebinding for the direct case
  but still cannot see through a proxy. Scope that deliberately; do not bolt it on.

## Related

- `docs/architectures/security.md` §7.3 A10 — the shipped control and both residuals.
- `tests/test_import_ssrf.py` — the executed refusal set, the redirect case, and the positive
  control that stops the whole suite from being satisfiable by a guard that refuses everything.
- [[df-072-3-one-json-envelope-per-cli-is-false]] — a sibling "the doc claims more than the code
  does" finding from the same task.
