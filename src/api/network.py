# File: src/api/network.py

from __future__ import annotations

import concurrent.futures
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from src.config.config import APP_NAME, APP_VERSION, CONFIG, get_active_api_config
from src.utils.errors import APIError
from src.utils.formatting import mask_address
from src.utils.validation import _sanitize_for_logging, sanitize_data_for_logging

logger = logging.getLogger(__name__)


_session = requests.Session()
_session.headers.update(
    {
        "User-Agent": f"{APP_NAME}/{APP_VERSION} (Windows NT 10.0; Win64; x64; contact@kaspapulse.com)"
    }
)


def _sanitize_url_for_logging(url: str) -> str:
    """Removes sensitive query parameters from a URL for safe logging."""
    try:
        parsed = urlparse(url)
        if not parsed.query:
            return url

        query_params: Dict[str, List[str]] = parse_qs(parsed.query)
        sensitive_keys: List[str] = [
            "key",
            "apikey",
            "token",
            "secret",
            "auth",
            "password",
            "signature",
            "private",
            "pin",
        ]

        for key in list(query_params.keys()):
            if any(s in key.lower() for s in sensitive_keys):
                query_params[key] = ["***REDACTED***"]

        new_query: str = urlencode(query_params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
    except Exception:
        return "[Failed to sanitize URL]"


def _make_api_request(url: str) -> Optional[Any]:
    """
    Makes a GET request to the specified URL with configured retries and backoff.

    Args:
        url: The URL to request.

    Returns:
         The JSON response as a Python object, or None if the request fails.
    """
    try:
        retry_attempts: int = int(CONFIG["performance"]["retry_attempts"])
        timeout: int = int(CONFIG["performance"]["timeout"])
        backoff_factor: float = float(CONFIG["performance"]["backoff_factor"])

        for attempt in range(retry_attempts):
            try:
                response = _session.get(url, timeout=timeout, verify=True)
                response.raise_for_status()
                return response.json()
            except (
                requests.exceptions.RequestException,
                requests.exceptions.HTTPError,
            ) as e:
                logger.warning(
                    f"API request to {_sanitize_url_for_logging(url)} failed on attempt {attempt + 1}/{retry_attempts}: {_sanitize_for_logging(e)}"
                )
                if attempt + 1 == retry_attempts:
                    raise APIError(
                        f"Failed to fetch data from {_sanitize_url_for_logging(url)} after {retry_attempts} attempts."
                    ) from e
                time.sleep((2**attempt) * backoff_factor)
    except APIError as e:
        logger.error(_sanitize_for_logging(e))
    return None


def fetch_address_balance(address: str) -> Optional[float]:
    """Fetches the balance for a single Kaspa address."""
    api_config: Dict[str, Any] = get_active_api_config()
    base: str = api_config["base_url"]
    endpoint: str = api_config["endpoints"]["balance"]
    url: str = f"{base}{endpoint.format(kaspaAddress=address)}"

    data: Optional[Any] = _make_api_request(url)
    try:
        if (
            isinstance(data, dict)
            and "balance" in data
            and data["balance"] is not None
            and isinstance(data["balance"], (int, float, str))
        ):
            # Convert sompi to KAS
            return float(data["balance"]) / 1e8

        logger.warning(
            f"Invalid or missing balance data structure for address {mask_address(address)}: {sanitize_data_for_logging(data)}"
        )
        return None
    except (ValueError, TypeError, KeyError) as e:
        logger.warning(
            f"Invalid or missing balance data received for address {mask_address(address)}: {sanitize_data_for_logging(data)} - Error: {_sanitize_for_logging(e)}"
        )
    return None


def fetch_address_names() -> Optional[List[Dict[str, str]]]:
    """Fetches the list of known address names."""
    api_config: Dict[str, Any] = get_active_api_config()
    url: str = f"{api_config['base_url']}{api_config['endpoints']['address_names']}"
    data: Optional[Any] = _make_api_request(url)

    return data if isinstance(data, list) else None


def fetch_top_addresses() -> Optional[List[Any]]:
    """Fetches the top addresses from the API."""
    api_config: Dict[str, Any] = get_active_api_config()
    url: str = f"{api_config['base_url']}{api_config['endpoints']['top_addresses']}"
    data: Optional[Any] = _make_api_request(url)
    # The API might return a list of lists/objects or a single dict containing the ranking list.
    # We return the raw data and let the consumer handle the structure (TopAddressesTab)
    return data if isinstance(data, (list, dict)) or data is None else None


def fetch_network_stats() -> Dict[str, Optional[float]]:
    """Fetches the current network hashrate and difficulty."""
    stats: Dict[str, Optional[float]] = {"hashrate": None, "difficulty": None}
    api_config: Dict[str, Any] = get_active_api_config()
    base: str = api_config["base_url"]

    try:
        url_hash: str = f"{base}{api_config['endpoints']['hashrate']}"
        hashrate_data: Optional[Any] = _make_api_request(url_hash)
        if (
            isinstance(hashrate_data, dict)
            and "hashrate" in hashrate_data
            and hashrate_data["hashrate"] is not None
        ):
            # Convert H/s to PH/s
            stats["hashrate"] = float(hashrate_data["hashrate"]) / 1000.0
    except (ValueError, TypeError, APIError) as e:
        logger.error(
            f"Failed to parse or fetch hashrate data: {_sanitize_for_logging(e)}",
            exc_info=False,
        )

    try:
        url_diff: str = f"{base}{api_config['endpoints']['network']}"
        difficulty_data: Optional[Any] = _make_api_request(url_diff)
        if (
            isinstance(difficulty_data, dict)
            and "difficulty" in difficulty_data
            and difficulty_data["difficulty"] is not None
        ):
            stats["difficulty"] = float(difficulty_data["difficulty"])
    except (ValueError, TypeError, APIError) as e:
        logger.error(
            f"Failed to parse or fetch difficulty data: {_sanitize_for_logging(e)}",
            exc_info=False,
        )

    return stats


def fetch_kaspa_info() -> Dict[str, Any]:
    """Fetches a comprehensive set of Kaspa network info endpoints in parallel."""
    info_data: Dict[str, Any] = {}
    api_config: Dict[str, Any] = get_active_api_config()
    base: str = api_config["base_url"]

    info_endpoints: Dict[str, str] = {
        "network": "network",
        "kaspad": "kaspad",
        "blockdag": "blockdag_info",
        "coinsupply": "coinsupply",
        "halving": "halving",
        "hashrate": "hashrate",
        "blockreward": "blockreward",
        "maxhashrate": "max_hashrate",
    }

    def fetch_endpoint(
        key_endpoint_tuple: Tuple[str, str],
    ) -> Tuple[str, Optional[Any]]:
        """Helper function to fetch a single endpoint."""
        key, endpoint_key = key_endpoint_tuple
        endpoint: Optional[str] = api_config["endpoints"].get(endpoint_key)
        if endpoint:
            url: str = f"{base}{endpoint}"
            data: Optional[Any] = _make_api_request(url)
            if data and isinstance(data, (dict, list)):
                return key, data
        return key, None

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(info_endpoints)
    ) as executor:
        future_to_endpoint: Dict[
            concurrent.futures.Future[Tuple[str, Optional[Any]]], Tuple[str, str]
        ] = {
            executor.submit(fetch_endpoint, item): item
            for item in info_endpoints.items()
        }
        for future in concurrent.futures.as_completed(future_to_endpoint):
            try:
                key, data = future.result()
                if data:
                    info_data[key] = data
            except Exception as e:
                logger.error(
                    f"Error fetching endpoint data in parallel: {_sanitize_for_logging(e)}"
                )

    return info_data


def fetch_latest_release_info(api_url: str) -> Optional[Dict[str, Any]]:
    """
    Fetches release information from a specific GitHub API URL.
    """
    logger.info(
        f"Fetching latest release info from: {_sanitize_url_for_logging(api_url)}"
    )

    # Use the existing robust _make_api_request function
    data: Optional[Any] = _make_api_request(api_url)

    if isinstance(data, dict):
        return data
    else:
        logger.warning(f"Unexpected data format received from GitHub API: {type(data)}")
        return None
