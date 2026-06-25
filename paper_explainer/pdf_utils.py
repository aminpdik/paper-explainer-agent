import base64
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

import fitz
from langchain_community.document_loaders import PyPDFLoader


def ensure_directory(directory_path: str | Path) -> Path:
    """
    Create a directory if it does not already exist.
    Return the directory as a Path object.
    """

    directory = Path(directory_path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def validate_pdf_path(pdf_path: str | Path) -> Path:
    """
    Validate that the given PDF path exists and is a PDF file.
    """

    path = Path(pdf_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, but got: {path}")

    return path


def clean_text_for_llm(text: str) -> str:
    return text.encode("utf-8", errors="ignore").decode("utf-8")


def extract_text_from_pdf(
    pdf_path: str | Path,
    max_pages: int | None = None,
) -> str:
    """
    Extract text from all pages of the PDF using PyPDFLoader.
    """

    pdf_path = validate_pdf_path(pdf_path)

    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()

    if max_pages is not None:
        pages = pages[:max_pages]

    page_texts = [
        f"[PAGE {page_number}]\n{page.page_content}"
        for page_number, page in enumerate(pages, start=1)
    ]

    extracted_text = "\n\n".join(page_texts)
    extracted_text=clean_text_for_llm(extracted_text)

    if not extracted_text.strip():
        raise ValueError(
            "No text was extracted from the PDF. "
            "The PDF may be scanned or image-only."
        )

    return extracted_text


def convert_pdf_pages_to_images(
    pdf_path: str | Path,
    output_dir: str | Path,
    dpi: int = 200,
    max_pages: int | None = None,
) -> list[str]:
    """
    Convert each PDF page into a PNG image.

    Returns:
        A list of image paths.
    """

    pdf_path = validate_pdf_path(pdf_path)
    output_dir = ensure_directory(output_dir)

    document = fitz.open(str(pdf_path))
    image_paths: list[str] = []

    try:
        total_pages = len(document)

        if max_pages is not None:
            total_pages = min(total_pages, max_pages)

        for page_index in range(total_pages):
            page = document[page_index]
            pixmap = page.get_pixmap(dpi=dpi)

            image_path = output_dir / f"page_{page_index + 1:03d}.png"
            pixmap.save(str(image_path))

            image_paths.append(str(image_path))

    finally:
        document.close()

    return image_paths


def image_path_to_data_url(image_path: str | Path) -> str:
    """
    Convert a local image file into a base64 data URL.

    LLMs cannot read your local path directly, so we send the actual image content.
    """

    path = Path(image_path)

    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    mime_type, _ = mimetypes.guess_type(str(path))

    if mime_type is None:
        mime_type = "image/png"

    with open(path, "rb") as image_file:
        encoded_image = base64.b64encode(image_file.read()).decode("utf-8")

    return f"data:{mime_type};base64,{encoded_image}"


def extract_visual_regions_from_pdf(
    pdf_path: str | Path,
    output_dir: str | Path,
    dpi: int = 220,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    """
    Crop tables and figure-like image regions from the PDF as PNG files.

    Tables are detected with pdfplumber table bounding boxes.
    Figures are detected from image blocks in the PDF page layout.

    Returns a list like:
        {
            "kind": "table" or "figure",
            "page_number": 1,
            "path": ".../page_001_table_001.png",
            "label": "Table 1"
        }
    """

    pdf_path = validate_pdf_path(pdf_path)
    output_dir = ensure_directory(output_dir)

    visual_items: list[dict[str, Any]] = []

    visual_items.extend(
        _extract_table_regions_from_pdf(
            pdf_path=pdf_path,
            output_dir=output_dir,
            dpi=dpi,
            max_pages=max_pages,
        )
    )
    visual_items.extend(
        _extract_figure_regions_from_pdf(
            pdf_path=pdf_path,
            output_dir=output_dir,
            dpi=dpi,
            max_pages=max_pages,
        )
    )

    return sorted(
        visual_items,
        key=lambda item: (item["page_number"], item["kind"], item["label"]),
    )


def _extract_table_regions_from_pdf(
    pdf_path: Path,
    output_dir: Path,
    dpi: int,
    max_pages: int | None,
) -> list[dict[str, Any]]:
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError(
            "pdfplumber is required to crop tables as images. "
            "Install it with: pip install pdfplumber"
        ) from exc

    visual_items: list[dict[str, Any]] = []

    document = fitz.open(str(pdf_path))

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            total_pages = len(pdf.pages)

            if max_pages is not None:
                total_pages = min(total_pages, max_pages)

            for page_index in range(total_pages):
                plumber_page = pdf.pages[page_index]
                fitz_page = document[page_index]

                tables = plumber_page.find_tables()

                for table_index, table in enumerate(tables, start=1):
                    x0, top, x1, bottom = table.bbox
                    bbox = fitz.Rect(x0, top, x1, bottom)

                    output_path = (
                        output_dir
                        / f"page_{page_index + 1:03d}_table_{table_index:02d}.png"
                    )

                    _crop_page_region_to_image(
                        page=fitz_page,
                        bbox=bbox,
                        output_path=output_path,
                        dpi=dpi,
                        padding=8,
                    )

                    visual_items.append(
                        {
                            "kind": "table",
                            "page_number": page_index + 1,
                            "path": str(output_path),
                            "label": f"Table {table_index}",
                        }
                    )

    finally:
        document.close()

    return visual_items


def _extract_figure_regions_from_pdf(
    pdf_path: Path,
    output_dir: Path,
    dpi: int,
    max_pages: int | None,
) -> list[dict[str, Any]]:
    document = fitz.open(str(pdf_path))
    visual_items: list[dict[str, Any]] = []

    try:
        total_pages = len(document)

        if max_pages is not None:
            total_pages = min(total_pages, max_pages)

        for page_index in range(total_pages):
            page = document[page_index]
            page_dict = page.get_text("dict")
            caption_bboxes = _find_caption_bboxes(page_dict, caption_kind="figure")

            figure_index = 0

            for block in page_dict.get("blocks", []):
                if block.get("type") != 1:
                    continue

                bbox = fitz.Rect(block["bbox"])

                if _is_small_region(bbox):
                    continue

                bbox = _merge_with_nearby_caption(
                    bbox=bbox,
                    caption_bboxes=caption_bboxes,
                )

                figure_index += 1
                output_path = (
                    output_dir
                    / f"page_{page_index + 1:03d}_figure_{figure_index:02d}.png"
                )

                _crop_page_region_to_image(
                    page=page,
                    bbox=bbox,
                    output_path=output_path,
                    dpi=dpi,
                    padding=10,
                )

                visual_items.append(
                    {
                        "kind": "figure",
                        "page_number": page_index + 1,
                        "path": str(output_path),
                        "label": f"Figure {figure_index}",
                    }
                )

    finally:
        document.close()

    return visual_items


def _crop_page_region_to_image(
    page: fitz.Page,
    bbox: fitz.Rect,
    output_path: str | Path,
    dpi: int,
    padding: float = 0,
) -> None:
    page_rect = page.rect
    crop_rect = fitz.Rect(
        max(page_rect.x0, bbox.x0 - padding),
        max(page_rect.y0, bbox.y0 - padding),
        min(page_rect.x1, bbox.x1 + padding),
        min(page_rect.y1, bbox.y1 + padding),
    )

    pixmap = page.get_pixmap(dpi=dpi, clip=crop_rect)
    pixmap.save(str(output_path))


def _find_caption_bboxes(
    page_dict: dict[str, Any],
    caption_kind: str,
) -> list[fitz.Rect]:
    if caption_kind == "figure":
        caption_pattern = re.compile(r"^\s*(fig\.|figure)\s*\d+", re.IGNORECASE)
    else:
        caption_pattern = re.compile(r"^\s*table\s*\d+", re.IGNORECASE)

    caption_bboxes: list[fitz.Rect] = []

    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue

        text = _text_from_block(block).strip()

        if caption_pattern.search(text):
            caption_bboxes.append(fitz.Rect(block["bbox"]))

    return caption_bboxes


def _text_from_block(block: dict[str, Any]) -> str:
    lines: list[str] = []

    for line in block.get("lines", []):
        spans = line.get("spans", [])
        line_text = "".join(span.get("text", "") for span in spans)
        lines.append(line_text)

    return "\n".join(lines)


def _merge_with_nearby_caption(
    bbox: fitz.Rect,
    caption_bboxes: list[fitz.Rect],
    max_distance: float = 110,
) -> fitz.Rect:
    merged_bbox = fitz.Rect(bbox)

    for caption_bbox in caption_bboxes:
        caption_below = 0 <= caption_bbox.y0 - bbox.y1 <= max_distance
        caption_above = 0 <= bbox.y0 - caption_bbox.y1 <= max_distance
        overlaps_horizontally = (
            min(bbox.x1, caption_bbox.x1) - max(bbox.x0, caption_bbox.x0)
        ) > 0

        if overlaps_horizontally and (caption_below or caption_above):
            merged_bbox.include_rect(caption_bbox)

    return merged_bbox


def _is_small_region(bbox: fitz.Rect) -> bool:
    width = bbox.x1 - bbox.x0
    height = bbox.y1 - bbox.y0
    area = width * height

    return width < 90 or height < 60 or area < 10000


def append_pdf_to_existing_pdf(
    existing_pdf_path: str | Path,
    pdf_to_append_path: str | Path,
) -> str:
    """
    Append one PDF to the end of another PDF.

    The final result is saved back into existing_pdf_path.

    Example:
        existing_pdf_path = paper_overview.pdf
        pdf_to_append_path = page_explanations.pdf

        Result:
        paper_overview.pdf now contains both sections.
    """

    existing_pdf_path = Path(existing_pdf_path)
    pdf_to_append_path = Path(pdf_to_append_path)

    if not existing_pdf_path.exists():
        raise FileNotFoundError(f"Main PDF not found: {existing_pdf_path}")

    if not pdf_to_append_path.exists():
        raise FileNotFoundError(f"PDF to append not found: {pdf_to_append_path}")

    temporary_output_path = existing_pdf_path.with_name(
        f"{existing_pdf_path.stem}_temp{existing_pdf_path.suffix}"
    )

    main_document = fitz.open(str(existing_pdf_path))
    appendix_document = fitz.open(str(pdf_to_append_path))

    try:
        main_document.insert_pdf(appendix_document)
        main_document.save(
            str(temporary_output_path),
            garbage=4,
            deflate=True,
        )

    finally:
        appendix_document.close()
        main_document.close()

    os.replace(temporary_output_path, existing_pdf_path)

    return str(existing_pdf_path)
