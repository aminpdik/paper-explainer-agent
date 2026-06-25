from typing import TypedDict


class PaperState(TypedDict, total=False):
    """
    Shared LangGraph state.

    Every node receives this state and returns partial updates.
    LangGraph merges the returned updates into the shared state.
    """

    pdf_path: str
    output_dir: str

    extracted_text: str
    paper_overview_markdown: str
    smooth_explanation_markdown: str

    page_image_paths: list[str]
    visual_region_items: list[dict]

    overview_pdf_path: str
    appendix_pdf_path: str
    final_pdf_path: str

    max_pages: int | None
