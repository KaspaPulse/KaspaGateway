import json
import logging
import threading
import time
from typing import TYPE_CHECKING, Callable, Dict, Optional

from src.api.price import get_kaspa_prices
from src.utils.errors import APIError

if TYPE_CHECKING:
    from src.database import AppDataDB
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


class PriceUpdater:
    def __init__(
        self, main_window: "MainWindow", db: "AppDataDB", update_interval_sec: int = 600
    ) -> None:
        self.main_window = main_window
        self.db = db
        self.update_interval = update_interval_sec
        self.update_callback: Optional[Callable[[Dict[str, float]], None]] = None
        self.current_prices: Dict[str, float] = {}
        self.last_updated_ts: int = 0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.initial_fetch_complete = threading.Event()
        logger.info("PriceUpdater initialized.")

    def get_current_prices(self) -> Dict[str, float]:
        return self.current_prices

    def get_last_updated_ts(self) -> int:
        return self.last_updated_ts

    def get_thread(self) -> Optional[threading.Thread]:
        return self._thread

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._update_loop, daemon=True, name="PriceUpdateScheduler"
        )
        self._thread.start()
        logger.info("PriceUpdater service started and scheduled.")

    def stop(self) -> None:
        self._stop_event.set()
        logger.info("PriceUpdater stop requested.")

    def initial_fetch(self) -> None:
        logger.info("Performing initial price fetch from cache or worker.")
        self.initial_fetch_complete.clear()
        cached_prices = self.db.get_cached_prices()
        if cached_prices:
            self.current_prices = cached_prices
            # self.last_updated_ts = self.db.get_latest_price_timestamp() # This method doesn't exist, get from file mod time or similar if needed
            if self.update_callback:
                self.update_callback(self.current_prices)
            logger.info("PriceUpdater loaded initial data from cache.")
            self.initial_fetch_complete.set()
        else:
            threading.Thread(
                target=self._fetch_and_update_worker,
                daemon=True,
                name="InitialPriceWorker",
            ).start()

    def _fetch_and_update_worker(self) -> None:
        logger.debug("Fetching prices in background worker.")
        try:
            if prices := get_kaspa_prices():
                self.current_prices = prices
                prices_json_string = json.dumps(prices)
                self.db.save_cached_prices(prices_json_string)
                self.last_updated_ts = int(time.time())
                if self.update_callback:
                    if self.main_window.winfo_exists():
                        self.main_window.after(
                            0, self.update_callback, self.current_prices
                        )
        except APIError:
            logger.warning("API error fetching prices. Using last known values.")
        except Exception as e:
            logger.error(f"Unexpected error fetching price data: {e}")
        finally:
            self.initial_fetch_complete.set()

    def _update_loop(self) -> None:
        while not self._stop_event.is_set():
            self._fetch_and_update_worker()
            self._stop_event.wait(timeout=self.update_interval)
        logger.info("PriceUpdater thread stopped.")
