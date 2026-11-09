
"""PDF extraction with controlled OCR fallback.

Uses PyMuPDF for text-based PDFs and Tesseract for
pages with insufficient extractable text.

PDF downloading and vector indexing remain separate.
"""

from pathlib import Path
import re
import subprocess

import pymupdf


MAX_PDF_SIZE_MB = 25
MAX_PAGES = 200
MAX_OCR_PAGES = 20
OCR_DPI = 200
OCR_TIMEOUT = 90
MIN_TEXT_CHARACTERS = 40


class PDFParsingError(Exception):
    """Raised when a PDF cannot be processed."""


class ScannedPDFError(PDFParsingError):
    """Raised when OCR cannot recover readable text."""


def clean_pdf_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_page_ocr(page) -> str:
    """Run OCR on a rendered PDF page."""

    try:
        pixmap = page.get_pixmap(
            dpi=OCR_DPI,
            alpha=False,
        )

        # Feed PNG bytes directly to Tesseract.
        # No temporary image files are required.
        result = subprocess.run(
            [
                "tesseract",
                "stdin",
                "stdout",
                "-l",
                "eng",
            ],
            input=pixmap.tobytes("png"),
            capture_output=True,
            timeout=OCR_TIMEOUT,
            check=True,
        )

        return clean_pdf_text(
            result.stdout.decode(
                "utf-8",
                errors="replace",
            )
        )

    except (
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
        OSError,
    ) as exc:
        raise PDFParsingError(
            f"OCR processing failed: {exc}"
        ) from exc


def parse_pdf(file_path: str) -> tuple[str, str]:
    """Extract text, using OCR where necessary."""

    path = Path(file_path)

    if not path.is_file():
        raise PDFParsingError(
            f"PDF file not found: {path}"
        )

    size = path.stat().st_size

    if size == 0:
        raise PDFParsingError("PDF file is empty")

    if size > MAX_PDF_SIZE_MB * 1024 * 1024:
        raise PDFParsingError(
            "PDF exceeds configured size limit"
        )

    with path.open("rb") as f:
        if f.read(5) != b"%PDF-":
            raise PDFParsingError(
                "Invalid PDF signature"
            )

    try:
        with pymupdf.open(str(path)) as pdf:

            if pdf.needs_pass:
                raise PDFParsingError(
                    "Encrypted PDF is not supported"
                )

            if pdf.page_count == 0:
                raise PDFParsingError(
                    "PDF contains no pages"
                )

            if pdf.page_count > MAX_PAGES:
                raise PDFParsingError(
                    "PDF exceeds page limit"
                )

            metadata = pdf.metadata or {}

            title = (
                metadata.get("title") or ""
            ).strip()

            if not title or title.lower() in {
                "untitled",
                "document",
                "microsoft word",
            }:
                title = path.stem.replace("_", " ")

            pages = []
            ocr_used = 0
            skipped_pages = []

            for index, page in enumerate(pdf):

                text = clean_pdf_text(
                    page.get_text(
                        "text",
                        sort=True,
                    )
                )

                # OCR only pages with very little text.
                if len(text) < MIN_TEXT_CHARACTERS:

                    if ocr_used < MAX_OCR_PAGES:
                        text = extract_page_ocr(page)
                        ocr_used += 1
                    else:
                        skipped_pages.append(index + 1)

                if text:
                    pages.append(
                        f"[Page {index + 1}]\n{text}"
                    )

            if skipped_pages:
                raise PDFParsingError(
                    "OCR page limit reached; "
                    "document is only partially extracted. "
                    f"Unprocessed pages: {skipped_pages[:10]}"
                )

            if not pages:
                raise ScannedPDFError(
                    "No readable text recovered"
                )

            print(
                f"PDF parsed: {pdf.page_count} pages, "
                f"OCR used on {ocr_used} pages"
            )

            return title, "\n\n".join(pages)

    except PDFParsingError:
        raise

    except (pymupdf.FileDataError, ValueError) as exc:
        raise PDFParsingError(
            f"Unable to parse PDF: {exc}"
        ) from exc
