import pandas as pd
import logging
import os
from typing import Tuple
from datetime import datetime
from src.utils.i18n import translate
from src.config.config import APP_NAME, APP_VERSION, get_active_api_config
from src.utils.validation import sanitize_csv_cell

logger = logging.getLogger(__name__)

def export_top_addresses_to_csv(df: pd.DataFrame, file_path: str, currency: str) -> Tuple[bool, str, str]:
    if not file_path.lower().endswith('.csv'):
        file_path += '.csv'
    try:
        export_df = df.copy(deep=True)
        api_config = get_active_api_config()
        addr_url_base = api_config['explorer']['address']
        export_df['Address URL'] = export_df['Address'].apply(lambda x: addr_url_base.format(kaspaAddress=x))
        
        export_df['Known Name'] = export_df['Known Name'].apply(sanitize_csv_cell)
        export_df['Address'] = export_df['Address'].apply(sanitize_csv_cell)

        currency_upper = currency.upper()
        value_col_name = translate(f"Value ({currency_upper})")
        if 'Value' in export_df.columns:
            export_df['ValueFormatted'] = export_df['Value'].apply(lambda x: f"{x:,.2f} {currency_upper}")
        rename_map = {
            'Rank': translate('Rank'),
            'Known Name': translate('Known Name'),
            'Address': translate('Address'),
            'Balance': translate('Balance (KAS)'),
            'ValueFormatted': value_col_name
        }
        export_df.rename(columns=rename_map, inplace=True)
        timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"Exporting top addresses to CSV: {file_path}")
        
        with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(f'# {APP_NAME} {translate("Version")} {APP_VERSION}\n')
            f.write(f'# {translate("Top Addresses")}\n')
            f.write(f'# {translate("Currency")}: {currency_upper}\n')
            f.write(f'# {translate("Exported On")}: {timestamp_str}\n\n')
            final_cols = [
                translate('Rank'), translate('Known Name'), translate('Address'), 
                'Address URL', translate('Balance (KAS)'), value_col_name
            ]
            export_df[final_cols].to_csv(f, index=False, float_format='%.8f')
        return True, "Export Successful", os.path.basename(file_path)
    except (OSError, KeyError, Exception) as e:
        logger.error(f"Top Addresses CSV Export Error: {e}")
        return False, "Error", str(e)