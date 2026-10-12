# Proposed upstream changes: lambda-feedback/toolkit-python

Draft issues/patches against `toolkit-python@ae52fa6` (2026-09-01). Once both land, these packages can switch from structural typing to a real `lf_toolkit` dependency (criteria's `ResultLike` protocol stands in for `lf_toolkit.evaluation.Result` until then). Nothing has been filed upstream yet.

## 1. Dev and optional tools are declared as runtime requirements

The `# dev dependencies` block in `pyproject.toml` sits inside `[tool.poetry.dependencies]`, so every install of `lf_toolkit` requires them:

```toml
poetry-plugin-export = "^1.9.0"
pytest-asyncio = "^1.2.0"
pillow = "^12.1.0"
requests = "^2.32.5"
dotenv = "^0.9.9"
boto3 = "^1.42.36"
pydantic = "^2.0"
```

**Impact:** `pip install lf_toolkit` installs 80 packages (237 MB), while the core (`sympy`, `ujson`, `anyio`, `jsonrpcserver`) is a fraction of that. Evaluation functions deployed to size-limited targets (e.g. AWS Lambda's 250 MB unzipped limit) pay for boto3, pillow and pydantic even if they never upload images or use chat types.

**What imports them** (checked at `ae52fa6`):

| Package | Imported by | Proposal |
|---|---|---|
| `pytest-asyncio`, `poetry-plugin-export` | nothing at runtime | move to `[tool.poetry.group.dev.dependencies]` |
| `pillow`, `requests`, `dotenv`, `boto3` (botocore) | `lf_toolkit/evaluation/image_upload.py` only | optional extra `image-upload` |
| `pydantic` | `lf_toolkit/shared/mued_api_v0_1_0.py`, used by `lf_toolkit.chat` | optional extra `chat` |

`dotenv` on PyPI is a shim that depends on `python-dotenv`; the module imported is `dotenv` from `python-dotenv`, so the extra should name `python-dotenv` directly.

Sketch:

```toml
[tool.poetry.dependencies]
python = "^3.11"
sympy = ">=1.12,<2.0"
ujson = "5.10.0"
anyio = "4.6.0"
jsonrpcserver = ">=5.0.9"
# ... existing optional parsing/http/ipc/gcs dependencies ...
pillow = { version = "^12.1.0", optional = true }
requests = { version = "^2.32.5", optional = true }
python-dotenv = { version = "^1.0", optional = true }
boto3 = { version = "^1.42.36", optional = true }
pydantic = { version = "^2.0", optional = true }

[tool.poetry.extras]
parsing = ["antlr4-python3-runtime", "lark", "latex2sympy"]
ipc = ["pywin32"]
gcs = ["google-cloud-storage"]
http = ["fastapi"]
image-upload = ["pillow", "requests", "python-dotenv", "boto3"]
chat = ["pydantic"]

[tool.poetry.group.dev.dependencies]
# ... existing black/flake8/isort/pre-commit/pytest/pytest-cov ...
poetry-plugin-export = "^1.9.0"
pytest-asyncio = "^1.2.0"
```

## 2. `Result.feedback` joins blank feedback entries

`Result.feedback` joins every feedback entry with `<br>`, so adding blank feedback produces empty segments (`"a<br><br>b"`). A tag can only be recorded by adding feedback, which forces a choice between losing the tag and emitting an empty segment.

compareExpressions records many tags whose feedback is intentionally blank (its generators return `None` or `""` for internal outcomes), and its tests assert on those tags. Its own `EvaluationResult` kept the tag but skipped blank text when serialising.

**Proposal:** skip blank entries when building the string, keeping tags unchanged:

```python
@property
def feedback(self) -> str:
    return "<br>".join(text.strip() for texts in self._feedback.values() for text in texts if text and text.strip())
```

`CriteriaGraph.export_feedback` already adds blank feedback as `""`, so once this lands the adopted output matches `EvaluationResult`'s.

## 3. (Minor) No home for extra test data

`Result` uses `__slots__`, so consumers can't attach extra test data such as compareExpressions' criteria-graph JSON and mermaid. `CriteriaGraph.test_data(graphs)` returns that payload for the consumer to merge into `to_dict(include_test_data=True)`. An `extra_test_data: dict` slot included by `to_dict(include_test_data=True)` would remove that step.
