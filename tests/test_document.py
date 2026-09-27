import numpy as np
import pytest
from PIL import Image

from gazemap.document import load_document


def test_pdf_pages_render_at_150_dpi_with_text_under_a_region(resume_pdf):
    with load_document(resume_pdf) as doc:
        assert [p.name for p in doc.pages] == ["page-1"]
        page = doc.pages[0]
        height, width, channels = page.image.shape
        assert channels == 3
        assert abs(width - 1240) <= 3 and abs(height - 1754) <= 3  # A4 at 150 dpi
        # the red header band spans the top of the page
        assert page.image[60, 100].tolist() == [225, 29, 72]
        assert page.image[height - 60, 100].tolist() == [255, 255, 255]
        text = page.text_in(x=60, y=40, width=600, height=80)
        assert "JANE EXAMPLE" in text
        assert page.text_in(x=60, y=height - 80, width=600, height=60) == ""


def test_multi_page_pdf_yields_one_entry_per_page(resume_pdf, tmp_path):
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(resume_pdf))
    doubled = pdfium.PdfDocument.new()
    doubled.import_pages(doc, [0, 0])
    two_pages = tmp_path / "two.pdf"
    doubled.save(str(two_pages))
    with load_document(two_pages) as doc:
        assert [p.name for p in doc.pages] == ["page-1", "page-2"]


def test_image_input_has_no_text_layer(tmp_path):
    path = tmp_path / "shot.png"
    Image.new("RGB", (300, 200), (255, 255, 255)).save(path)
    with load_document(path) as doc:
        (page,) = doc.pages
    assert page.name == "image"
    assert page.image.shape == (200, 300, 3)
    assert page.text_in(x=0, y=0, width=50, height=50) is None


def test_unsupported_file_type_raises(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello")
    with pytest.raises(ValueError, match="unsupported"):
        load_document(path)


def test_closing_a_pdf_releases_it_and_is_idempotent(resume_pdf):
    doc = load_document(resume_pdf)
    assert not doc.closed
    doc.close()
    doc.close()
    assert doc.closed
    with pytest.raises(RuntimeError, match="closed"):
        doc.pages[0].text_in(0, 0, 10, 10)
