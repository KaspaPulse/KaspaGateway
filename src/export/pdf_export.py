# -*- coding: utf-8 -*-
import io
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd

from src.config.config import (
    APP_NAME,
    APP_VERSION,
    get_active_api_config,
    get_assets_path,
)
from src.utils.i18n import translate

logger = logging.getLogger(__name__)

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        LongTable,
        PageTemplate,
        Paragraph,
        Spacer,
        TableStyle,
    )

    REPORTLAB_AVAILABLE = True
    font_path = get_assets_path(os.path.join("fonts", "DejaVuSans.ttf"))
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
    else:
        logger.warning(
            f"Font not found at {font_path}, non-Latin PDF export will not render correctly."
        )
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning(
        "PDF export functionality is disabled. Please run: pip install reportlab python-bidi arabic_reshaper"
    )


def create_paragraph(text: str, style: ParagraphStyle, is_rtl: bool) -> Paragraph:
    text_str = str(text)
    if is_rtl:
        try:
            reshaped_text = arabic_reshaper.reshape(text_str)
            bidi_text = get_display(reshaped_text)
            return Paragraph(bidi_text, style)
        except Exception:
            return Paragraph(text_str, style)
    return Paragraph(text_str, style)


class ReportPDFTemplate(BaseDocTemplate):
    def __init__(self, filename, **kw):
        self.kaspa_address = kw.pop("kaspa_address", "N/A")
        self.report_title = kw.pop(
            "report_title", translate("Kaspa Transaction Report")
        )
        super().__init__(filename, **kw)
        frame = Frame(
            self.leftMargin, self.bottomMargin, self.width, self.height, id="normal"
        )
        template = PageTemplate(id="main_template", frames=[frame], onPage=self._footer)
        self.addPageTemplates([template])

    def _footer(self, canvas, doc):
        canvas.saveState()
        api_config = get_active_api_config()
        is_rtl = api_config.get("language", "en") == "ar"
        styles = getSampleStyleSheet()
        styles.add(
            ParagraphStyle(
                name="FooterStyle",
                parent=styles["Normal"],
                fontName="DejaVuSans",
                fontSize=8,
            )
        )
        styles.add(
            ParagraphStyle(
                name="FooterRight", parent=styles["FooterStyle"], alignment=TA_RIGHT
            )
        )
        styles.add(
            ParagraphStyle(
                name="FooterLeft",
                parent=styles["FooterStyle"],
                alignment=TA_LEFT if not is_rtl else TA_RIGHT,
            )
        )

        program_info_text = f"{APP_NAME} {translate('Version')} {APP_VERSION}"
        p_info = create_paragraph(program_info_text, styles["FooterLeft"], is_rtl)
        p_info.wrapOn(canvas, doc.width / 2, doc.bottomMargin)
        p_info.drawOn(canvas, doc.leftMargin, 0.5 * inch)

        page_num_text = f"{translate('Page')} {doc.page}"
        p_page = create_paragraph(page_num_text, styles["FooterRight"], is_rtl)
        p_page.wrapOn(canvas, doc.width, doc.bottomMargin)
        p_page.drawOn(canvas, doc.leftMargin, 0.5 * inch)

        export_time_text = f"{translate('Exported On')}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        p_time = create_paragraph(export_time_text, styles["FooterLeft"], is_rtl)
        p_time.wrapOn(canvas, doc.width, doc.bottomMargin)
        p_time.drawOn(canvas, doc.leftMargin, 0.3 * inch)
        canvas.restoreState()


def export_to_pdf(
    df: pd.DataFrame,
    file_path: str,
    kaspa_address: str,
    address_name: str,
    currency: str,
    **kwargs,
) -> Tuple[bool, str, str]:
    if not REPORTLAB_AVAILABLE:
        return False, "Error", "Missing required PDF libraries. See logs for details."
    if not file_path.lower().endswith(".pdf"):
        file_path += ".pdf"

    try:
        api_config = get_active_api_config()
        is_rtl = api_config.get("language", "en") == "ar"
        default_align = TA_RIGHT if is_rtl else TA_LEFT
        styles = getSampleStyleSheet()
        styles.add(
            ParagraphStyle(
                name="TitleStyle",
                parent=styles["h1"],
                alignment=TA_CENTER,
                fontName="DejaVuSans",
            )
        )
        styles.add(
            ParagraphStyle(
                name="HeaderStyle",
                parent=styles["Normal"],
                fontSize=8,
                fontName="DejaVuSans",
                textColor=colors.whitesmoke,
                alignment=TA_CENTER,
                leading=10,
            )
        )
        styles.add(
            ParagraphStyle(
                name="CellStyle",
                parent=styles["Normal"],
                fontSize=7,
                fontName="DejaVuSans",
                alignment=default_align,
                leading=9,
                wordWrap="break",
            )
        )
        styles.add(
            ParagraphStyle(
                name="LinkStyle", parent=styles["CellStyle"], textColor=colors.blue
            )
        )
        styles.add(
            ParagraphStyle(
                name="HeaderInfo",
                parent=styles["Normal"],
                fontName="DejaVuSans",
                alignment=TA_CENTER,
                spaceAfter=6,
            )
        )
        styles.add(
            ParagraphStyle(
                name="HeaderInfoLink",
                parent=styles["HeaderInfo"],
                textColor=colors.blue,
            )
        )

        report_title_str = translate("Kaspa Transaction Report")
        story = [create_paragraph(report_title_str, styles["TitleStyle"], is_rtl)]
        addr_explorer_url = api_config["explorer"]["address"].format(
            kaspaAddress=kaspa_address
        )
        addr_header_text = f"{translate('Kaspa Address')}: <a href='{addr_explorer_url}'>{kaspa_address}</a>"
        story.append(
            create_paragraph(addr_header_text, styles["HeaderInfoLink"], is_rtl)
        )

        if address_name:
            name_header_text = f"({translate('Address Name')}: {address_name})"
            story.append(
                create_paragraph(name_header_text, styles["HeaderInfo"], is_rtl)
            )
        story.append(Spacer(1, 0.1 * inch))

        df_source = df.copy()
        df_final = pd.DataFrame()
        value_col_key = f"value_{currency.lower()}"

        export_cols_map = {
            "timestamp": translate("Date/Time"),
            "direction": translate("Direction"),
            "amount": translate("Amount (KAS)"),
            value_col_key: translate(f"Value ({currency.upper()})"),
            "txid": translate("Transaction ID"),
            "type": translate("Type:"),
        }

        if "timestamp" in df_source.columns:
            df_final[export_cols_map["timestamp"]] = pd.to_datetime(
                df_source["timestamp"], unit="s"
            ).dt.strftime("%Y-%m-%d %H:%M:%S")
        if "direction" in df_source.columns:
            df_final[export_cols_map["direction"]] = df_source["direction"].apply(
                lambda x: translate(str(x).capitalize())
            )
        if "amount" in df_source.columns:
            df_final[export_cols_map["amount"]] = df_source["amount"].apply(
                lambda x: f"{x:,.8f}"
            )
        if value_col_key in df_source.columns:
            df_final[export_cols_map[value_col_key]] = df_source[value_col_key].apply(
                lambda x: f"{x:,.2f} {currency.upper()}" if pd.notnull(x) else "N/A"
            )
        if "txid" in df_source.columns:
            df_final[export_cols_map["txid"]] = df_source["txid"]
        if "type" in df_source.columns:
            df_final[export_cols_map["type"]] = df_source["type"].apply(
                lambda x: translate(str(x).capitalize())
            )

        headers = [
            create_paragraph(h, styles["HeaderStyle"], is_rtl) for h in df_final.columns
        ]
        data_as_list = [headers]
        tx_url_base = api_config["explorer"]["transaction"]
        txid_col_name = translate("Transaction ID")

        for _, row in df_final.iterrows():
            row_data = []
            for col_name, cell in row.items():
                if col_name == txid_col_name and isinstance(cell, str):
                    link = f'<a href="{tx_url_base.format(txid=cell)}">{cell}</a>'
                    row_data.append(create_paragraph(link, styles["LinkStyle"], is_rtl))
                else:
                    row_data.append(
                        create_paragraph(str(cell), styles["CellStyle"], is_rtl)
                    )
            data_as_list.append(row_data)

        relative_widths = {
            translate("Date/Time"): 0.12,
            translate("Direction"): 0.07,
            translate("Amount (KAS)"): 0.12,
            translate(f"Value ({currency.upper()})"): 0.12,
            translate("Transaction ID"): 0.42,
            translate("Type:"): 0.07,
        }

        margins = {
            "leftMargin": 0.25 * inch,
            "rightMargin": 0.25 * inch,
            "topMargin": 0.5 * inch,
            "bottomMargin": 0.8 * inch,
        }
        temp_doc = BaseDocTemplate(io.BytesIO(), pagesize=landscape(letter), **margins)
        available_width = temp_doc.width
        col_widths = [
            available_width * relative_widths.get(col, 0.1) for col in df_final.columns
        ]

        if not col_widths or not data_as_list or len(data_as_list[0]) == 0:
            raise ValueError("No columns or data available to generate the PDF table.")

        table = LongTable(data_as_list, repeatRows=1, colWidths=col_widths)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#007bff")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(table)

        logger.info(f"Exporting data to PDF: {file_path}")
        doc = ReportPDFTemplate(
            file_path,
            pagesize=landscape(letter),
            kaspa_address=kaspa_address,
            report_title=report_title_str,
            **margins,
        )
        doc.build(story)

        return True, "Export Successful", os.path.basename(file_path)
    except Exception as e:
        logger.error(f"PDF Export Error: {e}")
        if os.path.exists(file_path) and os.path.getsize(file_path) < 1024:
            try:
                os.remove(file_path)
            except OSError:
                pass
        return False, "Error", translate("Check logs for details.")
