"""
Paper Explainer Package

This package builds a LangGraph workflow that:
1. Extracts text from a research paper PDF.
2. Creates a whole-paper overview.
3. Renders that overview into a styled PDF.
4. Converts each PDF page into an image.
5. Sends each page image to a vision-capable LLM.
6. Generates page-by-page explanations.
7. Appends those explanations to the generated PDF.
"""
