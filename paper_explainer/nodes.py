import logging
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
try:
    from langgraph.config import get_stream_writer
except ImportError:
    get_stream_writer = None

from paper_explainer.pdf_renderer import StyledPdfRenderer
from paper_explainer.pdf_utils import (
    append_pdf_to_existing_pdf,
    convert_pdf_pages_to_images,
    ensure_directory,
    extract_text_from_pdf,
    extract_visual_regions_from_pdf,
    image_path_to_data_url,
    validate_pdf_path,
)
from paper_explainer.prompts import (
    PAPER_CHUNK_SUMMARY_SYSTEM_PROMPT,
    PAPER_FINAL_OVERVIEW_FROM_CHUNKS_SYSTEM_PROMPT,
    PAPER_OVERVIEW_SYSTEM_PROMPT,
    SECTION_EXPLANATION_SYSTEM_PROMPT,
    SECTION_EXPLANATION_USER_PROMPT_TEMPLATE,
)
from paper_explainer.state import PaperState


logger = logging.getLogger(__name__)

MAX_DIRECT_OVERVIEW_CHARS = 50000
OVERVIEW_CHUNK_SIZE_CHARS = 18000
OVERVIEW_CHUNK_OVERLAP_CHARS = 1200
SECTION_CHUNK_SIZE_CHARS = 28000
SECTION_CHUNK_OVERLAP_CHARS = 1000
MAX_SECTION_MEMORY_CHARS = 7000
REFERENCE_SECTION_TITLES = {
    "references",
    "reference",
    "bibliography",
}
SECTION_HEADING_PATTERN = re.compile(
    r"(?im)^\s*(?:\d+\.?\s+|[IVX]+\.?\s+)?("
    r"abstract|introduction|related work|background|preliminaries|"
    r"method|methods|methodology|approach|proposed method|proposed approach|"
    r"model|framework|implementation|experiments|experimental setup|"
    r"evaluation|results|discussion|limitations|conclusion|conclusions|"
    r"references|reference|bibliography|appendix"
    r")\s*$"
)
PAGE_MARKER_PATTERN = re.compile(r"\[PAGE\s+(\d+)\]", re.IGNORECASE)


@dataclass
class PaperExplainerNodes:
    """
    Contains all LangGraph node functions.

    We keep nodes inside a class so dependencies like the LLM and PDF renderer
    are injected once and reused cleanly.
    """

    llm: Any
    pdf_renderer: StyledPdfRenderer

    def extract_text_node(self, state: PaperState) -> PaperState:
        pdf_path = validate_pdf_path(state["pdf_path"])
        max_pages = state.get("max_pages")

        logger.info("Extracting text from PDF: %s", pdf_path)

        extracted_text = extract_text_from_pdf(
            pdf_path=pdf_path,
            max_pages=max_pages,
        )

        return {
            "extracted_text": extracted_text,
        }

    def generate_paper_overview_node(self, state: PaperState) -> PaperState:
        extracted_text = state["extracted_text"]

        logger.info("Generating whole-paper overview.")

        if len(extracted_text) > MAX_DIRECT_OVERVIEW_CHARS:
            overview_markdown = self._generate_chunked_paper_overview(extracted_text)

            return {
                "paper_overview_markdown": overview_markdown,
            }

        messages = [
            SystemMessage(content=PAPER_OVERVIEW_SYSTEM_PROMPT),
            HumanMessage(content=extracted_text),
        ]

        response = self.llm.invoke(messages)

        return {
            "paper_overview_markdown": response.content,
        }

    def _generate_chunked_paper_overview(self, extracted_text: str) -> str:
        chunks = self._split_text_into_chunks(
            text=extracted_text,
            chunk_size=OVERVIEW_CHUNK_SIZE_CHARS,
            overlap=OVERVIEW_CHUNK_OVERLAP_CHARS,
        )

        logger.info("Paper text is long. Summarizing %s chunks first.", len(chunks))

        chunk_summaries: list[str] = []

        for chunk_number, chunk_text in enumerate(chunks, start=1):
            logger.info("Summarizing paper text chunk %s of %s.", chunk_number, len(chunks))

            messages = [
                SystemMessage(content=PAPER_CHUNK_SUMMARY_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Chunk {chunk_number} of {len(chunks)} from the paper:\n\n"
                        f"{chunk_text}"
                    )
                ),
            ]

            response = self.llm.invoke(messages)

            chunk_summaries.append(
                f"# Chunk {chunk_number} Summary\n\n{response.content}"
            )

        combined_summaries = "\n\n---\n\n".join(chunk_summaries)

        while len(combined_summaries) > MAX_DIRECT_OVERVIEW_CHARS:
            logger.info("Chunk summaries are still long. Compressing summaries again.")
            combined_summaries = self._compress_long_summary_text(combined_summaries)

        final_messages = [
            SystemMessage(content=PAPER_FINAL_OVERVIEW_FROM_CHUNKS_SYSTEM_PROMPT),
            HumanMessage(content=combined_summaries),
        ]

        final_response = self.llm.invoke(final_messages)
        return final_response.content

    def _compress_long_summary_text(self, summary_text: str) -> str:
        chunks = self._split_text_into_chunks(
            text=summary_text,
            chunk_size=OVERVIEW_CHUNK_SIZE_CHARS,
            overlap=OVERVIEW_CHUNK_OVERLAP_CHARS,
        )

        compressed_summaries: list[str] = []

        for chunk_number, chunk_text in enumerate(chunks, start=1):
            messages = [
                SystemMessage(content=PAPER_CHUNK_SUMMARY_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        "This text contains summaries from a long paper. "
                        "Compress it while preserving the main research area, "
                        "problem, proposed approach, important methods, and results.\n\n"
                        f"Summary chunk {chunk_number} of {len(chunks)}:\n\n"
                        f"{chunk_text}"
                    )
                ),
            ]

            response = self.llm.invoke(messages)
            compressed_summaries.append(response.content)

        return "\n\n---\n\n".join(compressed_summaries)

    @staticmethod
    def _split_text_into_chunks(
        text: str,
        chunk_size: int,
        overlap: int,
    ) -> list[str]:
        text = text.replace("\r\n", "\n").strip()

        if len(text) <= chunk_size:
            return [text]

        paragraphs = [paragraph.strip() for paragraph in text.split("\n\n")]
        chunks: list[str] = []
        current_chunk = ""

        for paragraph in paragraphs:
            if not paragraph:
                continue

            if len(paragraph) > chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""

                for start in range(0, len(paragraph), chunk_size - overlap):
                    paragraph_chunk = paragraph[start : start + chunk_size]
                    chunks.append(paragraph_chunk.strip())

                continue

            next_chunk = f"{current_chunk}\n\n{paragraph}".strip()

            if len(next_chunk) <= chunk_size:
                current_chunk = next_chunk
                continue

            chunks.append(current_chunk.strip())
            overlap_text = current_chunk[-overlap:] if overlap > 0 else ""
            current_chunk = f"{overlap_text}\n\n{paragraph}".strip()

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def render_overview_pdf_node(self, state: PaperState) -> PaperState:
        pdf_path = Path(state["pdf_path"])
        output_dir = ensure_directory(state["output_dir"])

        overview_pdf_path = output_dir / "paper_explanation.pdf"

        logger.info("Rendering overview PDF: %s", overview_pdf_path)

        self.pdf_renderer.render_markdown_to_pdf(
            markdown_text=state["paper_overview_markdown"],
            output_pdf_path=overview_pdf_path,
            document_name=pdf_path.name,
            title="Paper Overview",
        )

        return {
            "overview_pdf_path": str(overview_pdf_path),
            "final_pdf_path": str(overview_pdf_path),
        }

    def convert_pages_to_images_node(self, state: PaperState) -> PaperState:
        pdf_path = validate_pdf_path(state["pdf_path"])
        output_dir = ensure_directory(Path(state["output_dir"]) / "page_images")
        visual_output_dir = ensure_directory(Path(state["output_dir"]) / "visual_regions")

        max_pages = state.get("max_pages")

        logger.info("Converting PDF pages to images.")

        image_paths = convert_pdf_pages_to_images(
            pdf_path=pdf_path,
            output_dir=output_dir,
            dpi=300,
            max_pages=max_pages,
        )

        logger.info("Cropping figures and tables from PDF pages.")

        visual_region_items = extract_visual_regions_from_pdf(
            pdf_path=pdf_path,
            output_dir=visual_output_dir,
            dpi=220,
            max_pages=max_pages,
        )

        return {
            "page_image_paths": image_paths,
            "visual_region_items": visual_region_items,
        }

    def explain_pages_and_append_to_pdf_node(self, state: PaperState) -> PaperState:
        """
        Generate one smooth section-by-section explanation and append it to the
        overview PDF.

        Final PDF structure:
        1. Paper Overview
        2. Smooth section-by-section explanation
        """

        pdf_path = Path(state["pdf_path"])
        output_dir = ensure_directory(state["output_dir"])

        final_pdf_path = state["final_pdf_path"]
        extracted_text = state["extracted_text"]
        page_image_paths = state.get("page_image_paths", [])
        visual_region_items = state.get("visual_region_items", [])
        paper_overview = state["paper_overview_markdown"]

        logger.info("Generating smooth section-by-section explanation.")

        paper_sections = self._split_paper_into_sections(extracted_text)
        section_explanations: list[str] = []
        previous_section_memory = "No previous sections have been explained yet."
        stream_writer = self._get_stream_writer()

        for section_number, section in enumerate(paper_sections, start=1):
            section_title = section["title"]
            section_text = section["text"]
            section_pages = section["pages"]

            logger.info(
                "Explaining section %s of %s: %s",
                section_number,
                len(paper_sections),
                section_title,
            )

            self._emit_section_progress(
                stream_writer=stream_writer,
                section_number=section_number,
                total_sections=len(paper_sections),
                section_title=section_title,
                status="started",
            )

            user_prompt = SECTION_EXPLANATION_USER_PROMPT_TEMPLATE.format(
                whole_paper_summary=paper_overview,
                previous_section_memory=previous_section_memory,
                section_number=section_number,
                total_sections=len(paper_sections),
                section_title=section_title,
                section_text=section_text,
            )

            messages = [
                SystemMessage(content=SECTION_EXPLANATION_SYSTEM_PROMPT),
                HumanMessage(
                    content=self._build_section_message_content(
                        user_prompt=user_prompt,
                        page_image_paths=page_image_paths,
                        section_pages=section_pages,
                    )
                ),
            ]

            response = self.llm.invoke(messages)

            visual_regions_markdown = self._build_visual_regions_markdown_for_pages(
                visual_region_items=visual_region_items,
                page_numbers=section_pages,
                section_title=section_title,
            )

            section_markdown = response.content

            if visual_regions_markdown:
                section_markdown = f"{section_markdown}\n\n{visual_regions_markdown}"

            section_explanations.append(section_markdown)
            previous_section_memory = self._update_section_memory(
                previous_section_memory=previous_section_memory,
                section_title=section_title,
                section_explanation=section_markdown,
            )

            self._emit_section_progress(
                stream_writer=stream_writer,
                section_number=section_number,
                total_sections=len(paper_sections),
                section_title=section_title,
                status="completed",
            )

        appendix_markdown = "# Smooth Paper Explanation\n\n" + "\n\n---\n\n".join(
            section_explanations
        )

        appendix_pdf_path = output_dir / "smooth_paper_explanation.pdf"

        logger.info("Rendering smooth explanation appendix PDF: %s", appendix_pdf_path)

        self.pdf_renderer.render_markdown_to_pdf(
            markdown_text=appendix_markdown,
            output_pdf_path=appendix_pdf_path,
            document_name=pdf_path.name,
            title="Smooth Paper Explanation",
        )

        logger.info("Appending appendix PDF to final PDF.")

        append_pdf_to_existing_pdf(
            existing_pdf_path=final_pdf_path,
            pdf_to_append_path=appendix_pdf_path,
        )

        return {
            "appendix_pdf_path": str(appendix_pdf_path),
            "final_pdf_path": final_pdf_path,
            "smooth_explanation_markdown": appendix_markdown,
        }

    def _split_paper_into_sections(self, extracted_text: str) -> list[dict[str, Any]]:
        text = extracted_text.strip()
        matches = list(SECTION_HEADING_PATTERN.finditer(text))

        if not matches:
            chunks = self._split_text_into_chunks(
                text=text,
                chunk_size=SECTION_CHUNK_SIZE_CHARS,
                overlap=SECTION_CHUNK_OVERLAP_CHARS,
            )
            return [
                {
                    "title": f"Paper Explanation Part {index}",
                    "text": chunk,
                    "pages": self._extract_page_numbers(chunk),
                }
                for index, chunk in enumerate(chunks, start=1)
            ]

        sections: list[dict[str, Any]] = []
        preamble = text[: matches[0].start()].strip()

        for index, match in enumerate(matches):
            raw_title = match.group(1)
            normalized_title = self._normalize_section_title(raw_title)

            if normalized_title.lower() in REFERENCE_SECTION_TITLES:
                break

            section_start = match.end()
            section_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            section_text = text[section_start:section_end].strip()

            if preamble and index == 0:
                section_text = f"{preamble}\n\n{section_text}".strip()

            if not section_text:
                continue

            section_chunks = self._split_text_into_chunks(
                text=section_text,
                chunk_size=SECTION_CHUNK_SIZE_CHARS,
                overlap=SECTION_CHUNK_OVERLAP_CHARS,
            )

            if len(section_chunks) == 1:
                sections.append(
                    {
                        "title": normalized_title,
                        "text": section_chunks[0],
                        "pages": self._extract_page_numbers(section_chunks[0]),
                    }
                )
                continue

            for chunk_index, section_chunk in enumerate(section_chunks, start=1):
                sections.append(
                    {
                        "title": f"{normalized_title} Part {chunk_index}",
                        "text": section_chunk,
                        "pages": self._extract_page_numbers(section_chunk),
                    }
                )

        if sections:
            return sections

        return [
            {
                "title": "Paper Explanation",
                "text": text,
                "pages": self._extract_page_numbers(text),
            }
        ]

    @staticmethod
    def _normalize_section_title(raw_title: str) -> str:
        words = raw_title.strip().split()
        return " ".join(word.capitalize() for word in words)

    @staticmethod
    def _extract_page_numbers(text: str) -> set[int]:
        return {int(match.group(1)) for match in PAGE_MARKER_PATTERN.finditer(text)}

    @staticmethod
    def _update_section_memory(
        previous_section_memory: str,
        section_title: str,
        section_explanation: str,
    ) -> str:
        if previous_section_memory == "No previous sections have been explained yet.":
            previous_section_memory = ""

        combined_memory = (
            f"{previous_section_memory}\n\n"
            f"Previously explained section: {section_title}\n"
            f"{section_explanation}"
        ).strip()

        if len(combined_memory) <= MAX_SECTION_MEMORY_CHARS:
            return combined_memory

        return combined_memory[-MAX_SECTION_MEMORY_CHARS:]

    def _build_section_message_content(
        self,
        user_prompt: str,
        page_image_paths: list[str],
        section_pages: set[int],
    ) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": user_prompt,
            }
        ]

        for page_number in sorted(section_pages):
            page_index = page_number - 1

            if page_index < 0 or page_index >= len(page_image_paths):
                continue

            content.append(
                {
                    "type": "text",
                    "text": (
                        f"Page {page_number} image for this section. "
                        "Use this image to verify formulas, equations, figures, "
                        "tables, captions, and any content that may be missing "
                        "or poorly extracted from the text."
                    ),
                }
            )
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_path_to_data_url(page_image_paths[page_index]),
                    },
                }
            )

        return content

    @staticmethod
    def _get_stream_writer():
        if get_stream_writer is None:
            return None

        try:
            return get_stream_writer()
        except RuntimeError:
            return None

    @staticmethod
    def _emit_section_progress(
        stream_writer,
        section_number: int,
        total_sections: int,
        section_title: str,
        status: str,
    ) -> None:
        if stream_writer is None:
            return

        stream_writer(
            {
                "event": "section_progress",
                "section_number": section_number,
                "total_sections": total_sections,
                "section_title": section_title,
                "status": status,
            }
        )

    def _build_visual_regions_markdown_for_pages(
        self,
        visual_region_items: list[dict[str, Any]],
        page_numbers: set[int],
        section_title: str,
    ) -> str:
        if not page_numbers:
            return ""

        section_visual_items = [
            item
            for item in visual_region_items
            if item.get("page_number") in page_numbers
        ]

        if not section_visual_items:
            return ""

        visual_html_blocks: list[str] = []

        for item in section_visual_items:
            image_data_url = image_path_to_data_url(item["path"])
            kind = str(item.get("kind", "visual")).title()
            label = str(item.get("label", kind))
            page_number = item.get("page_number")
            caption = (
                f"Extracted {kind.lower()} from the {section_title} section "
                f"(page {page_number}): {label}"
            )

            visual_html_blocks.append(
                f"""
<figure class="visual-region">
    <img src="{image_data_url}" alt="{escape(caption)}">
    <figcaption>{escape(caption)}</figcaption>
</figure>
"""
            )

        return "\n\n### Extracted Figures and Tables From This Section\n\n" + "\n\n".join(
            visual_html_blocks
        )
