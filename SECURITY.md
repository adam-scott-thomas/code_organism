# Security policy

## Reporting a vulnerability

If you have found a security issue in Code Organism, please report it privately rather than opening a public GitHub issue.

**Email:** `adamthomasdirect@gmail.com`

Please include:

- A description of the issue and its impact.
- Steps to reproduce, or a proof-of-concept if you have one.
- The commit hash or release version you reproduced against.
- Whether you'd like to be credited in the fix's release notes.

You should expect an acknowledgement within a few days. If the report is confirmed, a fix will be developed in a private branch and disclosed in the release notes once shipped.

## Scope

In scope:

- The engine itself (`Code_Organism/`) — parsers, the health/malware analyser, the graph store, the renderers, the MCP server.
- Defaults of any local HTTP service started by the renderer or MCP entry points.
- Any file the package writes to disk by default (recordings, KuzuDB stores, temp directories).

Out of scope (please don't report these):

- A user explicitly choosing to bind a renderer to `0.0.0.0` and getting traffic — that's an opt-in.
- Findings against demonstrably-malicious sample inputs in `examples/` — those exist to be detected, not run.
- Vulnerabilities in third-party dependencies (`kuzu`, `tree-sitter`, `igraph`, `mcp`, ...). Report those upstream.

## Defaults that matter

- Renderer HTTP servers bind to `127.0.0.1` by default. The `bind` keyword opts a session into wider exposure.
- `.corg` recordings serialise via `json` + `gzip` — no `pickle`, so loading an untrusted recording does not execute code. (Loading still parses untrusted JSON; treat unknown recordings the same way you'd treat any unknown file.)
- The malware analyser's signature lists in `health/malware.py` and `health/patterns.py` are detection targets, not invocations.

## Supported versions

Code Organism follows semver. Security fixes are issued against the most recent minor release. Older versions may receive a fix at the maintainer's discretion.
