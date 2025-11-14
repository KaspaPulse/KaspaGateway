import pandas as pd
import logging
import os
from typing import Tuple
import html
from datetime import datetime
from src.utils.i18n import translate
from src.config.config import APP_NAME, APP_VERSION, get_active_api_config

logger = logging.getLogger(__name__)

STYLE = '''
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
'''

def export_to_html(df: pd.DataFrame, file_path: str, kaspa_address: str, address_name: str, currency: str, **kwargs) -> Tuple[bool, str, str]:
    if not file_path.lower().endswith('.html'):
        file_path += '.html'
    try:
        api_config = get_active_api_config()
        addr_url_base = api_config['explorer']['address']
        tx_url_base = api_config['explorer']['transaction']

        is_rtl = get_active_api_config().get("language", "en") == "ar"
        body_tag = f'<body class="{"rtl" if is_rtl else ""}">'
        export_df = df.copy(deep=True)
        if 'status' in export_df.columns:
            export_df.drop(columns=['status'], inplace=True)
        export_df = export_df.reset_index(drop=True)
        export_df.insert(0, translate('No.'), range(1, len(export_df) + 1))
        
        export_columns = [translate('No.')]
        
        column_definitions = [
            ('timestamp', 'Date/Time', lambda x: pd.to_datetime(x, unit='s').strftime('%Y-%m-%d %H:%M:%S')),
            ('txid', 'Transaction ID', lambda x: f"<a href='{tx_url_base.format(txid=x)}' target='_blank'>{html.escape(x)}</a>"),
            ('direction', 'Direction', lambda x: html.escape(translate(str(x).capitalize()))),
            ('amount', 'Amount (KAS)', lambda x: f"{x:,.8f}"),
            (f"value_{currency.lower()}", f"Value ({currency.upper()})", lambda x: f"{x:,.2f} {currency.upper()}" if pd.notnull(x) else "N/A"),
            ('block_height', 'Block Score', lambda x: str(x)),
            ('type', 'Type', lambda x: html.escape(translate(str(x).capitalize())))
        ]

        for col_key, col_name_key, formatter in column_definitions:
            if col_key in export_df.columns:
                col_name = translate(col_name_key)
                export_df[col_name] = export_df[col_key].apply(formatter)
                export_columns.append(col_name)

        html_table = export_df[export_columns].to_html(index=False, border=0, classes='kaspa-table', escape=False)
        timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        address_name_html = f'<p><strong>{translate("Address Name")}:</strong> {html.escape(address_name)}</p>' if address_name else ""
        report_header = f'''
        <div class="report-info">
            <p><strong>{translate("Kaspa Address")}:</strong> <a href='{addr_url_base.format(kaspaAddress=kaspa_address)}' target='_blank'>{html.escape(kaspa_address)}</a></p>
            {address_name_html}
            <p><strong>{translate("Currency")}:</strong> {html.escape(currency.upper())}</p>
        </div>
        '''
        footer = f'''
        <footer>
            <p>{APP_NAME} {translate('Version')} {APP_VERSION}</p>
            <p>{translate("Exported On")}: {timestamp_str}</p>
        </footer>
        '''
        html_title = f"{APP_NAME} - {translate('Kaspa Transaction Report')}"
        report_title = translate("Kaspa Transaction Report") 
        full_html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{html.escape(html_title)}</title>{STYLE}</head>{body_tag}<h1>{html.escape(report_title)}</h1>{report_header}{html_table}{footer}</body></html>'
        
        logger.info(f"Exporting data to HTML: {file_path}")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(full_html)
            
        return True, "Export Successful", os.path.basename(file_path)
    except Exception as e:
        logger.error(f"HTML Export Error: {e}")
        return False, "Error", str(e)