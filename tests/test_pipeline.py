import pytest

from ocr_pipeline.pipeline import run_pipeline


def test_run_pipeline_not_implemented():
    with pytest.raises(NotImplementedError):
        run_pipeline("dummy.pdf")
