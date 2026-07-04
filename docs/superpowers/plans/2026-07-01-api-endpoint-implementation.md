# API Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder `main.py` with a FastAPI app exposing `run_pipeline` as a `POST /extract` HTTP endpoint, per `docs/superpowers/specs/2026-07-01-api-endpoint-design.md`.

**Architecture:** One FastAPI app in `main.py` at the repo root. The endpoint writes an uploaded file to a temp path, calls the existing `run_pipeline`, and returns its JSON output directly. Two exception handlers map specific failure modes to HTTP status codes; everything else falls through to FastAPI's default 500.

**Tech Stack:** FastAPI, uvicorn (ASGI server), python-multipart (file upload parsing), FastAPI's `TestClient` for tests.

## Global Constraints

- No async job/polling pattern — synchronous request/response only.
- No file size/page count limits.
- No authentication.
- No response envelope — the response body is exactly the JSON string `run_pipeline` returns.
- Do not modify `ocr_pipeline/`'s existing modules or `run_pipeline`'s signature.
- Error mapping (exact): `fitz.FileDataError` / `fitz.EmptyFileError` → 400; `baml_py.errors.BamlError` → 502; anything else → FastAPI's default 500.
- Use `uv add` for all new dependencies — do not hand-edit `pyproject.toml`.

---

### Task 1: FastAPI app skeleton + happy-path `/extract` endpoint

**Files:**
- Modify: `pyproject.toml` (via `uv add fastapi uvicorn python-multipart`)
- Modify: `main.py` (replace the placeholder entirely)
- Create: `tests/test_main.py`

**Interfaces:**
- Consumes: `run_pipeline` from `ocr_pipeline.pipeline` (already implemented).
- Produces: FastAPI `app` object in `main.py`, importable as `from main import app` — consumed by Task 2 (adds exception handlers to the same `app`) and by `tests/test_main.py`.

- [ ] **Step 1: Add the dependencies**

Run: `uv add fastapi uvicorn python-multipart`
Expected: `pyproject.toml` gains `fastapi`, `uvicorn`, `python-multipart` under `dependencies`, `uv.lock` updated.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_main.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_extract_returns_pipeline_result(monkeypatch):
    async def fake_run_pipeline(pdf_path):
        assert pdf_path.endswith(".pdf")
        return '{"district": {"value": "Dhaka", "confidence": "HIGH"}}'

    monkeypatch.setattr("main.run_pipeline", fake_run_pipeline)

    response = client.post(
        "/extract",
        files={"file": ("sample.pdf", b"%PDF-1.4 fake content", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == {"district": {"value": "Dhaka", "confidence": "HIGH"}}


def test_extract_cleans_up_temp_file_on_success(monkeypatch):
    captured_path = {}

    async def fake_run_pipeline(pdf_path):
        captured_path["path"] = pdf_path
        assert Path(pdf_path).exists()
        return "{}"

    monkeypatch.setattr("main.run_pipeline", fake_run_pipeline)

    response = client.post(
        "/extract",
        files={"file": ("sample.pdf", b"fake", "application/pdf")},
    )

    assert response.status_code == 200
    assert not Path(captured_path["path"]).exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'main'` or `ImportError` (no `app` defined yet in the placeholder `main.py`).

- [ ] **Step 3: Write the implementation**

Replace the entire contents of `main.py` with:

```python
import tempfile
from pathlib import Path

from fastapi import FastAPI, Response, UploadFile

from ocr_pipeline.pipeline import run_pipeline

app = FastAPI()


@app.post("/extract")
async def extract(file: UploadFile) -> Response:
    contents = await file.read()
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name
        result_json = await run_pipeline(temp_path)
    finally:
        if temp_path is not None:
            Path(temp_path).unlink(missing_ok=True)
    return Response(content=result_json, media_type="application/json")
```

Note: `NamedTemporaryFile(delete=False)` is used (rather than relying on the
context manager's own cleanup) because the file must still exist on disk
*after* the `with` block closes it — PyMuPDF needs to open it by path in
`run_pipeline`, after our own write handle has closed. The `finally` block
guarantees deletion regardless of whether `run_pipeline` succeeds or
raises.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_main.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: PASS, no regressions.

```bash
git add pyproject.toml uv.lock main.py tests/test_main.py
git commit -m "feat: add FastAPI /extract endpoint wrapping run_pipeline"
```

---

### Task 2: Error handling for corrupt PDFs and BAML failures

**Files:**
- Modify: `main.py` (add exception handlers)
- Modify: `tests/test_main.py` (add tests)

**Interfaces:**
- Consumes: `app` (Task 1).
- Produces: nothing new consumed elsewhere — this is the final piece of the API layer for this plan.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_main.py`:

```python
import fitz
from baml_py.errors import BamlError


def test_extract_corrupt_pdf_returns_400(monkeypatch):
    async def fake_run_pipeline(pdf_path):
        raise fitz.FileDataError("bad pdf")

    monkeypatch.setattr("main.run_pipeline", fake_run_pipeline)

    response = client.post(
        "/extract",
        files={"file": ("sample.pdf", b"fake", "application/pdf")},
    )

    assert response.status_code == 400


def test_extract_empty_pdf_returns_400(monkeypatch):
    async def fake_run_pipeline(pdf_path):
        raise fitz.EmptyFileError("empty pdf")

    monkeypatch.setattr("main.run_pipeline", fake_run_pipeline)

    response = client.post(
        "/extract",
        files={"file": ("sample.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 400


def test_extract_baml_error_returns_502(monkeypatch):
    async def fake_run_pipeline(pdf_path):
        raise BamlError("llm failed")

    monkeypatch.setattr("main.run_pipeline", fake_run_pipeline)

    response = client.post(
        "/extract",
        files={"file": ("sample.pdf", b"fake", "application/pdf")},
    )

    assert response.status_code == 502


def test_extract_cleans_up_temp_file_on_failure(monkeypatch):
    captured_path = {}

    async def fake_run_pipeline(pdf_path):
        captured_path["path"] = pdf_path
        raise fitz.FileDataError("bad pdf")

    monkeypatch.setattr("main.run_pipeline", fake_run_pipeline)

    client.post(
        "/extract",
        files={"file": ("sample.pdf", b"fake", "application/pdf")},
    )

    assert not Path(captured_path["path"]).exists()
```

If `BamlError("llm failed")` fails to construct in Step 2 (its actual
`__init__` signature turns out to differ from a plain string-message
exception), adjust the test to however `BamlError` is actually
constructible — check `baml_py/errors.pyi` or the installed package for
its real signature. Don't change the exception-handling design in
`main.py` to work around it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL — the two new corrupt-PDF cases return 500 (unhandled `fitz` exceptions), the `BamlError` case returns 500 (unhandled), since no exception handlers exist yet.

- [ ] **Step 3: Add the exception handlers**

In `main.py`, add after the `app = FastAPI()` line and before the `/extract` endpoint:

```python
import fitz
from baml_py.errors import BamlError
from fastapi import Request
from fastapi.responses import JSONResponse


@app.exception_handler(fitz.FileDataError)
@app.exception_handler(fitz.EmptyFileError)
async def handle_invalid_pdf(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(BamlError)
async def handle_baml_error(request: Request, exc: BamlError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_main.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: PASS, no regressions across the whole suite.

```bash
git add main.py tests/test_main.py
git commit -m "feat: map corrupt-PDF and BAML errors to 400/502 in /extract"
```
