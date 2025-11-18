import logging
import os
from typing import Any, Dict, List, Tuple

import pandas as pd

from src.config.config import CONFIG, get_active_api_config, get_assets_path
from src.export.pdf_utils import (
    REPORTLAB_AVAILABLE,
    ReportPDFTemplate,
    create_paragraph,
)
from src.utils.i18n import translate

logger = logging.getLogger(__name__)

if REPORTLAB_AVAILABLE:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import LongTable, Paragraph, Spacer, TableStyle


def export_top_addresses_to_pdf(
    df: pd.DataFrame, file_path: str, currency: str
) -> Tuple[bool, str, str]:
    """
    Exports the top addresses DataFrame to a PDF file.
    """
    if not REPORTLAB_AVAILABLE:
        return False, "Error", "Missing required PDF libraries. See logs for details."
    if not file_path.lower().endswith(".pdf"):
        file_path += ".pdf"

    try:
        is_rtl: bool = CONFIG.get("language", "en") == "ar"
        default_align: int = TA_RIGHT if is_rtl else TA_LEFT
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
                fontName="DejaVuSans-Bold",
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

        report_title_str: str = translate("Top Addresses")
        story: List[Any] = [
            create_paragraph(report_title_str, styles["TitleStyle"], is_rtl),
            Spacer(1, 0.2 * inch),
        ]

        api_config = get_active_api_config()
        addr_url_base: str = api_config["explorer"]["address"]
        currency_upper: str = currency.upper()

        headers: List[str] = [
            translate("Rank"),
            translate("Known Name"),
            translate("Address"),
            translate("Balance (KAS)"),
            translate(f"Value ({currency_upper})"),
        ]

        data_as_list: List[List[Any]] = [
            [create_paragraph(h, styles["HeaderStyle"], is_rtl) for h in headers]
        ]

        for _, row in df.iterrows():
            row_data: List[Any] = [
                create_paragraph(str(row["Rank"]), styles["CellStyle"], is_rtl),
                create_paragraph(row["Known Name"], styles["CellStyle"], is_rtl),
                Paragraph(
                    f'<a href="{addr_url_base.format(kaspaAddress=row["Address"])}">{row["Address"]}</a>',
                    styles["LinkStyle"],
                ),
                create_paragraph(f"{row['Balance']:,.2f}", styles["CellStyle"], is_rtl),
                create_paragraph(
                    f"{row['Value']:,.2f} {currency_upper}", styles["CellStyle"], is_rtl
                ),
            ]
            data_as_list.append(row_data)

        relative_widths: List[float] = [0.05, 0.15, 0.50, 0.15, 0.15]
        doc_width: float = landscape(letter)[0] - 1 * inch
        col_widths: List[float] = [doc_width * w for w in relative_widths]

        table = LongTable(data_as_list, repeatRows=1, colWidths=col_widths)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#007bff")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("ALIGN", (0, 1), (0, -1), "CENTER"),
                    ("ALIGN", (3, 1), (4, -1), "RIGHT"),
                ]
            )
        )

        story.append(table)
        logger.info(f"Exporting top addresses to PDF: {file_path}")

        doc = ReportPDFTemplate(
            file_path,
            pagesize=landscape(letter),
            report_title=report_title_str,
            leftMargin=0.5 * inch,
            rightMargin=0.5 * inch,
            topMargin=0.5 * inch,
            bottomMargin=0.8 * inch,
        )
        doc.build(story)

        return True, "Export Successful", os.path.basename(file_path)
    except Exception as e:
        logger.error(f"Top Addresses PDF Export Error: {e}", exc_info=True)
        if os.path.exists(file_path) and os.path.getsize(file_path) < 1024:
            try:
                os.remove(file_path)
            except OSError:
                pass
        return False, "Error", translate("Check logs for details.")
