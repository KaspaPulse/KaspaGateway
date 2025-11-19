import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd

from src.config.config import APP_NAME, CONFIG, get_active_api_config
from src.utils.i18n import translate
from src.utils.validation import sanitize_csv_cell

logger = logging.getLogger(__name__)


def export_analysis_to_csv(
    file_path: str,
    kaspa_address: str,
    address_name: str,
    currency: str,
    counterparties: Dict[str, List[Dict[str, Any]]],
    known_names_map: Dict[str, str],
    **kwargs,
) -> Tuple[bool, str, str]:
    if not file_path.lower().endswith(".csv"):
        file_path += ".csv"

    try:
        api_config = get_active_api_config()
        addr_url_base = api_config["explorer"]["address"]
        tx_url_base = api_config["explorer"]["transaction"]

        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Exporting analysis data to CSV: {file_path}")

        with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(f'# {APP_NAME} {translate("Version")} {CONFIG["version"]}\n')
            f.write(
                f'# {translate("Analysis Report for Kaspa Address")}: {sanitize_csv_cell(kaspa_address)}\n'
            )
            if address_name:
                f.write(
                    f'# {translate("Address Name")}: {sanitize_csv_cell(address_name)}\n'
                )
            f.write(f'# {translate("Currency")}: {currency.upper()}\n')
            f.write(f'# {translate("Exported On")}: {timestamp_str}\n\n')

            for cp_address, tx_list in counterparties.items():
                cp_name = known_names_map.get(cp_address, "")
                f.write(
                    f'# {translate("Counterparty")}: {sanitize_csv_cell(cp_address)}\n'
                )
                f.write(
                    f"# Counterparty URL: {addr_url_base.format(kaspaAddress=cp_address)}\n"
                )
                if cp_name:
                    f.write(
                        f'# {translate("Known Name")}: {sanitize_csv_cell(cp_name)}\n'
                    )

                if not tx_list:
                    f.write(
                        f'# {translate("No transactions for this counterparty.")}\n\n'
                    )
                    continue

                df = pd.DataFrame(tx_list)
                export_df = df.copy(deep=True)

                if "direction" in export_df.columns:
                    export_df["direction"] = export_df["direction"].apply(
                        lambda x: sanitize_csv_cell(translate(str(x).capitalize()))
                    )
                if "type" in export_df.columns:
                    export_df["type"] = export_df["type"].apply(
                        lambda x: sanitize_csv_cell(translate(str(x).capitalize()))
                    )
                if "timestamp" in export_df.columns:
                    export_df["Date/Time"] = pd.to_datetime(
                        export_df["timestamp"], unit="s"
                    ).dt.tz_localize(None)

                if "txid" in export_df.columns:
                    export_df["Transaction URL"] = export_df["txid"].apply(
                        lambda x: tx_url_base.format(txid=x)
                    )

                export_df["txid"] = export_df["txid"].apply(sanitize_csv_cell)

                value_col_key = f"value_{currency.lower()}"
                value_col_name = translate(f"Value ({currency.upper()})")

                if (
                    value_col_key not in export_df.columns
                    and "amount" in export_df.columns
                ):
                    price = 0
                    if (
                        tx_list
                        and tx_list[0].get("amount")
                        and tx_list[0].get(value_col_key)
                    ):
                        price = tx_list[0].get(value_col_key, 0) / tx_list[0].get(
                            "amount", 1
                        )
                    export_df[value_col_key] = export_df["amount"] * price

                if value_col_key in export_df.columns:
                    export_df[value_col_key] = (
                        export_df[value_col_key]
                        .apply(
                            lambda x: (
                                f"{x:,.2f} {currency.upper()}"
                                if pd.notnull(x)
                                else "N/A"
                            )
                        )
                        .apply(sanitize_csv_cell)
                    )

                rename_map = {
                    "txid": translate("Transaction ID"),
                    "direction": translate("Direction"),
                    "amount": translate("Amount (KAS)"),
                    "block_height": translate("Block Score"),
                    "type": translate("Type"),
                    value_col_key: value_col_name,
                }

                cols_to_rename = {
                    k: v for k, v in rename_map.items() if k in export_df.columns
                }
                export_df.rename(columns=cols_to_rename, inplace=True)

                display_cols = [
                    "Date/Time",
                    translate("Transaction ID"),
                    "Transaction URL",
                    translate("Direction"),
                    translate("Amount (KAS)"),
                    value_col_name,
                    translate("Block Score"),
                    translate("Type"),
                ]

                final_cols = [col for col in display_cols if col in export_df.columns]

                export_df[final_cols].to_csv(f, index=False, float_format="%.8f")

                total_amount = df["amount"].sum()
                total_value = (
                    df[f"value_{currency.lower()}"].sum()
                    if f"value_{currency.lower()}" in df
                    else 0
                )
                summary_row = [""] * len(final_cols)

                try:
                    summary_row[final_cols.index(translate("Amount (KAS)"))] = (
                        sanitize_csv_cell(f"{total_amount:,.8f}")
                    )
                    summary_row[final_cols.index(value_col_name)] = sanitize_csv_cell(
                        f"{total_value:,.2f} {currency.upper()}"
                    )
                    summary_row[final_cols.index(translate("Direction"))] = (
                        sanitize_csv_cell(translate("Total"))
                    )
                except (ValueError, IndexError):
                    pass
                f.write(",".join(f'"{item}"' for item in summary_row) + "\n")
                f.write("\n\n")

        return True, "Export Successful", os.path.basename(file_path)
    except (OSError, KeyError, Exception) as e:
        logger.error(f"CSV Export Error: {e}")
        return False, "Error", str(e)
