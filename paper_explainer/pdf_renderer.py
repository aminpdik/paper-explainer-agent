import re
from html import escape
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

from paper_explainer.pdf_utils import ensure_directory


class StyledPdfRenderer:
    """
    Converts Markdown text into a clean, ChatGPT-style PDF.
    """

    def render_markdown_to_pdf(
        self,
        markdown_text: str,
        output_pdf_path: str | Path,
        document_name: str,
        title: str,
    ) -> str:
        output_pdf_path = Path(output_pdf_path)
        ensure_directory(output_pdf_path.parent)

        markdown_text, math_placeholders = self._protect_math(markdown_text)

        html_body = markdown.markdown(
            markdown_text,
            extensions=["extra", "sane_lists", "tables"],
        )

        html_body = self._restore_math(html_body, math_placeholders)

        html = self._build_html(
            html_body=html_body,
            document_name=document_name,
            title=title,
        )

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()

            page.set_content(html, wait_until="networkidle")
            page.wait_for_function("window.MathJax && MathJax.typesetPromise")
            page.evaluate("() => MathJax.typesetPromise()")

            page.pdf(
                path=str(output_pdf_path),
                format="Letter",
                print_background=True,
                margin={
                    "top": "0.6in",
                    "right": "0.6in",
                    "bottom": "0.6in",
                    "left": "0.6in",
                },
            )

            browser.close()

        return str(output_pdf_path)

    def _protect_math(self, markdown_text: str) -> tuple[str, dict[str, str]]:
        """
        Keep LaTeX untouched while Python-Markdown converts the rest of the text.

        Python-Markdown does not understand math syntax by default, so this
        prevents underscores, pipes, and backslashes inside equations from being
        treated as normal Markdown.
        """

        placeholders: dict[str, str] = {}

        def replace_display_math(match: re.Match[str]) -> str:
            key = f"@@DISPLAY_MATH_{len(placeholders)}@@"
            latex = escape(match.group(1).strip(), quote=False)
            placeholders[key] = f'<div class="math-block">$$\n{latex}\n$$</div>'
            return key

        def replace_inline_math(match: re.Match[str]) -> str:
            key = f"@@INLINE_MATH_{len(placeholders)}@@"
            latex = escape(match.group(1).strip(), quote=False)
            placeholders[key] = f'<span class="math-inline">\\({latex}\\)</span>'
            return key

        markdown_text = re.sub(
            r"\\\[(.*?)\\\]",
            replace_display_math,
            markdown_text,
            flags=re.DOTALL,
        )
        markdown_text = re.sub(
            r"\$\$(.*?)\$\$",
            replace_display_math,
            markdown_text,
            flags=re.DOTALL,
        )
        markdown_text = re.sub(
            r"\\\((.*?)\\\)",
            replace_inline_math,
            markdown_text,
            flags=re.DOTALL,
        )

        return markdown_text, placeholders

    def _restore_math(self, html_body: str, placeholders: dict[str, str]) -> str:
        for key, math_html in placeholders.items():
            html_body = html_body.replace(f"<p>{key}</p>", math_html)
            html_body = html_body.replace(key, math_html)

        return html_body

    def _build_html(
        self,
        html_body: str,
        document_name: str,
        title: str,
    ) -> str:
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">

    <script>
        window.MathJax = {{
            tex: {{
                inlineMath: [['\\\\(', '\\\\)']],
                displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
                processEscapes: true
            }},
            svg: {{
                fontCache: 'global'
            }}
        }};
    </script>
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>

    <style>
        @page {{
            size: Letter;
        }}

        body {{
            font-family: Arial, Helvetica, sans-serif;
            background-color: #f7f7f8;
            color: #1f2937;
            font-size: 14px;
            line-height: 1.7;
            margin: 0;
            padding: 40px;
        }}

        .container {{
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 18px;
            padding: 34px 40px;
            max-width: 780px;
            margin: 0 auto;
        }}

        .title {{
            font-size: 28px;
            font-weight: 700;
            color: #111827;
            margin-bottom: 6px;
        }}

        .subtitle {{
            font-size: 13px;
            color: #6b7280;
            margin-bottom: 22px;
        }}

        .divider {{
            height: 1px;
            background: #e5e7eb;
            margin-bottom: 24px;
        }}

        h1 {{
            color: #111827;
            font-size: 24px;
            margin-top: 36px;
            margin-bottom: 16px;
            page-break-before: auto;
        }}

        h2 {{
            color: #0f766e;
            background: #ecfdf5;
            border-left: 5px solid #0f766e;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 18px;
            margin-top: 28px;
            margin-bottom: 12px;
        }}

        h3 {{
            color: #374151;
            font-size: 16px;
            margin-top: 22px;
            margin-bottom: 10px;
        }}

        p {{
            margin-top: 0;
            margin-bottom: 16px;
            text-align: justify;
            text-justify: inter-word;
            text-align-last: left;
            hyphens: auto;
            overflow-wrap: break-word;
        }}

        ul, ol {{
            margin-top: 0;
            margin-bottom: 16px;
            padding-left: 24px;
        }}

        li {{
            margin-bottom: 8px;
        }}

        strong {{
            color: #111827;
            font-weight: 700;
        }}

        code {{
            background: #f3f4f6;
            padding: 2px 5px;
            border-radius: 5px;
            font-size: 13px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 18px 0;
            font-size: 13px;
        }}

        th, td {{
            border: 1px solid #e5e7eb;
            padding: 8px 10px;
            text-align: left;
        }}

        th {{
            background: #f9fafb;
            font-weight: 700;
        }}

        blockquote {{
            border-left: 4px solid #d1d5db;
            padding-left: 14px;
            color: #4b5563;
            margin-left: 0;
        }}

        hr {{
            border: none;
            border-top: 1px solid #e5e7eb;
            margin: 32px 0;
        }}

        .math-block {{
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            margin: 20px 0;
            padding: 14px 16px;
            overflow-x: auto;
            text-align: center;
            page-break-inside: avoid;
        }}

        .math-inline {{
            white-space: nowrap;
        }}

        mjx-container {{
            color: #111827;
        }}

        mjx-container[display="true"] {{
            margin: 0.8em 0;
            overflow-x: auto;
            overflow-y: hidden;
            max-width: 100%;
        }}

        .visual-region {{
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            margin: 18px 0 24px;
            padding: 12px;
            page-break-inside: avoid;
            background: #ffffff;
        }}

        .visual-region img {{
            display: block;
            width: 100%;
            max-width: 100%;
            height: auto;
            margin: 0 auto;
        }}

        .visual-region figcaption {{
            color: #6b7280;
            font-size: 12px;
            line-height: 1.4;
            margin-top: 8px;
            text-align: center;
        }}
    </style>
</head>

<body>
    <div class="container">
        <div class="title">{escape(title)}</div>
        <div class="subtitle">Generated from: {escape(document_name)}</div>
        <div class="divider"></div>

        {html_body}
    </div>
</body>
</html>
"""
