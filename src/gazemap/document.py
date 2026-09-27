"""PDF and image inputs rendered as pages the pipeline can analyze."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
DPI = 150  # readable overlays; the model resizes to 1024 px on the long side anyway


@dataclass
class DocumentPage:
    name: str
    image: np.ndarray  # height x width x 3, uint8 RGB
    _text_in: Callable[[int, int, int, int], str | None]

    def text_in(self, x: int, y: int, width: int, height: int) -> str | None:
        """Text inside a pixel rectangle, whitespace-normalized; None without a text layer."""
        return self._text_in(x, y, width, height)


@dataclass
class Document:
    """Pages of a PDF or a single image. Close it (or use ``with``) to release the PDF."""

    pages: list[DocumentPage]
    _close: Callable[[], None]
    closed: bool = False

    def close(self) -> None:
        if not self.closed:
            self._close()
            self.closed = True

    def __enter__(self) -> "Document":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def is_document_path(target: str) -> bool:
    if "://" in target:
        return False
    path = Path(target).expanduser()
    return path.suffix.lower() in IMAGE_SUFFIXES | {".pdf"} or path.exists()


def load_document(path: str | Path, dpi: int = DPI) -> Document:
    path = Path(path).expanduser()
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf(path, dpi)
    if suffix in IMAGE_SUFFIXES:
        image = np.asarray(Image.open(path).convert("RGB"))
        return Document([DocumentPage("image", image, lambda x, y, w, h: None)], _close=lambda: None)
    raise ValueError(f"unsupported file type {path.suffix!r} (use .pdf, .png, .jpg, .jpeg or .webp)")


def _load_pdf(path: Path, dpi: int) -> Document:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    scale = dpi / 72
    handles = []  # closed in reverse order: text pages, pages, then the document
    pages = []
    for index in range(len(pdf)):
        page = pdf[index]
        image = np.asarray(page.render(scale=scale).to_pil().convert("RGB"))
        textpage = page.get_textpage()
        handles += [page, textpage]
        page_height_pt = page.get_height()

        def text_in(x, y, width, height, textpage=textpage, top_pt=page_height_pt):
            if document.closed:
                raise RuntimeError("document is closed")
            # pixel rectangle (origin top-left) -> PDF points (origin bottom-left)
            raw = textpage.get_text_bounded(
                left=x / scale,
                bottom=top_pt - (y + height) / scale,
                right=(x + width) / scale,
                top=top_pt - y / scale,
            )
            return " ".join(raw.split())

        pages.append(DocumentPage(f"page-{index + 1}", image, text_in))

    def close() -> None:
        for handle in reversed(handles):
            handle.close()
        pdf.close()

    document = Document(pages, _close=close)
    return document
