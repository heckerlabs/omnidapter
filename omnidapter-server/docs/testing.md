# Testing

From repository root:

```bash
uv run pytest
```

Targeted server tests:

```bash
uv run pytest omnidapter-server/tests
```

Quality checks:

```bash
uv run ruff check .
uv run pyright
```

Coverage report:

```bash
uv run pytest --cov=omnidapter-server/src/omnidapter_server --cov-report=term
```
