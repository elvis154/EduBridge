# app/pdf_utils.py

"""
PDF Utilities
-------------
PDF validation, text extraction, OCR fallback, metadata,
text cleaning, chunking and PDF utilities.
"""

import os
import re
import logging
import time

from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any
from dataclasses import dataclass

from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.errors import PdfReadError


# ============================================================
# OPTIONAL OCR IMPORTS
# ============================================================

try:
    import pytesseract
    from PIL import Image
    import pdf2image

    OCR_AVAILABLE = True

except ImportError:
    OCR_AVAILABLE = False


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# CONSTANTS
# ============================================================

MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_PDF_PAGES = 1000

MAX_PAGES_FOR_OCR = 20

DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50

MIN_TEXT_LENGTH = 10
OCR_TRIGGER_LENGTH = 100

OCR_DPI = 200
OCR_TIMEOUT = 60


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class PDFMetadata:
    filename: str
    file_size: int
    pages: int

    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    creator: Optional[str] = None
    producer: Optional[str] = None

    creation_date: Optional[str] = None
    modification_date: Optional[str] = None

    encrypted: bool = False
    has_text: bool = False

    word_count: Optional[int] = None
    char_count: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:

        return {
            "filename": self.filename,
            "file_size": self.file_size,
            "pages": self.pages,
            "title": self.title,
            "author": self.author,
            "subject": self.subject,
            "creator": self.creator,
            "producer": self.producer,
            "creation_date": self.creation_date,
            "modification_date": self.modification_date,
            "encrypted": self.encrypted,
            "has_text": self.has_text,
            "word_count": self.word_count,
            "char_count": self.char_count,
        }


# ============================================================
# CUSTOM ERROR
# ============================================================

class PDFError(Exception):
    """Custom PDF processing exception."""
    pass


# ============================================================
# PDF VALIDATION
# ============================================================

def validate_pdf(
    path: str,
    check_encryption: bool = True
) -> Tuple[bool, str]:

    if not os.path.exists(path):
        return False, f"File not found: {path}"

    file_size = os.path.getsize(path)

    if file_size == 0:
        return False, "File is empty"

    if file_size > MAX_FILE_SIZE:
        return False, "File is too large (maximum 50MB)"

    if not path.lower().endswith(".pdf"):
        return False, "File must have .pdf extension"

    try:

        with open(path, "rb") as file:

            reader = PdfReader(file)

            if check_encryption and reader.is_encrypted:
                return False, "PDF is encrypted and cannot be read"

            page_count = len(reader.pages)

            if page_count == 0:
                return False, "PDF has no pages"

            if page_count > MAX_PDF_PAGES:
                return False, (
                    f"PDF has too many pages "
                    f"({page_count}). Maximum is {MAX_PDF_PAGES}."
                )

        return True, "Valid PDF"

    except PdfReadError as e:

        return False, f"Invalid PDF: {str(e)}"

    except Exception as e:

        return False, f"Failed to read PDF: {str(e)}"


# ============================================================
# METADATA
# ============================================================

def extract_metadata(path: str) -> PDFMetadata:

    try:

        file_size = os.path.getsize(path)
        filename = os.path.basename(path)

        with open(path, "rb") as file:

            reader = PdfReader(file)

            metadata = reader.metadata
            pages = len(reader.pages)

            text = _extract_with_pypdf2(path)

            return PDFMetadata(
                filename=filename,
                file_size=file_size,
                pages=pages,

                title=metadata.get("/Title")
                if metadata else None,

                author=metadata.get("/Author")
                if metadata else None,

                subject=metadata.get("/Subject")
                if metadata else None,

                creator=metadata.get("/Creator")
                if metadata else None,

                producer=metadata.get("/Producer")
                if metadata else None,

                creation_date=metadata.get("/CreationDate")
                if metadata else None,

                modification_date=metadata.get("/ModDate")
                if metadata else None,

                encrypted=reader.is_encrypted,

                has_text=len(text.strip()) >= MIN_TEXT_LENGTH,

                word_count=get_word_count(text),

                char_count=len(text)
            )

    except Exception as e:

        logger.error(
            f"Failed to extract metadata: {e}"
        )

        return PDFMetadata(
            filename=os.path.basename(path),
            file_size=os.path.getsize(path)
            if os.path.exists(path)
            else 0,
            pages=0
        )


# ============================================================
# MAIN EXTRACTION FUNCTION
# ============================================================

def extract_text_from_pdf(
    path: str,
    use_ocr: bool = True,
    max_pages_for_ocr: int = MAX_PAGES_FOR_OCR,
    timeout: int = OCR_TIMEOUT
) -> str:

    start_time = time.time()

    logger.info(
        f"Starting PDF extraction: {path}"
    )

    # --------------------------------------------------------
    # VALIDATE
    # --------------------------------------------------------

    valid, message = validate_pdf(path)

    if not valid:

        raise PDFError(message)

    try:

        # ----------------------------------------------------
        # STEP 1: NORMAL PDF TEXT EXTRACTION
        # ----------------------------------------------------

        logger.info(
            "Attempting standard PDF text extraction..."
        )

        text = _extract_with_pypdf2(path)

        logger.info(
            f"Standard extraction returned "
            f"{len(text)} characters"
        )

        # ----------------------------------------------------
        # STEP 2: OCR FALLBACK
        # ----------------------------------------------------

        if (
            use_ocr
            and len(text.strip()) < OCR_TRIGGER_LENGTH
        ):

            if OCR_AVAILABLE:

                logger.info(
                    "Insufficient text detected."
                )

                logger.info(
                    "Starting OCR fallback..."
                )

                try:

                    ocr_text = _extract_with_ocr(
                        path=path,
                        max_pages=max_pages_for_ocr,
                        timeout=timeout
                    )

                    logger.info(
                        f"OCR returned "
                        f"{len(ocr_text)} characters"
                    )

                    # Only use OCR if it actually
                    # produced more useful text.

                    if len(ocr_text.strip()) > len(
                        text.strip()
                    ):

                        text = ocr_text

                        logger.info(
                            "Using OCR result."
                        )

                except Exception as e:

                    logger.warning(
                        f"OCR failed: {e}"
                    )

            else:

                logger.warning(
                    "OCR requested but OCR dependencies "
                    "are not installed."
                )

        # ----------------------------------------------------
        # STEP 3: CLEAN TEXT
        # ----------------------------------------------------

        text = clean_text(text)

        # ----------------------------------------------------
        # STEP 4: VALIDATE RESULT
        # ----------------------------------------------------

        if (
            not text
            or len(text.strip()) < MIN_TEXT_LENGTH
        ):

            raise PDFError(
                "No text could be extracted from this PDF. "
                "The document may be scanned, image-based, "
                "or corrupted."
            )

        elapsed = time.time() - start_time

        logger.info(
            f"PDF extraction completed: "
            f"{len(text)} characters "
            f"in {elapsed:.2f}s"
        )

        return text

    except PDFError:
        raise

    except Exception as e:

        logger.exception(
            "PDF extraction failed"
        )

        raise PDFError(
            f"Failed to extract text: {str(e)}"
        )


# ============================================================
# STANDARD PDF EXTRACTION
# ============================================================

def _extract_with_pypdf2(path: str) -> str:

    text_parts = []

    try:

        with open(path, "rb") as file:

            reader = PdfReader(file)

            total_pages = len(reader.pages)

            for page_number, page in enumerate(
                reader.pages,
                start=1
            ):

                try:

                    page_text = (
                        page.extract_text()
                        or ""
                    )

                    if page_text.strip():

                        # Preserve page boundaries.
                        text_parts.append(
                            f"\n[Page {page_number}]\n"
                            f"{page_text}"
                        )

                    else:

                        logger.debug(
                            f"Page {page_number} "
                            f"contains no text."
                        )

                except Exception as e:

                    logger.warning(
                        f"Page {page_number} "
                        f"extraction failed: {e}"
                    )

            text = "\n".join(text_parts)

            if not text.strip():

                logger.info(
                    "No standard PDF text found."
                )

            return text

    except PdfReadError as e:

        logger.error(
            f"PDF read error: {e}"
        )

        raise

    except Exception as e:

        logger.error(
            f"Standard extraction error: {e}"
        )

        raise


# ============================================================
# OCR EXTRACTION
# ============================================================

def _extract_with_ocr(
    path: str,
    max_pages: int,
    timeout: int
) -> str:

    if not OCR_AVAILABLE:

        raise PDFError(
            "OCR libraries are not installed."
        )

    start_time = time.time()

    text_parts = []

    try:

        logger.info(
            f"Converting PDF to images "
            f"at {OCR_DPI} DPI..."
        )

        images = pdf2image.convert_from_path(
            path,
            dpi=OCR_DPI,
            first_page=1,
            last_page=max_pages,
            fmt="jpeg"
        )

        logger.info(
            f"Converted {len(images)} pages "
            f"for OCR."
        )

        # ----------------------------------------------------
        # OCR EACH PAGE
        # ----------------------------------------------------

        for page_number, image in enumerate(
            images,
            start=1
        ):

            elapsed = time.time() - start_time

            if elapsed > timeout:

                logger.warning(
                    "OCR timeout reached."
                )

                break

            try:

                logger.info(
                    f"OCR processing page "
                    f"{page_number}/{len(images)}"
                )

                # ------------------------------------------------
                # TESSERACT
                # ------------------------------------------------

                page_text = pytesseract.image_to_string(
                    image,
                    config="--oem 3 --psm 6"
                )

                if page_text.strip():

                    text_parts.append(
                        f"\n[Page {page_number}]\n"
                        f"{page_text}"
                    )

                    logger.info(
                        f"Page {page_number}: "
                        f"{len(page_text)} characters"
                    )

                else:

                    logger.warning(
                        f"Page {page_number}: "
                        f"No text detected"
                    )

            except Exception as e:

                logger.warning(
                    f"OCR failed on page "
                    f"{page_number}: {e}"
                )

                continue

        return "\n".join(text_parts)

    except Exception as e:

        logger.exception(
            "OCR extraction failed"
        )

        raise PDFError(
            f"OCR failed: {str(e)}"
        )


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text: str) -> str:

    if not text:
        return ""

    # Remove null/control characters
    text = re.sub(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]",
        "",
        text
    )

    # Normalize line endings
    text = text.replace(
        "\r\n",
        "\n"
    )

    text = text.replace(
        "\r",
        "\n"
    )

    # Normalize spaces WITHOUT destroying
    # line structure.
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    # Remove spaces before punctuation
    text = re.sub(
        r"\s+([.,!?;:])",
        r"\1",
        text
    )

    # Reduce excessive blank lines
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    # Remove whitespace from each line
    lines = []

    for line in text.split("\n"):

        line = line.strip()

        if line:
            lines.append(line)

    text = "\n".join(lines)

    return text.strip()


# ============================================================
# TEXT CHUNKING
# ============================================================

def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP
) -> List[str]:

    if not text:
        return []

    if chunk_size <= 0:
        raise ValueError(
            "chunk_size must be greater than 0"
        )

    if overlap < 0:
        raise ValueError(
            "overlap cannot be negative"
        )

    if overlap >= chunk_size:
        raise ValueError(
            "overlap must be smaller than chunk_size"
        )

    if len(text) <= chunk_size:
        return [text]

    chunks = []

    start = 0

    while start < len(text):

        end = min(
            start + chunk_size,
            len(text)
        )

        # ----------------------------------------------------
        # Try to stop at sentence boundary
        # ----------------------------------------------------

        if end < len(text):

            search_start = max(
                start,
                end - 150
            )

            section = text[
                search_start:end
            ]

            matches = list(
                re.finditer(
                    r"[.!?](?:\s|$)",
                    section
                )
            )

            if matches:

                last_match = matches[-1]

                end = (
                    search_start
                    + last_match.end()
                )

        chunk = text[
            start:end
        ].strip()

        if chunk:

            chunks.append(chunk)

        if end >= len(text):
            break

        start = end - overlap

    return chunks


# ============================================================
# WORD COUNT
# ============================================================

def get_word_count(text: str) -> int:

    if not text:
        return 0

    return len(
        re.findall(
            r"\b\w+\b",
            text
        )
    )


# ============================================================
# TEXT STATISTICS
# ============================================================

def get_text_statistics(
    text: str
) -> Dict[str, Any]:

    if not text:

        return {
            "char_count": 0,
            "word_count": 0,
            "sentence_count": 0,
            "paragraph_count": 0,
            "avg_word_length": 0,
            "avg_sentence_length": 0
        }

    words = re.findall(
        r"\b\w+\b",
        text
    )

    sentences = [
        sentence
        for sentence in re.split(
            r"[.!?]+",
            text
        )
        if sentence.strip()
    ]

    paragraphs = [
        paragraph
        for paragraph in text.split("\n\n")
        if paragraph.strip()
    ]

    return {

        "char_count": len(text),

        "word_count": len(words),

        "sentence_count": len(sentences),

        "paragraph_count": len(paragraphs),

        "avg_word_length": (
            sum(len(word) for word in words)
            / len(words)
            if words
            else 0
        ),

        "avg_sentence_length": (
            len(words)
            / len(sentences)
            if sentences
            else 0
        )
    }


# ============================================================
# SEARCH PAGES BY KEYWORD
# ============================================================

def extract_pages_by_keyword(
    path: str,
    keywords: List[str],
    case_sensitive: bool = False
) -> List[Dict[str, Any]]:

    try:

        # Extract without OCR here because
        # page boundaries are important.

        with open(path, "rb") as file:

            reader = PdfReader(file)

            results = []

            for page_number, page in enumerate(
                reader.pages,
                start=1
            ):

                page_text = (
                    page.extract_text()
                    or ""
                )

                search_text = (
                    page_text
                    if case_sensitive
                    else page_text.lower()
                )

                found_keywords = []

                for keyword in keywords:

                    search_keyword = (
                        keyword
                        if case_sensitive
                        else keyword.lower()
                    )

                    if search_keyword in search_text:

                        found_keywords.append(
                            keyword
                        )

                if found_keywords:

                    results.append({
                        "page": page_number,
                        "keywords": found_keywords,
                        "text": page_text[:500]
                    })

            return results

    except Exception as e:

        logger.error(
            f"Keyword extraction failed: {e}"
        )

        return []


# ============================================================
# MERGE PDFS
# ============================================================

def merge_pdfs(
    pdf_paths: List[str],
    output_path: str
) -> bool:

    try:

        writer = PdfWriter()

        for pdf_path in pdf_paths:

            with open(
                pdf_path,
                "rb"
            ) as file:

                reader = PdfReader(file)

                for page in reader.pages:

                    writer.add_page(page)

        with open(
            output_path,
            "wb"
        ) as output:

            writer.write(output)

        logger.info(
            f"Merged {len(pdf_paths)} PDFs"
        )

        return True

    except Exception as e:

        logger.error(
            f"Failed to merge PDFs: {e}"
        )

        return False


# ============================================================
# SPLIT PDF
# ============================================================

def split_pdf(
    path: str,
    output_dir: str,
    max_pages_per_file: int = 10
) -> List[str]:

    output_paths = []

    try:

        os.makedirs(
            output_dir,
            exist_ok=True
        )

        with open(
            path,
            "rb"
        ) as file:

            reader = PdfReader(file)

            total_pages = len(
                reader.pages
            )

            for start_page in range(
                0,
                total_pages,
                max_pages_per_file
            ):

                end_page = min(
                    start_page
                    + max_pages_per_file,
                    total_pages
                )

                writer = PdfWriter()

                for page_index in range(
                    start_page,
                    end_page
                ):

                    writer.add_page(
                        reader.pages[
                            page_index
                        ]
                    )

                output_path = os.path.join(
                    output_dir,
                    f"{Path(path).stem}"
                    f"_part_"
                    f"{start_page // max_pages_per_file + 1}"
                    f".pdf"
                )

                with open(
                    output_path,
                    "wb"
                ) as output:

                    writer.write(output)

                output_paths.append(
                    output_path
                )

        logger.info(
            f"Split PDF into "
            f"{len(output_paths)} files"
        )

        return output_paths

    except Exception as e:

        logger.error(
            f"Failed to split PDF: {e}"
        )

        return []


# ============================================================
# BACKWARD COMPATIBILITY
# ============================================================

def extract_text_from_pdf_simple(
    path: str
) -> str:

    return extract_text_from_pdf(
        path,
        use_ocr=False
    )


# ============================================================
# OCR STATUS
# ============================================================

def get_ocr_status() -> Dict[str, Any]:

    status = {
        "python_packages_available": OCR_AVAILABLE,
        "tesseract_available": False,
        "poppler_available": False,
    }

    # Check Tesseract
    if OCR_AVAILABLE:

        try:

            pytesseract.get_tesseract_version()

            status[
                "tesseract_available"
            ] = True

        except Exception:

            pass

        # Poppler is indirectly tested by
        # attempting to access pdf2image.
        try:

            from pdf2image.pdf2image import (
                pdfinfo_from_path
            )

            status[
                "poppler_available"
            ] = True

        except Exception:

            pass

    status["ocr_ready"] = (
        status["python_packages_available"]
        and status["tesseract_available"]
        and status["poppler_available"]
    )

    return status


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("PDF OCR TEST")
    print("=" * 60)

    print(
        "OCR status:",
        get_ocr_status()
    )

    test_file = "sample.pdf"

    if os.path.exists(test_file):

        valid, message = validate_pdf(
            test_file
        )

        print(
            "Valid:",
            valid
        )

        print(
            "Message:",
            message
        )

        if valid:

            try:

                text = extract_text_from_pdf(
                    test_file,
                    use_ocr=True
                )

                print(
                    f"Extracted characters: "
                    f"{len(text)}"
                )

                print(
                    f"Word count: "
                    f"{get_word_count(text)}"
                )

                print(
                    "\nPreview:"
                )

                print(
                    text[:1000]
                )

            except PDFError as e:

                print(
                    "Extraction error:",
                    e
                )

    else:

        print(
            f"Test file '{test_file}' "
            f"not found."
        )