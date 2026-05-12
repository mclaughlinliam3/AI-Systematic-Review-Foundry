"""
Export manager for the Systematic Review Foundry.
Handles export to .docx, .pdf, and .tex formats.
"""
import re
import io
import unicodedata
from typing import Dict, Any

from models import ReviewSession


def sanitize_for_latex(text: str) -> str:
    """Make a string block compatible with LaTeX."""
    replacements = [
        ('\\', r'\textbackslash{}'),
        ('&', r'\&'), ('%', r'\%'), ('$', r'\$'), ('#', r'\#'),
        ('_', r'\_'), ('{', r'\{'), ('}', r'\}'),
        ('~', r'\textasciitilde{}'), ('^', r'\textasciicircum{}'),
        ('≥', r'$\geq$'), ('≤', r'$\leq$'),
        ('>', r'$>$'), ('<', r'$<$'),
    ]

    def replace_unescaped(text, char, replacement):
        result = ""
        i = 0
        while i < len(text):
            if text[i:i+len(char)] == char:
                if i == 0 or text[i-1] != '\\':
                    result += replacement
                    i += len(char)
                else:
                    result += char
                    i += len(char)
            else:
                result += text[i]
                i += 1
        return result

    def replace_greek(text):
        result = ""
        for char in text:
            try:
                name = unicodedata.name(char, '')
                if name.startswith('GREEK SMALL LETTER'):
                    latex_name = name.split()[-1].lower()
                    result += f'$\\{latex_name}$'
                elif name.startswith('GREEK CAPITAL LETTER'):
                    latex_name = name.split()[-1].lower()
                    result += f'$\\{latex_name.capitalize()}$'
                else:
                    result += char
            except ValueError:
                result += char
        return result

    for char, replacement in replacements:
        text = replace_unescaped(text, char, replacement)
    text = replace_greek(text)
    return text


def export_to_latex(session: ReviewSession, filepath: str, title: str = "Systematic Review"):
    """Export the review session to a .tex file."""
    parts = []
    parts.append("\\documentclass[12pt,a4paper]{article}")
    parts.append("\\usepackage[utf8]{inputenc}")
    parts.append("\\usepackage{hyperref}")
    parts.append("\\usepackage{geometry}")
    parts.append("\\geometry{margin=1in}")
    parts.append("\\usepackage{lmodern}")
    parts.append("\\begin{document}")
    parts.append(f"\\title{{{sanitize_for_latex(title)}}}")
    parts.append("\\author{Systematic Review Team}")
    parts.append("\\maketitle")

    if session.abstract:
        parts.append("\\section{Abstract}")
        parts.append(sanitize_for_latex(session.abstract))

    if session.intro:
        parts.append("\\section{Introduction}")
        parts.append(sanitize_for_latex(session.intro))

    if session.methods:
        parts.append("\\section{Methods}")
        parts.append(sanitize_for_latex(session.methods))

    if session.results:
        parts.append("\\section{Results}")
        for rs in session.results:
            sec_title = rs.get('section', 'Untitled')
            sec_title = re.sub(r'^\d+\.\s*', '', sec_title)
            text = rs.get('text', '')
            if text:
                parts.append(f"\\subsection{{{sanitize_for_latex(sec_title)}}}")
                parts.append(sanitize_for_latex(text))

    if session.discussion:
        parts.append("\\section{Discussion}")
        parts.append(sanitize_for_latex(session.discussion))

    if session.conclusion:
        parts.append("\\section{Conclusion}")
        parts.append(sanitize_for_latex(session.conclusion))

    if session.citations:
        parts.append("\\section{References}")
        parts.append(sanitize_for_latex(session.citations))

    parts.append("\\end{document}")

    with io.open(filepath, 'w', encoding='utf-8') as f:
        f.write("\n\n".join(parts))


def export_to_docx(session: ReviewSession, filepath: str, title: str = "Systematic Review"):
    """Export the review session to a .docx file."""
    try:
        from docx import Document
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        raise ImportError("python-docx is required for DOCX export. Install with: pip install python-docx")

    doc = Document()

    # Title
    title_para = doc.add_heading(title, level=0)
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    sections = [
        ("Abstract", session.abstract),
        ("Introduction", session.intro),
        ("Methods", session.methods),
    ]

    for heading, content in sections:
        if content:
            doc.add_heading(heading, level=1)
            doc.add_paragraph(content)

    if session.results:
        doc.add_heading("Results", level=1)
        for rs in session.results:
            sec_title = rs.get('section', 'Untitled')
            sec_title = re.sub(r'^\d+\.\s*', '', sec_title)
            text = rs.get('text', '')
            if text:
                doc.add_heading(sec_title, level=2)
                doc.add_paragraph(text)

    more_sections = [
        ("Discussion", session.discussion),
        ("Conclusion", session.conclusion),
        ("References", session.citations),
    ]

    for heading, content in more_sections:
        if content:
            doc.add_heading(heading, level=1)
            doc.add_paragraph(content)

    doc.save(filepath)


def export_to_pdf(session: ReviewSession, filepath: str, title: str = "Systematic Review"):
    """Export via generating LaTeX then compiling, or use reportlab as fallback."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.units import inch
    except ImportError:
        raise ImportError("reportlab is required for PDF export. Install with: pip install reportlab")

    doc = SimpleDocTemplate(filepath, pagesize=letter,
                            topMargin=inch, bottomMargin=inch,
                            leftMargin=inch, rightMargin=inch)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('ReviewTitle', parent=styles['Title'], fontSize=18, spaceAfter=20)
    heading_style = ParagraphStyle('ReviewHeading', parent=styles['Heading1'], fontSize=14, spaceAfter=10)
    subheading_style = ParagraphStyle('ReviewSubheading', parent=styles['Heading2'], fontSize=12, spaceAfter=8)
    body_style = ParagraphStyle('ReviewBody', parent=styles['Normal'], fontSize=11, spaceAfter=6, leading=14)

    story = []
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 0.3 * inch))

    def add_section(heading, content):
        if content:
            story.append(Paragraph(heading, heading_style))
            for para in content.split('\n'):
                if para.strip():
                    # Escape XML special chars for reportlab
                    safe = para.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    story.append(Paragraph(safe, body_style))
            story.append(Spacer(1, 0.15 * inch))

    add_section("Abstract", session.abstract)
    add_section("Introduction", session.intro)
    add_section("Methods", session.methods)

    if session.results:
        story.append(Paragraph("Results", heading_style))
        for rs in session.results:
            sec_title = rs.get('section', 'Untitled')
            sec_title = re.sub(r'^\d+\.\s*', '', sec_title)
            text = rs.get('text', '')
            if text:
                story.append(Paragraph(sec_title, subheading_style))
                for para in text.split('\n'):
                    if para.strip():
                        safe = para.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                        story.append(Paragraph(safe, body_style))
        story.append(Spacer(1, 0.15 * inch))

    add_section("Discussion", session.discussion)
    add_section("Conclusion", session.conclusion)
    add_section("References", session.citations)

    doc.build(story)
