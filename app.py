from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import streamlit as st

from paper_explainer.graph import graph


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


APP_TITLE = "Research Paper Explainer"
DEFAULT_OUTPUT_ROOT = Path("outputs") / "streamlit_runs"
WORKFLOW_STEPS = [
    (
        "extract_text",
        "Extracting text from the uploaded PDF...",
    ),
    (
        "generate_paper_overview",
        "Generating the whole-paper explanation...",
    ),
    (
        "render_overview_pdf",
        "Rendering the overview section into the PDF...",
    ),
    (
        "convert_pages_to_images",
        "Converting PDF pages to images and extracting visual regions...",
    ),
    (
        "explain_pages_and_append_to_pdf",
        "Generating a smooth section-by-section explanation and building the final PDF...",
    ),
]
WORKFLOW_PROGRESS = {
    node_name: int(step_number / len(WORKFLOW_STEPS) * 100)
    for step_number, (node_name, _) in enumerate(WORKFLOW_STEPS, start=1)
}
WORKFLOW_MESSAGES = dict(WORKFLOW_STEPS)
WORKFLOW_STEP_INDEX = {
    node_name: step_index
    for step_index, (node_name, _) in enumerate(WORKFLOW_STEPS)
}
SECTION_PROGRESS_START = WORKFLOW_PROGRESS["convert_pages_to_images"]
SECTION_PROGRESS_END = WORKFLOW_PROGRESS["explain_pages_and_append_to_pdf"]


def update_section_progress(
    section_progress_update: dict,
    progress_bar,
    status_message,
) -> None:
    if section_progress_update.get("event") != "section_progress":
        return

    section_number = int(section_progress_update["section_number"])
    total_sections = max(1, int(section_progress_update["total_sections"]))
    section_title = section_progress_update["section_title"]
    status = section_progress_update.get("status")

    if status == "completed":
        completed_sections = section_number
        message = (
            f"Finished section {section_number} of {total_sections}: "
            f"{section_title}."
        )
    else:
        completed_sections = section_number - 1
        message = (
            f"Explaining section {section_number} of {total_sections}: "
            f"{section_title}..."
        )

    section_progress_range = SECTION_PROGRESS_END - SECTION_PROGRESS_START
    progress = SECTION_PROGRESS_START + int(
        completed_sections / total_sections * section_progress_range
    )

    status_message.info(message)
    progress_bar.progress(progress, text=message)


def run_graph_with_progress(initial_state: dict) -> dict:
    starting_message = WORKFLOW_STEPS[0][1]
    progress_bar = st.progress(
        0,
        text=starting_message,
    )
    status_message = st.empty()
    status_message.info(starting_message)
    result = dict(initial_state)

    for stream_update in graph.stream(
        initial_state,
        stream_mode=["updates", "custom"],
    ):
        if isinstance(stream_update, tuple):
            stream_mode, node_update = stream_update
        else:
            stream_mode = "updates"
            node_update = stream_update

        if stream_mode == "custom":
            update_section_progress(
                section_progress_update=node_update,
                progress_bar=progress_bar,
                status_message=status_message,
            )
            continue

        for node_name, updates in node_update.items():
            progress = WORKFLOW_PROGRESS.get(node_name, 0)

            if isinstance(updates, dict):
                result.update(updates)

            step_index = WORKFLOW_STEP_INDEX.get(node_name)

            if step_index is not None and step_index + 1 < len(WORKFLOW_STEPS):
                next_message = WORKFLOW_STEPS[step_index + 1][1]
                status_message.info(next_message)
                progress_bar.progress(progress, text=next_message)
            else:
                message = WORKFLOW_MESSAGES.get(
                    node_name,
                    f"Completed workflow step: {node_name}",
                )
                progress_bar.progress(progress, text=message)

    progress_bar.progress(
        100,
        text="Explanation PDF generation finished.",
    )
    status_message.success("Explanation PDF generation finished.")

    return result


st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
)


st.title(APP_TITLE)
st.write(
    "Upload a research paper PDF. I will create a styled PDF "
    "with a whole-paper overview and a smooth section-by-section explanation."
)


with st.sidebar:
    st.header("Settings")

    max_pages_enabled = st.checkbox(
        "Limit number of pages",
        value=True,
        help="Useful for testing. The explanation will only use the first selected pages.",
    )

    max_pages = None
    if max_pages_enabled:
        max_pages = st.number_input(
            "Maximum pages to explain",
            min_value=1,
            max_value=100,
            value=2,
            step=1,
        )

    st.caption(
        "Tip: first test with 1–2 pages. Then run the full paper after you confirm everything works."
    )


uploaded_file = st.file_uploader(
    "Upload your PDF file",
    type=["pdf"],
)


if uploaded_file is not None:
    st.success("PDF uploaded successfully.")

    safe_stem = Path(uploaded_file.name).stem.replace(" ", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = DEFAULT_OUTPUT_ROOT / f"{safe_stem}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = run_dir / uploaded_file.name
    pdf_path.write_bytes(uploaded_file.getbuffer())

    output_dir = run_dir / "generated"

    initial_state = {
        "pdf_path": str(pdf_path),
        "output_dir": str(output_dir),
        "max_pages": int(max_pages) if max_pages is not None else None,
    }

    run_button = st.button("Generate Explanation PDF", type="primary")

    if run_button:
        result = run_graph_with_progress(initial_state)

        st.success("LangGraph workflow finished.")

        final_pdf_path = Path(result["final_pdf_path"])
        extracted_text = result.get("extracted_text", "")
        page_image_paths = result.get("page_image_paths", [])
        paper_overview_markdown = result.get("paper_overview_markdown", "")
        smooth_explanation_markdown = result.get("smooth_explanation_markdown", "")

        tab1, tab2, tab3, tab4, tab5 = st.tabs(
            [
                "Final PDF",
                "Paper Overview",
                "Smooth Explanation",
                "Extracted Text",
                "Extracted Page Images",
            ]
        )

        with tab1:
            st.subheader("Generated Explanation PDF")

            if final_pdf_path.exists():
                st.write(f"Saved at: `{final_pdf_path}`")

                st.download_button(
                    label="Download Final PDF",
                    data=final_pdf_path.read_bytes(),
                    file_name="paper_explanation.pdf",
                    mime="application/pdf",
                )
            else:
                st.error("The final PDF was not found.")

        with tab2:
            st.subheader("Whole-Paper Overview")

            if paper_overview_markdown.strip():
                st.markdown(paper_overview_markdown)
            else:
                st.warning("No paper overview was generated.")

        with tab3:
            st.subheader("Smooth Section-by-Section Explanation")

            if smooth_explanation_markdown.strip():
                st.markdown(smooth_explanation_markdown)
            else:
                st.warning("No smooth explanation was generated.")

        with tab4:
            st.subheader("Extracted Text")

            if extracted_text.strip():
                st.text_area(
                    "Text from PDF",
                    extracted_text,
                    height=500,
                )

                st.download_button(
                    label="Download Extracted Text",
                    data=extracted_text,
                    file_name="extracted_text.txt",
                    mime="text/plain",
                )
            else:
                st.warning(
                    "No text was extracted. This PDF may be scanned or image-only. "
                    "For scanned PDFs, you need OCR."
                )

        with tab5:
            st.subheader("Extracted Page Images")

            if page_image_paths:
                for page_number, image_path in enumerate(page_image_paths, start=1):
                    image_path = Path(image_path)
                    st.write(f"Page {page_number}")

                    if image_path.exists():
                        st.image(str(image_path), use_container_width=True)
                    else:
                        st.warning(f"Image file not found: {image_path}")
            else:
                st.warning("No page images were created.")
