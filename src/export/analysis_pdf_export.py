import logging
import os
from typing import Any, Dict, List, Optional, Tuple

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
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    from reportlab.platypus.flowables import Flowable

    font_path = get_assets_path(os.path.join("fonts", "DejaVuSans.ttf"))
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", font_path))
    else:
        logger.warning(
            f"Font not found at {font_path}, PDF export may not render correctly."
        )
else:
    # Define dummy classes if reportlab is not available
    Flowable = object
    ParagraphStyle = object
    Table = object
    Spacer = object
    Paragraph = object
    letter = (0, 0)
    inch = 0
    colors = None
    TA_CENTER = 0
    TA_RIGHT = 0
    TA_LEFT = 0


def export_analysis_to_pdf(
    file_path: str,
    kaspa_address: str,
    address_name: str,
    currency: str,
    counterparties: Dict[str, List[Dict[str, Any]]],
    known_names_map: Dict[str, str],
    analysis_data: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Tuple[bool, str, str]:
    """
    Exports the analysis data, broken down by counterparty, to a PDF file.
    Note: This exporter currently only exports tabular data, not charts.
    """
    if not REPORTLAB_AVAILABLE:
        return False, "Error", "Missing required PDF libraries. See logs for details."
    if not file_path.lower().endswith(".pdf"):
        file_path += ".pdf"

    try:
        is_rtl: bool = CONFIG.get("language", "en") == "ar"
        styles: Dict[str, ParagraphStyle] = getSampleStyleSheet()
        styles.add(
            ParagraphStyle(
                name="LinkStyle",
                parent=styles["Normal"],
                fontName="DejaVuSans",
                fontSize=7,
                textColor=colors.blue,
            )
        )
        styles.add(
            ParagraphStyle(
                name="CellStyle",
                parent=styles["Normal"],
                fontName="DejaVuSans",
                fontSize=7,
            )
        )
        styles.add(
            ParagraphStyle(
                name="HeaderStyle",
                parent=styles["Normal"],
                fontName="DejaVuSans-Bold",
                fontSize=8,
                textColor=colors.whitesmoke,
                alignment=TA_CENTER,
            )
        )
        styles.add(
            ParagraphStyle(
                name="H3Style", parent=styles["h3"], fontName="DejaVuSans-Bold"
            )
        )

        api_config: Dict[str, Any] = get_active_api_config()
        addr_url_base: str = api_config.get("explorer", {}).get("address", "")
        tx_url_base: str = api_config.get("explorer", {}).get("transaction", "")

        report_title_str: str = translate("Kaspa Analysis Report")
        story: List[Flowable] = [
            create_paragraph(report_title_str, styles["h1"], is_rtl)
        ]
        kaspa_addr_link: str = (
            f"<a href='{addr_url_base.format(kaspaAddress=kaspa_address)}'>{kaspa_address}</a>"
            if addr_url_base
            else kaspa_address
        )
        story.append(
            Paragraph(
                f"{translate('Analysis Report for Kaspa Address')}: {kaspa_addr_link}",
                styles["Normal"],
            )
        )

        if address_name:
            story.append(
                create_paragraph(
                    f"({translate('Address Name')}: {address_name})",
                    styles["Normal"],
                    is_rtl,
                )
            )
        story.append(Spacer(1, 0.2 * inch))

        for cp_address, tx_list in counterparties.items():
            cp_name: str = known_names_map.get(cp_address, "")
            cp_name_str: str = f"({cp_name})" if cp_name else ""
            cp_addr_link: str = (
                f"<a href='{addr_url_base.format(kaspaAddress=cp_address)}'>{cp_address}</a>"
                if addr_url_base
                else cp_address
            )
            story.append(
                Paragraph(
                    f"{translate('Counterparty')}: {cp_addr_link} {cp_name_str}",
                    styles["H3Style"],
                )
            )

            if not tx_list:
                story.append(
                    create_paragraph(
                        translate("No transactions for this counterparty."),
                        styles["Normal"],
                        is_rtl,
                    )
                )
                story.append(Spacer(1, 0.2 * inch))
                continue

            df_cp = pd.DataFrame(tx_list)
            value_col_key: str = f"value_{currency.lower()}"

            headers: List[str] = [
                translate("Date/Time"),
                translate("Transaction ID"),
                translate("Direction"),
                translate("Amount (KAS)"),
                translate(f"Value ({currency.upper()})"),
                translate("Block Score"),
                translate("Type"),
            ]

            data_list: List[List[Any]] = [
                [create_paragraph(h, styles["HeaderStyle"], is_rtl) for h in headers]
            ]

            for _, row in df_cp.iterrows():
                row_data: List[Any] = [
                    create_paragraph(
                        pd.to_datetime(row["timestamp"], unit="s").strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        styles["CellStyle"],
                        is_rtl,
                    ),
                    (
                        Paragraph(
                            f"<a href='{tx_url_base.format(txid=row['txid'])}' color='blue'>{row['txid']}</a>",
                            styles["LinkStyle"],
                        )
                        if tx_url_base
                        else create_paragraph(row["txid"], styles["CellStyle"], is_rtl)
                    ),
                    create_paragraph(
                        translate(str(row["direction"]).capitalize()),
                        styles["CellStyle"],
                        is_rtl,
                    ),
                    create_paragraph(
                        f"{row['amount']:,.8f}", styles["CellStyle"], is_rtl
                    ),
                    create_paragraph(
                        (
                            f"{row.get(value_col_key, 0.0):,.2f} {currency.upper()}"
                            if pd.notnull(row.get(value_col_key))
                            else "N/A"
                        ),
                        styles["CellStyle"],
                        is_rtl,
                    ),
                    create_paragraph(
                        str(row["block_height"]), styles["CellStyle"], is_rtl
                    ),
                    create_paragraph(
                        translate(str(row["type"]).capitalize()),
                        styles["CellStyle"],
                        is_rtl,
                    ),
                ]
                data_list.append(row_data)

            total_amount: float = df_cp["amount"].sum()
            total_value: float = (
                df_cp[value_col_key].sum()
                if value_col_key in df_cp and not df_cp[value_col_key].isnull().all()
                else 0.0
            )

            summary_row: List[Any] = [""] * len(headers)
            summary_row[2] = create_paragraph(
                translate("Total"), styles["CellStyle"], is_rtl
            )
            summary_row[3] = create_paragraph(
                f"{total_amount:,.8f}", styles["CellStyle"], is_rtl
            )
            summary_row[4] = create_paragraph(
                f"{total_value:,.2f} {currency.upper()}", styles["CellStyle"], is_rtl
            )
            data_list.append(summary_row)

            doc_width: float = landscape(letter)[0] - 0.5 * inch
            col_widths: List[float] = [
                doc_width * w for w in [0.12, 0.40, 0.08, 0.12, 0.12, 0.08, 0.08]
            ]

            table = Table(
                data_list, repeatRows=1, colWidths=col_widths, hAlign="CENTER"
            )

            style_commands: List[Tuple[str, Tuple[int, int], Tuple[int, int], Any]] = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#007bff")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
                ("FONT", (0, -1), (-1, -1), "DejaVuSans-Bold", 7),
            ]

            table.setStyle(TableStyle(style_commands))
            story.append(table)
            story.append(Spacer(1, 0.2 * inch))

        logger.info(f"Exporting data to PDF: {file_path}")
        doc = ReportPDFTemplate(
            file_path,
            pagesize=landscape(letter),
            leftMargin=0.25 * inch,
            rightMargin=0.25 * inch,
            topMargin=0.5 * inch,
            bottomMargin=0.8 * inch,
        )
        doc.build(story)

        return True, "Export Successful", os.path.basename(file_path)
    except Exception as e:
        logger.error(f"PDF Export Error: {e}", exc_info=True)
        if os.path.exists(file_path) and os.path.getsize(file_path) < 1024:
            try:
                os.remove(file_path)
            except OSError:
                pass
        return False, "Error", translate("Check logs for details.")
