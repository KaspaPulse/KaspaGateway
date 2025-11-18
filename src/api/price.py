# File: src/api/price.py

from __future__ import annotations

import json
import logging
from typing import Dict, Optional

from src.api.network import _make_api_request, _sanitize_url_for_logging
from src.config.config import CONFIG, get_active_api_config
from src.utils.errors import APIError
from src.utils.validation import _sanitize_for_logging

logger = logging.getLogger(__name__)


def get_kaspa_prices() -> Optional[Dict[str, float]]:
    """
    Fetches Kaspa prices for supported currencies from CoinGecko.

    Returns:
        A dictionary mapping currency codes (lowercase) to their float prices,
        or None if the request fails or data is invalid.
    """
    api_config = get_active_api_config()
    api_url_template = api_config["external"]["coingecko"]
    if not api_url_template or not isinstance(api_url_template, str):
        logger.error("CoinGecko API URL is not configured.")
        return None

    try:
        supported_currencies: List[str] = CONFIG["display"].get(
            "supported_currencies", ["usd"]
        )
        currencies_str = ",".join(supported_currencies).lower()
        api_url = api_url_template.format(supported_currencies=currencies_str)
    except Exception as e:
        logger.error(f"Failed to format CoinGecko URL: {e}")
        return None

    try:
        logger.info(
            f"Fetching prices from CoinGecko API: {_sanitize_url_for_logging(api_url)}"
        )
        data = _make_api_request(api_url)
        if not data:
            raise APIError("No data received from CoinGecko API.")

        kaspa_data = data.get("kaspa")
        if not isinstance(kaspa_data, dict):
            raise APIError(
                "Unexpected data format from CoinGecko API: 'kaspa' key missing or not a dictionary."
            )

        prices = {k.lower(): float(v) for k, v in kaspa_data.items()}

        if all(p >= 0 for p in prices.values()):
            logger.info(
                f"Successfully fetched prices: {', '.join([f'{k.upper()}={v:.4f}' for k, v in prices.items() if v > 0])}"
            )
            return prices
        else:
            logger.warning(
                f"CoinGecko API returned invalid or incomplete prices: {_sanitize_for_logging(prices)}"
            )
            return None

    except APIError as e:
        logger.error(
            f"API request to CoinGecko failed after multiple retries: {_sanitize_for_logging(e)}"
        )
        raise APIError(f"Failed to fetch price data from CoinGecko: {e}") from e
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        logger.error(
            f"Failed to parse price data from CoinGecko: {_sanitize_for_logging(e)}"
        )
        raise APIError(f"Invalid data format from CoinGecko: {e}") from e
