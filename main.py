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
