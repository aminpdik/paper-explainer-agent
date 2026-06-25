from langgraph.graph import END, START, StateGraph

from paper_explainer.config import MyLLM
from paper_explainer.nodes import PaperExplainerNodes
from paper_explainer.pdf_renderer import StyledPdfRenderer
from paper_explainer.state import PaperState


def build_paper_explainer_graph():
    """
    Build and compile the LangGraph workflow.

    Workflow:

    START
      ↓
    extract_text
      ↓
    generate_paper_overview
      ↓
    render_overview_pdf
      ↓
    convert_pages_to_images
      ↓
    explain_pages_and_append_to_pdf
      ↓
    END
    """

    pdf_renderer = StyledPdfRenderer()

    nodes = PaperExplainerNodes(
        llm=MyLLM,
        pdf_renderer=pdf_renderer,
    )

    builder = StateGraph(PaperState)

    builder.add_node("extract_text", nodes.extract_text_node)
    builder.add_node("generate_paper_overview", nodes.generate_paper_overview_node)
    builder.add_node("render_overview_pdf", nodes.render_overview_pdf_node)
    builder.add_node("convert_pages_to_images", nodes.convert_pages_to_images_node)
    builder.add_node(
        "explain_pages_and_append_to_pdf",
        nodes.explain_pages_and_append_to_pdf_node,
    )

    builder.add_edge(START, "extract_text")
    builder.add_edge("extract_text", "generate_paper_overview")
    builder.add_edge("generate_paper_overview", "render_overview_pdf")
    builder.add_edge("render_overview_pdf", "convert_pages_to_images")
    builder.add_edge("convert_pages_to_images", "explain_pages_and_append_to_pdf")
    builder.add_edge("explain_pages_and_append_to_pdf", END)

    return builder.compile()


graph = build_paper_explainer_graph()
