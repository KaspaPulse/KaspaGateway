import logging
import threading
import time
from typing import TYPE_CHECKING, Callable, Optional, Tuple

from src.api.network import fetch_network_stats
from src.utils.errors import APIError

if TYPE_CHECKING:
    from src.database import AppDataDB
    from src.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


class NetworkUpdater:
    def __init__(
        self, main_window: "MainWindow", db: "AppDataDB", update_interval_sec: int = 180
    ):
        self.main_window = main_window
        self.db = db
        self.update_interval = update_interval_sec
        self.update_callback: Optional[Callable[[float, float], None]] = None
        self.hashrate, self.difficulty = 0.0, 0.0
        self.last_updated_ts = 0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.initial_fetch_complete = threading.Event()
        logger.info("NetworkUpdater initialized.")

    def get_stats(self) -> Tuple[float, float]:
        return self.hashrate, self.difficulty

    def get_last_updated_ts(self) -> int:
        return self.last_updated_ts

    def get_thread(self) -> Optional[threading.Thread]:
        return self._thread

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._update_loop, daemon=True, name="NetworkUpdateScheduler"
        )
        self._thread.start()
        logger.info("NetworkUpdater service started and scheduled.")

    def stop(self):
        self._stop_event.set()
        logger.info("NetworkUpdater stop requested.")

    def initial_fetch(self):
        logger.info("Performing initial network stats fetch from cache or worker.")
        self.initial_fetch_complete.clear()
        cached = self.db.get_cached_network_data()
        if cached:
            self.hashrate, self.difficulty = cached
            if self.update_callback:
                self.update_callback(self.hashrate, self.difficulty)
            logger.info("NetworkUpdater loaded initial data from cache.")
            self.initial_fetch_complete.set()
        else:
            threading.Thread(
                target=self._fetch_and_update_worker,
                daemon=True,
                name="InitialNetworkWorker",
            ).start()

    def _fetch_and_update_worker(self):
        logger.debug("Fetching network stats in background worker.")
        try:
            stats = fetch_network_stats()
            hashrate = stats.get("hashrate")
            difficulty = stats.get("difficulty")

            if hashrate is not None and difficulty is not None:
                hashrate_float = float(hashrate)
                difficulty_float = float(difficulty)

                if hashrate_float >= 0 and difficulty_float > 0:
                    self.hashrate, self.difficulty = hashrate_float, difficulty_float
                    self.db.save_cached_network_data(self.hashrate, self.difficulty)
                    self.last_updated_ts = int(time.time())
                    if self.update_callback and self.main_window.winfo_exists():
                        self.main_window.after(
                            0, self.update_callback, self.hashrate, self.difficulty
                        )
        except APIError as e:
            logger.warning(
                f"API error fetching network stats: {e}. Using last known values."
            )
        except (ValueError, TypeError) as e:
            logger.error(f"Type or Value error processing network data: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching network data: {e}")
        finally:
            self.initial_fetch_complete.set()

    def _update_loop(self):
        while not self._stop_event.is_set():
            self._fetch_and_update_worker()
            self._stop_event.wait(timeout=self.update_interval)
        logger.info("NetworkUpdater thread stopped.")
