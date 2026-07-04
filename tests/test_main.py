from pathlib import Path

import fitz
from baml_py.errors import BamlError
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
