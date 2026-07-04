import fitz

from ocr_pipeline.ingestion import Page, is_valid_bangla_text, split_pdf_pages


def test_page_dataclass_fields():
    page = Page(
        page_number=1,
        image_bytes=b"",
        native_text="some text",
        has_valid_text_layer=True,
    )
    assert page.page_number == 1
    assert page.image_bytes == b""
    assert page.native_text == "some text"
    assert page.has_valid_text_layer is True


def test_split_pdf_pages_returns_one_page_per_pdf_page(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Hello, this is a valid English sentence.")
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Another valid page of text.")
    doc.save(str(pdf_path))
    doc.close()

    pages = split_pdf_pages(str(pdf_path))

    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert pages[1].page_number == 2
    for page in pages:
        assert page.image_bytes
        assert page.native_text is not None
        assert page.has_valid_text_layer is True


def test_split_pdf_pages_blank_page_has_no_valid_text_layer(tmp_path):
    pdf_path = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(pdf_path))
    doc.close()

    pages = split_pdf_pages(str(pdf_path))

    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert pages[0].native_text is None
    assert pages[0].has_valid_text_layer is False
    assert pages[0].image_bytes


def test_is_valid_bangla_text_pure_english():
    assert is_valid_bangla_text("Hello, this is a valid English sentence.") is True


def test_is_valid_bangla_text_pure_bangla():
    assert is_valid_bangla_text("এটি একটি বৈধ বাংলা বাক্য।") is True


def test_is_valid_bangla_text_mixed():
    assert is_valid_bangla_text("Owner: রহিম, Plot No: 123") is True


def test_is_valid_bangla_text_gibberish():
    assert is_valid_bangla_text("¤§¶†‡•‰∑∆π√∫≈≠±÷×¥£€¢©®™¤§¶†‡•‰∑∆") is False


def test_is_valid_bangla_text_empty():
    assert is_valid_bangla_text("") is False


def test_is_valid_bangla_text_whitespace_only():
    assert is_valid_bangla_text("   \n\t  ") is False


def test_is_valid_bangla_text_tolerates_small_noise():
    assert is_valid_bangla_text("A mostly clean English sentence with one stray symbol: ¤") is True
