from __future__ import annotations

import pandas as pd
import logging
import os
import base64
import io
import html
from typing import Tuple, Dict, Any, List, Optional, Callable
from datetime import datetime

from src.utils.i18n import translate
from src.config.config import CONFIG, APP_NAME, get_active_api_config

logger = logging.getLogger(__name__)

STYLE: str = '''
<style>
    body { font-family: 'Segoe UI', Arial, sans-serif; margin: 2em; background-color: #f4f4f9; color: #333; }
    .rtl { direction: rtl; text-align: right; }
    h1, h2, h3 { color: #007bff; border-bottom: 2px solid #dee2e6; padding-bottom: 10px; }
    h3 { font-size: 1.2em; color: #495057; border-bottom-style: dashed; margin-top: 2.5em; }
    .report-info, .summary-grid { background-color: #e9ecef; padding: 15px; border-radius: 8px; margin-bottom: 2em; }
    .report-info p { margin: 5px 0; }
    .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; }
    .summary-item { background-color: #fff; padding: 15px; border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .summary-item .title { font-weight: bold; color: #495057; font-size: 0.9em; }
    .summary-item .value { font-size: 1.5em; color: #007bff; font-weight: 600; }
    .kaspa-table { border-collapse: collapse; width: 100%; box-shadow: 0 2px 5px rgba(0,0,0,0.15); background-color: #fff; margin-top: 1em; margin-bottom: 2em;}
    .kaspa-table th, .kaspa-table td { border: 1px solid #ddd; padding: 12px; text-align: left; word-break: break-all; }
    .rtl .kaspa-table th, .rtl .kaspa-table td { text-align: right; }
    .kaspa-table th { background-color: #007bff; color: white; font-weight: bold; }
    .kaspa-table tr:nth-child(even) { background-color: #f9f9f9; }
    .kaspa-table tfoot tr { font-weight: bold; background-color: #e9ecef; }
    a { color: #0056b3; text-decoration: none; }
    a:hover { text-decoration: underline; }
    footer { text-align: center; margin-top: 2em; font-size: 0.8em; color: #6c757d; }
</style>
'''

def _df_to_html_table(df: pd.DataFrame, currency: str) -> str:
    """Converts a DataFrame of transactions to an HTML table with a summary footer."""
    if df.empty:
        return f"<p>{translate('No transactions for this counterparty.')}</p>"

    api_config: Dict[str, Any] = get_active_api_config()
    export_df = df.copy(deep=True).reset_index(drop=True)
    export_df.insert(0, translate('No.'), range(1, len(export_df) + 1))

    export_columns: List[str] = [translate('No.')]
    tx_url_base: str = api_config.get('explorer', {}).get('transaction', '')
    
    value_col_key = f"value_{currency.lower()}"
    value_col_name = translate(f"Value ({currency.upper()})")

    column_definitions: List[Tuple[str, str, Callable[[Any], str]]] = [
        ('timestamp', 'Date/Time', lambda x: pd.to_datetime(x, unit='s').strftime('%Y-%m-%d %H:%M:%S')),
        ('txid', 'Transaction ID', lambda x: f"<a href='{tx_url_base.format(txid=x)}' target='_blank'>{html.escape(x)}</a>" if tx_url_base else html.escape(x)),
        ('direction', 'Direction', lambda x: html.escape(translate(str(x).capitalize()))),
        ('amount', 'Amount (KAS)', lambda x: f"{x:,.8f}" if pd.notnull(x) else "N/A"),
        (value_col_key, value_col_name, lambda x: f"{x:,.2f} {html.escape(currency.upper())}" if pd.notnull(x) else "N/A"),
        ('block_height', 'Block Score', lambda x: str(x)),
        ('type', 'Type', lambda x: html.escape(translate(str(x).capitalize())))
    ]

    for col_key, col_name_key, formatter in column_definitions:
        if col_key in export_df.columns:
            col_name: str = col_name_key if col_key == value_col_key else translate(col_name_key)
            export_df[col_name] = export_df[col_key].apply(formatter)
            export_columns.append(col_name)

    table_html: str = export_df[export_columns].to_html(
        index=False, border=0, classes='kaspa-table',
        justify='left', escape=False
    )

    total_amount: float = df['amount'].sum()
    total_value: float = df[value_col_key].sum() if value_col_key in df else 0.0

    try:
        amount_idx: int = export_columns.index(translate('Amount (KAS)'))
        value_idx: int = export_columns.index(value_col_name)
        total_label_idx: int = amount_idx - 1
    except (ValueError, IndexError):
        return table_html

    footer_cells: str = ""
    for i in range(len(export_columns)):
        if i == total_label_idx:
            footer_cells += f"<td>{translate('Total')}</td>"
        elif i == amount_idx:
            footer_cells += f"<td style='text-align: left;'>{total_amount:,.8f}</td>"
        elif i == value_idx:
            footer_cells += f"<td style='text-align: left;'>{total_value:,.2f} {html.escape(currency.upper())}</td>"
        else:
            footer_cells += "<td></td>"
            
    footer_html: str = f"<tfoot><tr>{footer_cells}</tr></tfoot>"
    table_html = table_html.replace("</tbody>", f"{footer_html}</tbody>", 1)

    return table_html

def export_analysis_to_html(
    file_path: str,
    kaspa_address: str,
    address_name: str,
    currency: str,
    counterparties: Dict[str, List[Dict[str, Any]]],
    known_names_map: Dict[str, str],
    analysis_data: Optional[Dict[str, Any]] = None,
    **kwargs: Any
) -> Tuple[bool, str, str]:
    """
    Exports analysis data to a styled HTML file.
    (Chart functionality has been removed)
    """
    if not file_path.lower().endswith('.html'):
        file_path += '.html'
        
    try:
        is_rtl: bool = CONFIG.get("language", "en") == "ar"
        body_tag: str = f'<body class="{"rtl" if is_rtl else ""}">'
        timestamp_str: str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        addr_url_base: str = get_active_api_config().get('explorer', {}).get('address', '')
        
        address_name_html: str = f'<p><strong>{translate("Address Name")}:</strong> {html.escape(address_name)}</p>' if address_name else ""
        report_header: str = f'''
        <div class="report-info">
            <p><strong>{translate("Analysis Report for Kaspa Address")}:</strong> <a href='{addr_url_base.format(kaspaAddress=kaspa_address)}' target='_blank'>{html.escape(kaspa_address)}</a></p>
            {address_name_html}
            <p><strong>{translate("Currency")}:</strong> {html.escape(currency.upper())}</p>
        </div>
        '''
        
        footer: str = f'<footer><p>{APP_NAME} {translate("Version")} {CONFIG.get("version", "N/A")}</p><p>{translate("Exported On")}: {timestamp_str}</p></footer>'
        
        main_content: str = ""
        report_title_key: str = "Kaspa Analysis Report"

        if analysis_data:
            summary_html = f'<h2>{translate("Summary")}</h2><div class="summary-grid">'
            for key, value in analysis_data.get('summary', {}).items():
                summary_html += f'<div class="summary-item"><div class="title">{translate(key)}</div><div class="value">{html.escape(str(value))}</div></div>'
            summary_html += '</div>'
            main_content += summary_html
            
            # Chart section fully removed
            
        main_content += f'<h2>{translate("Counterparty Breakdown")}</h2>'
        for cp_address, tx_list in counterparties.items():
            cp_name: str = known_names_map.get(cp_address, "")
            cp_name_str: str = f"({html.escape(cp_name)})" if cp_name else ""
            cp_link: str = f'<a href="{addr_url_base.format(kaspaAddress=cp_address)}" target="_blank">{html.escape(cp_address)}</a>' if addr_url_base else html.escape(cp_address)
            main_content += f'<h3>{translate("Counterparty")}: {cp_link} {cp_name_str}</h3>'
            
            df_cp = pd.DataFrame(tx_list)
            main_content += _df_to_html_table(df_cp, currency)

        html_title: str = f"{APP_NAME} - {translate(report_title_key)}"
        full_html: str = f'<!DOCTYPE html><html lang="{CONFIG.get("language", "en")}"><html><head><meta charset="UTF-8"><title>{html.escape(html_title)}</title>{STYLE}</head>{body_tag}<h1>{html.escape(translate(report_title_key))}</h1>{report_header}{main_content}{footer}</body></html>'
        
        logger.info(f"Exporting data to HTML: {file_path}")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(full_html)
            
        return True, "Export Successful", os.path.basename(file_path)
    except Exception as e:
        logger.error(f"HTML Export Error: {e}", exc_info=True)
        return False, "Error", str(e)