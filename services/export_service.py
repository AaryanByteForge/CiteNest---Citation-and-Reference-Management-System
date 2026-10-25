"""
Export Module (IExport / ExportService) for CiteNest.
Generates academic-grade PDF and TXT files for full documents or standalone bibliographies.
"""

import io
import uuid
import datetime
import html
import re
from typing import Dict, Any, Optional, Tuple
from database import get_db
from models import DocumentLifecycleState
from services.document_service import DocumentService
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable


class ExportService:
    """Implements IExport interface for PDF and TXT export."""

    @staticmethod
    def _html_to_clean_text(html_content: str) -> str:
        """Converts HTML formatted content to clean plain text."""
        if not html_content:
            return ""

        # Replace citation token spans with just their inner citation text
        clean = re.sub(
            r'<span[^>]*class=["\'][^"\']*citenest-citation[^"\']*["\'][^>]*>.*?<span class=["\']cite-text["\']>(.*?)</span>.*?</span>',
            r'\1',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )

        # Replace common tags with newlines
        clean = re.sub(r'</?(h1|h2|h3|p|div|br)[^>]*>', '\n\n', clean, flags=re.IGNORECASE)
        # Strip all other tags
        clean = re.sub(r'<[^>]+>', '', clean)
        # Unescape HTML entities
        clean = html.unescape(clean)
        # Clean multiple blank lines
        clean = re.sub(r'\n{3,}', '\n\n', clean)
        return clean.strip()

    @staticmethod
    def _html_to_reportlab_paragraphs(html_content: str, styles) -> list:
        """Converts HTML body into ReportLab Platypus flowable elements."""
        flowables = []

        # Replace citation tokens with just their text inside <b> or normal
        clean_html = re.sub(
            r'<span[^>]*class=["\'][^"\']*citenest-citation[^"\']*["\'][^>]*>.*?<span class=["\']cite-text["\']>(.*?)</span>.*?</span>',
            r'\1',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )

        # Split into blocks by H1, H2, H3, P
        blocks = re.split(r'(<(?:h1|h2|h3|p)[^>]*>.*?</(?:h1|h2|h3|p)>)', clean_html, flags=re.DOTALL | re.IGNORECASE)

        for block in blocks:
            b = block.strip()
            if not b:
                continue

            tag_match = re.match(r'<([a-zA-Z0-9]+)[^>]*>(.*?)</\1>', b, flags=re.DOTALL)
            if tag_match:
                tag = tag_match.group(1).lower()
                inner_text = tag_match.group(2).strip()

                # Clean unsupported tags inside paragraph for ReportLab
                inner_text = re.sub(r'</?(?:span|div)[^>]*>', '', inner_text)

                if tag == 'h1':
                    flowables.append(Paragraph(inner_text, styles['AcademicH1']))
                    flowables.append(Spacer(1, 10))
                elif tag == 'h2':
                    flowables.append(Paragraph(inner_text, styles['AcademicH2']))
                    flowables.append(Spacer(1, 8))
                elif tag == 'h3':
                    flowables.append(Paragraph(inner_text, styles['AcademicH3']))
                    flowables.append(Spacer(1, 6))
                elif tag == 'p':
                    flowables.append(Paragraph(inner_text, styles['AcademicBody']))
                    flowables.append(Spacer(1, 10))
            else:
                # Raw text
                cleaned_text = re.sub(r'<[^>]+>', '', b).strip()
                if cleaned_text:
                    flowables.append(Paragraph(cleaned_text, styles['AcademicBody']))
                    flowables.append(Spacer(1, 8))

        return flowables

    @staticmethod
    def export_document(
        owner_id: str,
        document_id: str,
        export_format: str,
        standalone_bibliography: bool = False
    ) -> Tuple[bool, str, Optional[bytes], str, str]:
        """
        Exports document or standalone bibliography to PDF or TXT.
        Returns: (success: bool, error_msg: str, file_bytes: bytes, file_name: str, mime_type: str)
        """
        fmt = export_format.upper().strip()
        if fmt not in ["PDF", "TXT"]:
            return False, "Unsupported export format. CiteNest supports PDF and TXT only.", None, "", ""

        # Pre-build: recompile bibliography (Annex C)
        DocumentService.recompile_document_citations(owner_id, document_id)
        doc = DocumentService.get_document_by_id(owner_id, document_id)
        if not doc:
            return False, "Document not found or access denied.", None, "", ""

        title = doc["title"]
        style_name = doc["citationStyle"]
        bib_entries = doc.get("bibliography", {}).get("entries", [])
        has_citations = len(bib_entries) > 0

        # Sanitize filename
        safe_title = re.sub(r'[^a-zA-Z0-9_\- ]', '', title).replace(' ', '_')
        if standalone_bibliography:
            file_name = f"{safe_title}_Bibliography_{style_name}.{fmt.lower()}"
        else:
            file_name = f"{safe_title}_{style_name}.{fmt.lower()}"

        try:
            if fmt == "TXT":
                output = io.StringIO()
                if standalone_bibliography:
                    output.write(f"BIBLIOGRAPHY ({style_name} Style)\n")
                    output.write(f"Document: {title}\n")
                    output.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                    output.write("=" * 60 + "\n\n")

                    if has_citations:
                        for entry in bib_entries:
                            output.write(f"{entry.get('text', '')}\n\n")
                    else:
                        output.write("No references cited in this document.\n")
                else:
                    output.write(f"{title}\n")
                    output.write(f"Citation Style: {style_name}\n")
                    output.write(f"Date: {datetime.datetime.now().strftime('%B %d, %Y')}\n")
                    output.write("=" * 60 + "\n\n")

                    body_text = ExportService._html_to_clean_text(doc.get("content", ""))
                    output.write(body_text + "\n\n")

                    # No-citations branch: export without References if 0 citations (UC-018 Alt Flow)
                    if has_citations:
                        output.write("-" * 40 + "\n")
                        output.write(f"REFERENCES ({style_name})\n")
                        output.write("-" * 40 + "\n\n")
                        for entry in bib_entries:
                            output.write(f"{entry.get('text', '')}\n\n")

                file_bytes = output.getvalue().encode("utf-8")
                mime_type = "text/plain"

            elif fmt == "PDF":
                buffer = io.BytesIO()
                doc_pdf = SimpleDocTemplate(
                    buffer,
                    pagesize=letter,
                    rightMargin=54,
                    leftMargin=54,
                    topMargin=54,
                    bottomMargin=54
                )

                styles = getSampleStyleSheet()

                # Custom academic styles
                styles.add(ParagraphStyle(
                    name='AcademicTitle',
                    fontName='Helvetica-Bold',
                    fontSize=20,
                    leading=24,
                    textColor=colors.HexColor('#1E293B'),
                    spaceAfter=8,
                    alignment=1  # Centered
                ))
                styles.add(ParagraphStyle(
                    name='AcademicMeta',
                    fontName='Helvetica',
                    fontSize=10,
                    leading=14,
                    textColor=colors.HexColor('#64748B'),
                    alignment=1,
                    spaceAfter=18
                ))
                styles.add(ParagraphStyle(
                    name='AcademicH1',
                    fontName='Helvetica-Bold',
                    fontSize=15,
                    leading=19,
                    textColor=colors.HexColor('#0F172A'),
                    spaceBefore=14,
                    spaceAfter=6
                ))
                styles.add(ParagraphStyle(
                    name='AcademicH2',
                    fontName='Helvetica-Bold',
                    fontSize=13,
                    leading=17,
                    textColor=colors.HexColor('#1E293B'),
                    spaceBefore=12,
                    spaceAfter=4
                ))
                styles.add(ParagraphStyle(
                    name='AcademicH3',
                    fontName='Helvetica-Bold',
                    fontSize=11,
                    leading=15,
                    textColor=colors.HexColor('#334155'),
                    spaceBefore=10,
                    spaceAfter=4
                ))
                styles.add(ParagraphStyle(
                    name='AcademicBody',
                    fontName='Times-Roman',
                    fontSize=11,
                    leading=16,
                    textColor=colors.HexColor('#0F172A'),
                    firstLineIndent=18,
                    spaceAfter=8
                ))
                styles.add(ParagraphStyle(
                    name='AcademicBibEntry',
                    fontName='Times-Roman',
                    fontSize=10,
                    leading=15,
                    textColor=colors.HexColor('#0F172A'),
                    leftIndent=24,
                    firstLineIndent=-24,  # Hanging indent
                    spaceAfter=8
                ))

                flowables = []

                if standalone_bibliography:
                    flowables.append(Paragraph(f"Bibliography — {title}", styles['AcademicTitle']))
                    flowables.append(Paragraph(f"Style: {style_name} | Generated: {datetime.datetime.now().strftime('%B %d, %Y')}", styles['AcademicMeta']))
                    flowables.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E1'), spaceAfter=14))

                    if has_citations:
                        for entry in bib_entries:
                            # Use HTML formatting (<i>...</i>) supported by ReportLab Paragraph
                            entry_html = entry.get('html', entry.get('text', ''))
                            # Remove <a> tags for PDF
                            entry_html = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', entry_html)
                            flowables.append(Paragraph(entry_html, styles['AcademicBibEntry']))
                    else:
                        flowables.append(Paragraph("<i>No references currently cited in this document.</i>", styles['AcademicBody']))
                else:
                    # Full document export
                    flowables.append(Paragraph(title, styles['AcademicTitle']))
                    flowables.append(Paragraph(f"CiteNest Academic Export • Style: {style_name} • {datetime.datetime.now().strftime('%B %d, %Y')}", styles['AcademicMeta']))
                    flowables.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E1'), spaceAfter=14))

                    # Convert HTML content
                    content_flowables = ExportService._html_to_reportlab_paragraphs(doc.get("content", ""), styles)
                    flowables.extend(content_flowables)

                    # Only append References section if citations exist (UC-018 Alt Flow)
                    if has_citations:
                        flowables.append(Spacer(1, 14))
                        flowables.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor('#94A3B8'), spaceBefore=8, spaceAfter=12))
                        flowables.append(Paragraph("References", styles['AcademicH1']))
                        flowables.append(Spacer(1, 6))

                        for entry in bib_entries:
                            entry_html = entry.get('html', entry.get('text', ''))
                            entry_html = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', entry_html)
                            flowables.append(Paragraph(entry_html, styles['AcademicBibEntry']))

                doc_pdf.build(flowables)
                file_bytes = buffer.getvalue()
                mime_type = "application/pdf"

            # Record ExportedFile and transition document state to 'Exported'
            with get_db() as conn:
                cursor = conn.cursor()
                file_id = f"FILE-{uuid.uuid4().hex[:6].upper()}"
                now = datetime.datetime.now(datetime.timezone.utc).isoformat()

                cursor.execute("""
                    INSERT INTO exported_files (fileId, documentId, format, generatedDate, fileName)
                    VALUES (?, ?, ?, ?, ?);
                """, (file_id, document_id, fmt, now, file_name))

                cursor.execute("""
                    UPDATE documents SET state = ?, lastModifiedDate = ? WHERE documentId = ?;
                """, (DocumentLifecycleState.EXPORTED.value, now, document_id))

                log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
                cursor.execute("""
                    INSERT INTO audit_logs (logId, actorId, action, timestamp)
                    VALUES (?, ?, ?, ?);
                """, (log_id, owner_id, f"Exported document {document_id} ({file_name})", now))

                conn.commit()

            return True, "", file_bytes, file_name, mime_type

        except Exception as e:
            # AC-05 Failure handling: document remains completely unchanged
            return False, f"Export failed: {str(e)}", None, "", ""
