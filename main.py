import tempfile
from pathlib import Path

import fitz
from baml_py.errors import BamlError
from fastapi import FastAPI, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from ocr_pipeline.pipeline import run_pipeline

app = FastAPI()


@app.exception_handler(fitz.FileDataError)
@app.exception_handler(fitz.EmptyFileError)
async def handle_invalid_pdf(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(BamlError)
async def handle_baml_error(request: Request, exc: BamlError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


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
