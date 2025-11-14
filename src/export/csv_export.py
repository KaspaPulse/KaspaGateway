import pandas as pd
import logging
import os
from typing import Tuple
from datetime import datetime
from src.utils.i18n import translate
from src.config.config import APP_NAME, APP_VERSION, get_active_api_config

logger = logging.getLogger(__name__)

def export_to_csv(df: pd.DataFrame, file_path: str, kaspa_address: str, address_name: str, currency: str, **kwargs) -> Tuple[bool, str, str]:
    if not file_path.lower().endswith('.csv'):
        file_path += '.csv'
    try:
        export_df = df.copy(deep=True)
        api_config = get_active_api_config()
        tx_url_base = api_config['explorer']['transaction']

        if 'direction' in export_df.columns:
            export_df['direction'] = export_df['direction'].apply(lambda x: translate(str(x).capitalize()))
        if 'type' in export_df.columns:
            export_df['type'] = export_df['type'].apply(lambda x: translate(str(x).capitalize()))
        if 'timestamp' in export_df.columns:
            export_df['Date/Time'] = pd.to_datetime(export_df['timestamp'], unit='s').dt.tz_localize(None)
        if 'txid' in export_df.columns:
            export_df['Transaction URL'] = export_df['txid'].apply(lambda x: tx_url_base.format(txid=x))
            
        currency_upper = currency.upper()
        value_col_key = f"value_{currency.lower()}"
        value_col_name = translate(f"Value ({currency_upper})")

        if value_col_key in export_df.columns:
            export_df[value_col_key] = export_df[value_col_key].apply(lambda x: f"{x:,.2f} {currency_upper}" if pd.notnull(x) else "N/A")

        rename_map = {
            'txid': translate('Transaction ID'),
            'direction': translate('Direction'),
            'from_address': translate('From Address(es)'),
            'to_address': translate('To Address(es)'),
            'amount': translate('Amount (KAS)'),
            'block_height': translate('Block Score'),
            'type': translate('Type:'),
            value_col_key: value_col_name
        }
        cols_to_rename = {k: v for k, v in rename_map.items() if k in export_df.columns}
        export_df.rename(columns=cols_to_rename, inplace=True)
        
        timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"Exporting data to CSV: {file_path}")
        
        with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(f'# {APP_NAME} {translate("Version")} {APP_VERSION}\n')
            f.write(f'# {translate("Kaspa Address")}: {kaspa_address}\n')
            if address_name:
                f.write(f'# {translate("Address Name")}: {address_name}\n')
            f.write(f'# {translate("Currency")}: {currency_upper}\n')
            f.write(f'# {translate("Exported On")}: {timestamp_str}\n\n')
            export_df.to_csv(f, index=False)
            
        return True, "Export Successful", os.path.basename(file_path)
    except (OSError, KeyError, Exception) as e:
        logger.error(f"CSV Export Error: {e}")
        return False, "Error", str(e)