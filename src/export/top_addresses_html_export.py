import html
import logging
import os
from datetime import datetime
from typing import Tuple

import pandas as pd

from src.config.config import APP_NAME, APP_VERSION, CONFIG, get_active_api_config
from src.utils.i18n import translate

logger = logging.getLogger(__name__)

STYLE = """
<style>
    body { font-family: 'Segoe UI', Arial, sans-serif; margin: 2em; background-color: #f4f4f9; color: #333; }
    .rtl { direction: rtl; text-align: right; }
    h1 { color: #007bff; }
    .report-info { background-color: #e9ecef; padding: 10px 15px; border-radius: 5px; margin-bottom: 2em; }
    .report-info p { margin: 5px 0; }
    .kaspa-table { border-collapse: collapse; width: 100%; box-shadow: 0 2px 5px rgba(0,0,0,0.15); background-color: #fff; }
    .kaspa-table th, .kaspa-table td { border: 1px solid #ddd; padding: 12px; text-align: left; word-break: break-all; }
    .rtl .kaspa-table th, .rtl .kaspa-table td { text-align: right; }
    .kaspa-table th { background-color: #007bff; color: white; font-weight: bold; }
    .kaspa-table tr:nth-child(even) { background-color: #f9f9f9; }
    a { color: #0056b3; text-decoration: none; }
    a:hover { text-decoration: underline; }
    footer { text-align: center; margin-top: 2em; font-size: 0.8em; color: #6c757d; }
</style>
"""


def export_top_addresses_to_html(
    df: pd.DataFrame, file_path: str, currency: str
) -> Tuple[bool, str, str]:
    if not file_path.lower().endswith(".html"):
        file_path += ".html"
    try:
        is_rtl = CONFIG.get("language", "en") == "ar"
        body_tag = f'<body class="{"rtl" if is_rtl else ""}">'
        export_df = df.copy(deep=True)
        export_df["Known Name"] = export_df["Known Name"].apply(
            lambda x: html.escape(str(x))
        )
        api_config = get_active_api_config()
        addr_url_base = api_config["explorer"]["address"]
        export_df["Address"] = export_df["Address"].apply(
            lambda x: f'<a href="{addr_url_base.format(kaspaAddress=x)}" target="_blank">{x}</a>'
        )
        currency_upper = currency.upper()
        value_col_name = translate(f"Value ({currency_upper})")
        if "Value" in export_df.columns:
            export_df["Value"] = export_df["Value"].apply(
                lambda x: f"{x:,.2f} {currency_upper}"
            )
        rename_map = {
            "Rank": translate("Rank"),
            "Known Name": translate("Known Name"),
            "Address": translate("Address"),
            "Balance": translate("Balance (KAS)"),
            "Value": value_col_name,
        }
        export_df.rename(columns=rename_map, inplace=True)
        final_cols = [
            translate("Rank"),
            translate("Known Name"),
            translate("Address"),
            translate("Balance (KAS)"),
            value_col_name,
        ]
        html_table = export_df[final_cols].to_html(
            index=False,
            border=0,
            classes="kaspa-table",
            escape=False,
            float_format="%.2f",
        )
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_header = f"""
        <div class="report-info">
            <p><strong>{translate("Top Addresses")}</strong></p>
            <p><strong>{translate("Currency")}:</strong> {currency_upper}</p>
        </div>
        """
        footer = f"""
        <footer>
            <p>{APP_NAME} {translate('Version')} {APP_VERSION}</p>
            <p>{translate("Exported On")}: {timestamp_str}</p>
        </footer>
        """
        html_title = f"{APP_NAME} - {translate('Top Addresses')}"
        report_title = translate("Top Addresses")
        full_html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{html_title}</title>{STYLE}</head>{body_tag}<h1>{report_title}</h1>{report_header}{html_table}{footer}</body></html>'
        logger.info(f"Exporting top addresses to HTML: {file_path}")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(full_html)
        return True, "Export Successful", os.path.basename(file_path)
    except Exception as e:
        logger.error(f"Top Addresses HTML Export Error: {e}")
        return False, "Error", str(e)
