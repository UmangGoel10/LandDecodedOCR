# API Endpoint: FastAPI Microservice — Design

## Context

`run_pipeline` (in `src/ocr_pipeline/pipeline.py`) is fully implemented and
tested against mocked LLM calls, but only callable as a Python function
taking a local file path. This design wraps it in an HTTP API so the OCR
pipeline can run as a standalone microservice, replacing the placeholder
`main.py` at the repo root.

## Non-goals

- No async job/polling pattern — the endpoint is synchronous, holding the
  request open until `run_pipeline` completes.
- No file size/page count limits — deferred until there's real usage data
  to calibrate a sensible threshold against.
- No authentication/authorization.
- No response envelope — the response body is exactly the JSON
  `run_pipeline` already produces (a `LandRecordFields` object), no
  wrapping metadata.
- No changes to `ocr_pipeline/`'s existing 4 modules or their public
  interfaces — this design only adds an API layer on top of the existing
  `run_pipeline` entry point.

## Components

### `main.py` (repo root, replaces the placeholder)

A FastAPI app with one endpoint:

```
POST /extract
  Request:  multipart/form-data, one file field (a PDF)
  Response: 200, body = LandRecordFields JSON (same shape run_pipeline
            already returns)
```

Flow per request:
1. Read the uploaded file's bytes.
2. Write them to a temp file via `tempfile.NamedTemporaryFile` (or
   equivalent) — `run_pipeline` takes a path, not bytes, and this design
   deliberately doesn't change that (see Non-goals).
3. `await run_pipeline(temp_path)`.
4. Delete the temp file in a `finally` block, so cleanup happens even if
   `run_pipeline` raises.
5. Return the JSON string as the response body.

### Error handling

Two specific failure modes get distinct status codes; everything else
propagates to FastAPI's default exception handler (500), matching the
"no custom exception types, let real failures surface" pattern already
used throughout `ocr_pipeline/`:

| Exception | Status | Reasoning |
|---|---|---|
| `fitz.FileDataError`, `fitz.EmptyFileError` | 400 Bad Request | Corrupt/empty PDF — client-caused bad input. |
| `baml_py.errors.BamlError` (base class for all BAML/LLM call failures) | 502 Bad Gateway | The server's own upstream dependency (Claude/Gemini) failed — not the client's fault. |
| Anything else | 500 (FastAPI default) | Unclassified failure; refine later once real failure modes are observed. |

Implemented via FastAPI exception handlers (`@app.exception_handler(...)`)
registered for `fitz.FileDataError`/`fitz.EmptyFileError` and `BamlError`,
rather than a try/except inside the endpoint function — keeps the endpoint
body itself linear (the happy path only) and the error-status mapping in
one place, visible independent of the endpoint logic.

## Dependencies

Add via `uv add`: `fastapi`, `uvicorn`, `python-multipart` (FastAPI's
required parser for multipart file uploads).

## Testing

FastAPI's `TestClient` (httpx-based, ships with FastAPI). Tests mock
`run_pipeline` itself (not the underlying BAML calls again — those are
already covered by `ocr_pipeline`'s own test suite) so these tests verify
request/response wiring only:

- A successful upload returns 200 with the `run_pipeline` JSON as the body.
- `run_pipeline` raising `fitz.FileDataError`/`EmptyFileError` → 400.
- `run_pipeline` raising `BamlError` → 502.
- The temp file is cleaned up in both the success and failure cases.
