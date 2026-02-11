from __future__ import annotations
import os
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH


def write_resume_docx(text: str, out_path: str) -> None:
    """
    Convert plain-text resume to a simple, nicely formatted DOCX.

    Input expectations:
      - Section headers are UPPERCASE on their own line (e.g., SUMMARY, CORE SKILLS, EXPERIENCE).
      - Bullets start with "• " or "- " at the beginning of the line.
      - Blank lines separate sections.
    """
    # Ensure output directory exists
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    doc = Document()

    # Base (Normal) style
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Calibri"
    font.size = Pt(11)

    # Simple formatting knobs
    HEADER_FONT_SIZE = Pt(13)  # slightly larger than body
    HEADER_BOLD = True

    def _is_header(line: str) -> bool:
        # Treat short UPPERCASE lines as section headers
        s = line.strip()
        if not s:
            return False
        return s.isupper() and len(s) <= 80

    for raw in text.splitlines():
        line = raw.rstrip()

        # Keep intentional blank lines
        if not line.strip():
            doc.add_paragraph("")  # blank paragraph
            continue

        # Bullets
        if line.lstrip().startswith(("• ", "- ")):
            # Strip the bullet itself, keep content
            content = line.lstrip().lstrip("•- ").strip()
            if not content:
                # Edge case: a line that is only "•" or "-"
                content = ""
            p = doc.add_paragraph(style="List Bullet")
            run = p.add_run(content)
            run.font.size = Pt(11)
            continue

        # Section headers (UPPERCASE)
        if _is_header(line):
            p = doc.add_paragraph()
            run = p.add_run(line.strip())
            run.bold = HEADER_BOLD
            run.font.size = HEADER_FONT_SIZE
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            continue

        # Regular paragraph
        doc.add_paragraph(line)

    doc.save(out_path)