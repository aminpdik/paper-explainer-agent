# Research Paper Explainer (In progress)

Research Paper Explainer is a **LangGraph + Streamlit** application that turns a research paper PDF into a beginner-friendly explanation document.

The app extracts text from a PDF, creates a high-level paper overview, converts paper pages into images, checks visual content such as equations, figures, and tables with a vision-capable LLM, and generates a styled PDF containing a smooth section-by-section explanation.

## Why I Built This

Research papers are often difficult to read because they combine dense writing, equations, figures, tables, and field-specific terminology. This project is designed to help students, researchers, and technical readers understand papers more easily by creating a guided explanation that feels like a teacher walking through the paper step by step.

## Features

- Upload a research paper PDF through a Streamlit interface
- Extract text from the PDF using LangChain's PDF loader
- Generate a whole-paper overview with three sections:
  - Research area
  - Problem
  - Proposed approach
- Split long papers into manageable chunks before summarization
- Convert PDF pages into high-resolution images
- Extract figure-like and table-like visual regions from the paper
- Use a vision-capable LLM to verify formulas, figures, tables, captions, and visual content
- Generate a smooth section-by-section explanation instead of disconnected page-by-page notes
- Preserve context across sections using previous-section memory
- Render the final explanation as a styled PDF
- Show progress updates while the LangGraph workflow runs
- Download the final generated explanation PDF from the Streamlit UI

## Tech Stack

- **Python**
- **Streamlit** for the web interface
- **LangGraph** for workflow orchestration
- **LangChain** for LLM and PDF-loading utilities
- **OpenAI / Cerebras** as supported LLM providers
- **PyMuPDF** for PDF page rendering and PDF merging
- **pdfplumber** for table-region detection
- **Playwright** for rendering Markdown/HTML into PDF
- **MathJax** for rendering LaTeX equations in the generated PDF

## Project Structure

```text
.
├── app.py                         # Streamlit application
├── paper_explainer/
│   ├── __init__.py                 # Package description
│   ├── config.py                   # LLM provider configuration
│   ├── graph.py                    # LangGraph workflow definition
│   ├── nodes.py                    # Workflow node implementations
│   ├── pdf_renderer.py             # Styled Markdown-to-PDF renderer
│   ├── pdf_utils.py                # PDF text, image, table, and figure utilities
│   ├── prompts.py                  # System and user prompts
│   └── state.py                    # Shared LangGraph state schema
└── outputs/                        # Generated outputs, created at runtime
```

## Workflow

The application follows this LangGraph pipeline:

```text
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
```

### 1. Extract Text

The app validates the uploaded PDF path and extracts text from the paper. Each page is marked with a page label so the system can later connect text sections back to page images.

### 2. Generate Paper Overview

The LLM creates a beginner-friendly overview of the full paper. For long papers, the text is first split into chunks, each chunk is summarized, and then the chunk summaries are combined into one final overview.

### 3. Render Overview PDF

The overview is converted from Markdown into a styled PDF using Playwright and MathJax.

### 4. Convert Pages to Images

The original PDF pages are converted into PNG images. The app also attempts to crop tables and figure-like visual regions from the PDF.

### 5. Generate Smooth Section Explanation

The paper is split into logical sections such as introduction, method, experiments, results, and conclusion. For each section, the LLM receives:

- The whole-paper overview
- The current section text
- Memory from previous sections
- Page images related to that section
- Extracted figure and table regions when available

This allows the explanation to be more continuous and accurate, especially when equations or visuals are not extracted cleanly as text.

### 6. Build Final PDF

The final output PDF contains:

1. A whole-paper overview
2. A smooth section-by-section paper explanation
3. Extracted visual regions where available

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git
cd YOUR_REPOSITORY_NAME
```

### 2. Create a virtual environment

On macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install streamlit langgraph langchain langchain-openai langchain-cerebras langchain-community python-dotenv pymupdf pdfplumber markdown playwright pypdf
```

Then install the Playwright browser:

```bash
playwright install chromium
```

## Environment Variables

Create a `.env` file in the project root.

### OpenAI Example

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o
```

### Cerebras Example

```env
LLM_PROVIDER=cerebras
CEREBRAS_API_KEY=your_cerebras_api_key
CEREBRAS_MODEL=gpt-oss-120b
```

> Note: The section explanation step can send page images to the model. For best results, use a model that supports image input.

## Running the App

```bash
streamlit run app.py
```

Then open the local Streamlit URL shown in your terminal.

## How to Use

1. Upload a research paper PDF.
2. Choose whether to limit the number of pages.
3. Click **Generate Explanation PDF**.
4. Wait for the workflow to finish.
5. Review the generated overview, smooth explanation, extracted text, and page images in the Streamlit tabs.
6. Download the final explanation PDF.

## Output Files

Generated files are saved under:

```text
outputs/streamlit_runs/<paper_name>_<timestamp>/generated/
```

Typical outputs include:

```text
paper_explanation.pdf              # Final generated PDF
smooth_paper_explanation.pdf       # Section-by-section explanation appendix
page_images/                       # Rendered PDF page images
visual_regions/                    # Cropped figures and tables
```

## Notes and Limitations

- Scanned or image-only PDFs may not work unless OCR is added.
- Very long papers can require many LLM calls and may increase cost.
- Equation quality depends on both PDF text extraction and image readability.
- Figure and table extraction is heuristic and may not perfectly capture every visual region.
- The app is designed for explanation and study support, not for replacing careful reading of the original paper.

## Possible Future Improvements

- Add OCR support for scanned PDFs
- Add a chat interface for asking questions about the paper
- Add citation-aware explanations linked to exact paper pages
- Add support for multiple uploaded papers
- Add retrieval-augmented memory for comparing related papers
- Add evaluation metrics for explanation quality and faithfulness
- Add Docker support for easier deployment

## Example Use Cases

- Understanding a new research paper before a meeting
- Preparing for a journal club or paper presentation
- Studying unfamiliar equations, figures, and experiments
- Creating beginner-friendly paper summaries
- Building an AI-assisted research-reading workflow

## License


## Author

Amin Karimi

