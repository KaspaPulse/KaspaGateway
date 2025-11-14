import os
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any
from src.config.config import CONFIG, APP_NAME
from src.utils.i18n import translate

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import BaseDocTemplate
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus.doctemplate import PageTemplate, Frame
    from reportlab.lib.styles import StyleSheet1

# We still perform the import checks at runtime
try:
    t_start_reportlab = time.perf_counter()
    logger.info("PERF: Importing reportlab...")
    
    from reportlab.platypus import (
        BaseDocTemplate, Frame, PageTemplate, Paragraph
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_LEFT
    from reportlab.lib.units import inch
    import arabic_reshaper
    from bidi.algorithm import get_display
    
    REPORTLAB_AVAILABLE = True
    
    t_end_reportlab = time.perf_counter()
    logger.info(f"PERF: reportlab imported successfully in {t_end_reportlab - t_start_reportlab:.4f} seconds.")
    
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("PDF export functionality is disabled. Required libraries are missing.")
    
    # Define dummy classes if reportlab is not available to avoid NameErrors at load time
    class BaseDocTemplate:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            pass
    class ParagraphStyle:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            pass

def create_paragraph(text: str, style: "ParagraphStyle", is_rtl: bool) -> "Paragraph":
    """
    Creates a ReportLab Paragraph, handling RTL text reshaping if necessary.
    """
    text_str = str(text) if text is not None else ""
    if is_rtl:
        try:
            reshaped_text = arabic_reshaper.reshape(text_str)
            bidi_text = get_display(reshaped_text)
            return Paragraph(bidi_text, style)
        except Exception:
            # Fallback for any reshaping error
            return Paragraph(text_str, style)
    return Paragraph(text_str, style)

class ReportPDFTemplate(BaseDocTemplate):
    """
    Custom BaseDocTemplate to add consistent headers and footers to PDF reports.
    """
    def __init__(self, filename: str, **kw: Any):
        super().__init__(filename, **kw)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='normal')
        template = PageTemplate(id='main_template', frames=[frame], onPage=self._footer)
        self.addPageTemplates([template])

    def _footer(self, canvas: "Canvas", doc: Any) -> None:
        """
        Internal method to draw the footer on each page.
        """
        canvas.saveState()
        is_rtl: bool = CONFIG.get("language", "en") == "ar"
        styles: "StyleSheet1" = getSampleStyleSheet()
        
        styles.add(ParagraphStyle(name='FooterStyle', parent=styles['Normal'], fontName='DejaVuSans', fontSize=8))
        styles.add(ParagraphStyle(name='FooterRight', parent=styles['FooterStyle'], alignment=TA_RIGHT))
        styles.add(ParagraphStyle(name='FooterLeft', parent=styles['FooterStyle'], alignment=TA_LEFT if not is_rtl else TA_RIGHT))
        
        app_version: str = CONFIG.get("version", "N/A")
        program_info_text: str = f"{APP_NAME} {translate('Version')} {app_version}"
        p_info = create_paragraph(program_info_text, styles['FooterLeft'], is_rtl)
        p_info.wrapOn(canvas, doc.width / 2, doc.bottomMargin)
        p_info.drawOn(canvas, doc.leftMargin, 0.5 * inch)
        
        page_num_text: str = f"{translate('Page')} {doc.page}"
        p_page = create_paragraph(page_num_text, styles['FooterRight'], is_rtl)
        p_page.wrapOn(canvas, doc.width, doc.bottomMargin)
        p_page.drawOn(canvas, doc.leftMargin, 0.5 * inch)
        
        export_time_text: str = f"{translate('Exported On')}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        p_time = create_paragraph(export_time_text, styles['FooterLeft'], is_rtl)
        p_time.wrapOn(canvas, doc.width, doc.bottomMargin)
        p_time.drawOn(canvas, doc.leftMargin, 0.3 * inch)
        
        canvas.restoreState()