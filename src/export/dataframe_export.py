import html
import io
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple, cast

import pandas as pd

from src.config.config import APP_NAME, CONFIG, get_active_api_config, get_assets_path
from src.export.pdf_utils import (
    REPORTLAB_AVAILABLE,
    ReportPDFTemplate,
    create_paragraph,
)
from src.utils.i18n import translate
from src.utils.validation import sanitize_csv_cell

logger = logging.getLogger(__name__)

STYLE = """
<style>
    body { font-family: 'Segoe UI', Arial, sans-serif; margin: 2em; background-color: #f4f4f9; color: #333; }
    .rtl { direction: rtl; text-align: right; }
    h1, h2 { color: #007bff; border-bottom: 2px solid #dee2e6; padding-bottom: 10px; }
    .report-info { background-color: #e9ecef; padding: 15px; border-radius: 8px; margin-bottom: 2em; }
    .report-info p { margin: 5px 0; }
    .kaspa-table { border-collapse: collapse; width: 100%; box-shadow: 0 2px 5px rgba(0,0,0,0.15); background-color: #fff; }
    .kaspa-table th, .kaspa-table td { border: 1px solid #ddd; padding: 12px; text-align: left; word-break: break-word; }
    .rtl .kaspa-table th, .rtl .kaspa-table td { text-align: right; }
    .kaspa-table th { background-color: #007bff; color: white; font-weight: bold; }
    .kaspa-table tr:nth-child(even) { background-color: #f9f9f9; }
    a { color: #0056b3; text-decoration: none; }
    a:hover { text-decoration: underline; }
    footer { text-align: center; margin-top: 2em; font-size: 0.8em; color: #6c757d; }
</style>
"""

if REPORTLAB_AVAILABLE:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    font_path = get_assets_path(os.path.join("fonts", "DejaVuSans.ttf"))
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", font_path))


def _create_report_header_text(
    kaspa_address: str, address_name: str, currency: str
) -> str:
    """
    Generates the comment header for CSV exports.
    """
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = f'# {APP_NAME} {translate("Version")} {CONFIG.get("version", "N/A")}\n'
    header += (
        f'# {translate("Transaction Report for Kaspa Address")}: {kaspa_address}\n'
    )
    if address_name:
        header += f'# {translate("Address Name")}: {address_name}\n'
    header += f'# {translate("Currency")}: {currency.upper()}\n'
    header += f'# {translate("Exported On")}: {timestamp_str}\n\n'
    return header


def _prepare_dataframe_for_export(
    df: pd.DataFrame,
    currency: str,
    known_names_map: Dict[str, str],
    sanitize_for_csv: bool = False,
) -> Tuple[pd.DataFrame, str, Dict[str, str]]:
    """
    Prepares a DataFrame for export by selecting columns, formatting names, and translating headers.
    """
    value_col_key = f"value_{currency.lower()}"
    core_cols = [
        "timestamp",
        "txid",
        "direction",
        "from_address",
        "to_address",
        "amount",
        "block_height",
        "type",
    ]

    required_cols = [col for col in core_cols if col in df.columns]
    if value_col_key in df.columns:
        required_cols.append(value_col_key)

    export_df = df[required_cols].copy()

    for addr_col in ["from_address", "to_address"]:
        if addr_col in export_df.columns:
            if sanitize_for_csv:
                export_df[addr_col] = export_df[addr_col].apply(
                    lambda x: ", ".join(
                        sanitize_csv_cell(known_names_map.get(addr, addr))
                        for addr in str(x).split(", ")
                    )
                )
            else:
                export_df[addr_col] = export_df[addr_col].apply(
                    lambda x: ", ".join(
                        html.escape(known_names_map.get(addr, addr))
                        for addr in str(x).split(", ")
                    )
                )

    if "timestamp" in export_df.columns:
        export_df["timestamp"] = pd.to_datetime(export_df["timestamp"], unit="s")

    value_col_name = translate(f"Value ({currency.upper()})")
    rename_map: Dict[str, str] = {
        "timestamp": translate("Date/Time"),
        "txid": translate("Transaction ID"),
        "direction": translate("Direction"),
        "from_address": translate("From Address(es)"),
        "to_address": translate("To Address(es)"),
        "amount": translate("Amount (KAS)"),
        "block_height": translate("Block Score"),
        "type": translate("Type"),
        value_col_key: value_col_name,
    }
    export_df.rename(columns=rename_map, inplace=True)
    return export_df, value_col_name, rename_map


def export_df_to_csv(
    df: pd.DataFrame,
    file_path: str,
    kaspa_address: str,
    address_name: str,
    currency: str,
    known_names_map: Dict[str, str],
    **kwargs: Any,
) -> Tuple[bool, str, str]:
    """
    Exports a DataFrame to a CSV file with a metadata header.
    """
    if not file_path.lower().endswith(".csv"):
        file_path += ".csv"
    try:
        export_df, value_col_name, rename_map = _prepare_dataframe_for_export(
            df, currency, known_names_map, sanitize_for_csv=True
        )

        if value_col_name in export_df.columns:
            export_df[value_col_name] = export_df[value_col_name].apply(
                lambda x: f"{x:,.2f} {currency.upper()}" if pd.notnull(x) else "N/A"
            )

        if (dir_col := rename_map.get("direction")) in export_df.columns:
            export_df[dir_col] = export_df[dir_col].apply(
                lambda x: sanitize_csv_cell(translate(str(x).capitalize()))
            )
        if (type_col := rename_map.get("type")) in export_df.columns:
            export_df[type_col] = export_df[type_col].apply(
                lambda x: sanitize_csv_cell(translate(str(x).capitalize()))
            )
        if (txid_col := rename_map.get("txid")) in export_df.columns:
            export_df[txid_col] = export_df[txid_col].apply(sanitize_csv_cell)

        with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(_create_report_header_text(kaspa_address, address_name, currency))
            export_df.to_csv(f, index=False, date_format="%Y-%m-%d %H:%M:%S")
        return True, "Export Successful", os.path.basename(file_path)
    except Exception as e:
        logger.error(f"DataFrame to CSV Export Error: {e}", exc_info=True)
        return False, "Error", str(e)


def export_df_to_html(
    df: pd.DataFrame,
    file_path: str,
    kaspa_address: str,
    address_name: str,
    currency: str,
    known_names_map: Dict[str, str],
    **kwargs: Any,
) -> Tuple[bool, str, str]:
    """
    Exports a DataFrame to a styled HTML file.
    """
    if not file_path.lower().endswith(".html"):
        file_path += ".html"
    try:
        export_df, value_col_name, rename_map = _prepare_dataframe_for_export(
            df, currency, known_names_map
        )
        api_config = get_active_api_config()
        tx_url_base: str = api_config.get("explorer", {}).get("transaction", "")

        if value_col_name in export_df.columns:
            export_df[value_col_name] = export_df[value_col_name].apply(
                lambda x: (
                    f"{x:,.2f} {html.escape(currency.upper())}"
                    if pd.notnull(x)
                    else "N/A"
                )
            )

        tx_id_col = rename_map.get("txid")
        if tx_id_col in export_df.columns and tx_url_base and "txid" in df.columns:
            export_df[tx_id_col] = df["txid"].apply(
                lambda x: (
                    f'<a href="{tx_url_base.format(txid=x)}" target="_blank">{html.escape(str(x))}</a>'
                    if x
                    else ""
                )
            )

        if (dir_col := rename_map.get("direction")) in export_df.columns:
            export_df[dir_col] = export_df[dir_col].apply(
                lambda x: html.escape(translate(str(x).capitalize()))
            )
        if (type_col := rename_map.get("type")) in export_df.columns:
            export_df[type_col] = export_df[type_col].apply(
                lambda x: html.escape(translate(str(x).capitalize()))
            )

        is_rtl: bool = CONFIG.get("language", "en") == "ar"
        body_tag: str = f'<body class="{"rtl" if is_rtl else ""}">'

        html_content: str = export_df.to_html(
            index=True,
            index_label=translate("No."),
            escape=False,
            classes="kaspa-table",
            justify="left",
        )
        report_title: str = translate("Kaspa Transaction Report")
        header: str = f"""
        <h1>{html.escape(report_title)}</h1>
        <div class="report-info">
            <p><strong>{translate("Kaspa Address")}:</strong> {html.escape(kaspa_address)}</p>
            {'<p><strong>' + translate('Address Name') + f':</strong> {html.escape(address_name)}</p>' if address_name else ''}
            <p><strong>{translate("Exported On")}:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        """
        footer: str = (
            f'<footer><p>{APP_NAME} {translate("Version")} {CONFIG.get("version", "N/A")}</p></footer>'
        )
        full_html: str = (
            f'<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{html.escape(report_title)}</title>{STYLE}</head>{body_tag}{header}{html_content}{footer}</body></html>'
        )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(full_html)
        return True, "Export Successful", os.path.basename(file_path)
    except Exception as e:
        logger.error(f"DataFrame to HTML Export Error: {e}", exc_info=True)
        return False, "Error", str(e)


def export_df_to_pdf(
    df: pd.DataFrame,
    file_path: str,
    kaspa_address: str,
    address_name: str,
    currency: str,
    known_names_map: Dict[str, str],
    **kwargs: Any,
) -> Tuple[bool, str, str]:
    """
    Exports a DataFrame to a PDF file.
    """
    if not REPORTLAB_AVAILABLE:
        return False, "Error", "Missing required PDF libraries."
    if not file_path.lower().endswith(".pdf"):
        file_path += ".pdf"

    try:
        is_rtl: bool = CONFIG.get("language", "en") == "ar"
        styles = getSampleStyleSheet()
        story: List[Any] = [
            create_paragraph(
                translate("Kaspa Transaction Report"), styles["h1"], is_rtl
            )
        ]
        story.append(
            create_paragraph(
                f"{translate('Kaspa Address')}: {kaspa_address}",
                styles["Normal"],
                is_rtl,
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

        export_df, value_col_name, rename_map = _prepare_dataframe_for_export(
            df, currency, known_names_map
        )

        if (ts_col := rename_map.get("timestamp")) in export_df.columns:
            export_df[ts_col] = export_df[ts_col].dt.strftime("%Y-%m-%d %H:%M:%S")

        if value_col_name in export_df.columns:
            export_df[value_col_name] = export_df[value_col_name].apply(
                lambda x: f"{x:,.2f} {currency.upper()}" if pd.notnull(x) else "N/A"
            )

        if (amount_col := rename_map.get("amount")) in export_df.columns:
            export_df[amount_col] = export_df[amount_col].apply(
                lambda x: f"{x:,.8f}" if pd.notnull(x) else "N/A"
            )

        if (dir_col := rename_map.get("direction")) in export_df.columns:
            export_df[dir_col] = export_df[dir_col].apply(
                lambda x: translate(str(x).capitalize())
            )
        if (type_col := rename_map.get("type")) in export_df.columns:
            export_df[type_col] = export_df[type_col].apply(
                lambda x: translate(str(x).capitalize())
            )

        data_list: List[List[Any]] = [export_df.columns.tolist()] + cast(
            List[List[Any]], export_df.values.tolist()
        )

        doc_width: float = landscape(letter)[0] - inch
        relative_widths: Dict[str, float] = {
            rename_map.get("timestamp", "ts"): 0.10,
            rename_map.get("txid", "txid"): 0.26,
            rename_map.get("direction", "dir"): 0.06,
            rename_map.get("from_address", "from"): 0.15,
            rename_map.get("to_address", "to"): 0.15,
            rename_map.get("amount", "amt"): 0.08,
            value_col_name: 0.08,
            rename_map.get("block_height", "bh"): 0.06,
            rename_map.get("type", "type"): 0.06,
        }
        col_widths: List[float] = [
            doc_width * relative_widths.get(str(col), 0.1) for col in export_df.columns
        ]

        table = Table(data_list, colWidths=col_widths, repeatRows=1, hAlign="CENTER")

        align_val: str = "RIGHT" if is_rtl else "LEFT"
        style_commands: List[Tuple[str, Tuple[int, int], Tuple[int, int], Any]] = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#007bff")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONT", (0, 0), (-1, 0), "DejaVuSans-Bold", 8),
            ("FONT", (0, 1), (-1, -1), "DejaVuSans", 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), align_val),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]

        if not is_rtl:
            col_map: Dict[str, int] = {
                name: i for i, name in enumerate(export_df.columns)
            }
            if (dir_col := rename_map.get("direction")) in col_map:
                style_commands.append(
                    ("ALIGN", (col_map[dir_col], 1), (col_map[dir_col], -1), "CENTER")
                )
            if (type_col := rename_map.get("type")) in col_map:
                style_commands.append(
                    ("ALIGN", (col_map[type_col], 1), (col_map[type_col], -1), "CENTER")
                )
            if (amount_col := rename_map.get("amount")) in col_map:
                style_commands.append(
                    (
                        "ALIGN",
                        (col_map[amount_col], 1),
                        (col_map[amount_col], -1),
                        "RIGHT",
                    )
                )
            if value_col_name in col_map:
                style_commands.append(
                    (
                        "ALIGN",
                        (col_map[value_col_name], 1),
                        (col_map[value_col_name], -1),
                        "RIGHT",
                    )
                )

        table.setStyle(TableStyle(style_commands))
        story.append(table)

        doc = ReportPDFTemplate(
            file_path,
            pagesize=landscape(letter),
            leftMargin=0.5 * inch,
            rightMargin=0.5 * inch,
            topMargin=0.5 * inch,
            bottomMargin=0.8 * inch,
        )
        doc.build(story)

        return True, "Export Successful", os.path.basename(file_path)
    except Exception as e:
        logger.error(f"DataFrame to PDF Export Error: {e}", exc_info=True)
        return False, "Error", str(e)
