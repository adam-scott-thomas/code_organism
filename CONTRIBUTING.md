# Contributing

Thanks for thinking about contributing to Code Organism. This document covers the practical bits — environment, tests, commits, PRs.

## Development setup

```bash
git clone https://github.com/adam-scott-thomas/code_organism.git
cd code_organism
pip install -e ".[dev]"
```

Python 3.10 or newer. Runtime deps are pinned in `pyproject.toml`.

## Running the test suite

```bash
python -m pytest tests/
```

148 tests, ~22 seconds, no external services required.

CI runs the same command on Python 3.10, 3.11, and 3.12 for every push and PR.

## Code style

- Apache 2.0 license — every source file carries `# SPDX-License-Identifier: Apache-2.0`.
- Type hints on public APIs.
- No new `datetime.utcnow()` calls — use `datetime.now(timezone.utc)`.
- HTTP servers bind `127.0.0.1` by default; expose more only when the user asks for it.
- Don't add `eval` / `exec` / `subprocess` to the engine. The malware module *detects* those patterns; the engine doesn't use them.

## Commit messages

Conventional-Commits style is preferred but not enforced:

```
fix(security): bind renderer servers to localhost
docs: add CHANGELOG
chore: untrack __pycache__ bytecode
```

Granular commits are welcome. Squash on merge if you'd rather have one in `main`.

## Pull requests

1. Fork → branch → PR against `main`.
2. CI must be green.
3. Update `CHANGELOG.md` under `[Unreleased]` if your change is user-visible.
4. New behaviour gets new tests. Bug fixes get a regression test.

## Reporting security issues

Don't open a public issue for a security report. See `SECURITY.md`.

## License

By contributing you agree your contribution is licensed under Apache 2.0.
