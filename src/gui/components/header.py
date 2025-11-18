import logging
import webbrowser
from datetime import datetime
from typing import TYPE_CHECKING, Callable

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.tooltip import ToolTip

from src.config.config import CONFIG
from src.utils.i18n import get_available_languages, translate

if TYPE_CHECKING:
    from src.gui.config_manager import ConfigManager
    from src.gui.main_window import MainWindow
    from src.gui.theme_manager import ThemeManager

logger = logging.getLogger(__name__)


class Header(ttk.Frame):
    def __init__(
        self,
        parent: "MainWindow",
        price_var,
        hashrate_var,
        difficulty_var,
        clock_date_var,
        clock_time_var,
        theme_manager: "ThemeManager",
        currency_callback: Callable[[str], None],
        currency_var,
        lang_callback: Callable[[str], None],
        config_manager: "ConfigManager",
    ):
        super().__init__(parent)
        self.main_window = parent
        self.theme_manager = theme_manager
        self.config_manager = config_manager
        self.lang_callback = lang_callback
        self.currency_var = currency_var
        self._build_ui(
            price_var,
            hashrate_var,
            difficulty_var,
            clock_date_var,
            clock_time_var,
            currency_callback,
        )

    def _open_link(self, url):
        webbrowser.open(url, new=2)

    def _build_ui(
        self,
        price_var,
        hashrate_var,
        difficulty_var,
        clock_date_var,
        clock_time_var,
        currency_callback,
    ):
        self.grid_columnconfigure(1, weight=1)
        left_frame = ttk.Frame(self)
        left_frame.grid(row=0, column=0, sticky="w", padx=0, pady=5)

        title_version_frame = ttk.Frame(left_frame)
        title_version_frame.pack(side=LEFT, padx=(0, 20), anchor="s", fill="y")
        self.title_label = ttk.Label(
            title_version_frame,
            text=translate("KaspaGateway"),
            font="-size 20 -weight bold",
        )
        self.title_label.pack(side=TOP, anchor="sw")

        sub_title_frame = ttk.Frame(title_version_frame)
        sub_title_frame.pack(side=TOP, anchor="sw", pady=(0, 2), fill="x")

        self.version_label = ttk.Label(
            sub_title_frame,
            text=f"{translate('Version')} {CONFIG['version']}",
            font="-size 8",
            bootstyle="secondary",
        )
        self.version_label.pack(side=LEFT, anchor="s", padx=(0, 15))

        style = ttk.Style()
        link_font = "-size 8 -underline 1"

        links_frame = ttk.Frame(sub_title_frame)
        links_frame.pack(side=LEFT, anchor="s")

        self.donation_link = ttk.Label(
            links_frame,
            text=translate("Donations"),
            font="-size 8",
            foreground=style.colors.info,
            cursor="hand2",
        )
        self.donation_link.pack(side=LEFT, padx=5)
        self.donation_link.bind(
            "<Button-1>", lambda e: self._open_link(CONFIG["links"]["donation"])
        )
        self.donation_link.bind(
            "<Enter>", lambda e: self.donation_link.config(font=link_font)
        )
        self.donation_link.bind(
            "<Leave>", lambda e: self.donation_link.config(font="-size 8")
        )

        self.twitter_link = ttk.Label(
            links_frame,
            text="Twitter",
            font="-size 8",
            foreground=style.colors.info,
            cursor="hand2",
        )
        self.twitter_link.pack(side=LEFT, padx=5)
        self.twitter_link.bind(
            "<Button-1>", lambda e: self._open_link(CONFIG["links"]["twitter"])
        )
        self.twitter_link.bind(
            "<Enter>", lambda e: self.twitter_link.config(font=link_font)
        )
        self.twitter_link.bind(
            "<Leave>", lambda e: self.twitter_link.config(font="-size 8")
        )

        self.github_link = ttk.Label(
            links_frame,
            text="GitHub",
            font="-size 8",
            foreground=style.colors.info,
            cursor="hand2",
        )
        self.github_link.pack(side=LEFT, padx=5)
        self.github_link.bind(
            "<Button-1>", lambda e: self._open_link(CONFIG["links"]["github"])
        )
        self.github_link.bind(
            "<Enter>", lambda e: self.github_link.config(font=link_font)
        )
        self.github_link.bind(
            "<Leave>", lambda e: self.github_link.config(font="-size 8")
        )

        self.price_label, self.price_frame = self._create_stat_frame(
            left_frame, "Price", price_var, "info"
        )
        self.hashrate_label, self.hashrate_frame = self._create_stat_frame(
            left_frame, "Hashrate", hashrate_var, "success"
        )
        self.difficulty_label, self.difficulty_frame = self._create_stat_frame(
            left_frame, "Difficulty", difficulty_var, "warning"
        )

        self.price_tooltip = ToolTip(self.price_frame, text="N/A")
        self.hashrate_tooltip = ToolTip(self.hashrate_frame, text="N/A")
        self.difficulty_tooltip = ToolTip(self.difficulty_frame, text="N/A")

        right_frame = ttk.Frame(self)
        right_frame.grid(row=0, column=2, sticky="e", padx=0, pady=5)

        clock_frame = ttk.Frame(right_frame)
        clock_frame.pack(side=LEFT, padx=(0, 15))
        ttk.Label(clock_frame, textvariable=clock_date_var, font="-size 10").pack(
            anchor="e"
        )
        ttk.Label(
            clock_frame, textvariable=clock_time_var, font="-size 12 -weight bold"
        ).pack(anchor="e")

        self.lang_frame = ttk.Frame(right_frame)
        self.lang_frame.pack(side=LEFT, padx=(0, 15))
        self.lang_label = ttk.Label(
            self.lang_frame, text=f"{translate('Language')}:", font="-size 10"
        )
        self.lang_label.pack(anchor="w")
        self._setup_language_dropdown()

        theme_frame = ttk.Frame(right_frame)
        theme_frame.pack(side=LEFT, padx=(0, 15))
        self.theme_label = ttk.Label(
            theme_frame, text=f"{translate('Theme')}:", font="-size 10"
        )
        self.theme_label.pack(anchor="w")

        # Define the new curated list of themes
        professional_themes = ["superhero", "litera", "darkly"]

        self.theme_combo = ttk.Combobox(
            theme_frame, values=professional_themes, state="readonly", width=12
        )

        # Ensure the current theme is valid, otherwise set to new default
        current_theme = self.theme_manager.get_current_theme()
        if current_theme not in professional_themes:
            current_theme = "superhero"

        self.theme_combo.set(current_theme)
        self.theme_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: self.theme_manager.apply_theme(self.theme_combo.get()),
        )
        self.theme_combo.bind(
            "<Button-1>", lambda e: self.theme_combo.event_generate("<Down>")
        )
        self.theme_combo.pack(anchor="w")

        currency_frame = ttk.Frame(right_frame)
        currency_frame.pack(side=LEFT, padx=(0, 10))
        self.currency_label = ttk.Label(
            currency_frame, text=f"{translate('Currency')}:", font="-size 10"
        )
        self.currency_label.pack(anchor="w")

        self.currency_combo = ttk.Combobox(
            currency_frame, values=[], state="readonly", width=8
        )
        self.currency_combo.set(self.currency_var.get())
        self.currency_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: currency_callback(self.currency_combo.get()),
        )
        self.currency_combo.bind(
            "<Button-1>", lambda e: self.currency_combo.event_generate("<Down>")
        )
        self.currency_combo.pack(anchor="w")
        self._setup_currency_dropdown()

    def _setup_currency_dropdown(self):
        all_currencies = [c.upper() for c in CONFIG["display"]["supported_currencies"]]
        displayed_codes_lower = CONFIG["display"]["displayed_currencies"]
        displayed_currencies = [
            c.upper() for c in all_currencies if c.lower() in displayed_codes_lower
        ]

        self.currency_combo["values"] = displayed_currencies
        current_selection = self.currency_var.get().upper()
        if current_selection not in displayed_currencies:
            new_selection = displayed_currencies[0] if displayed_currencies else "USD"
            self.currency_var.set(new_selection)
            self.main_window._apply_currency_change(new_selection)
        self.currency_combo.set(self.currency_var.get())

    def _setup_language_dropdown(self):
        all_langs = get_available_languages()
        displayed_lang_codes = CONFIG["display"]["displayed_languages"]
        display_langs = [
            lang for lang in all_langs if lang["code"] in displayed_lang_codes
        ]

        self.lang_display_map = {
            f"{translate(lang['name'])} ({lang['code']})": lang["code"]
            for lang in display_langs
        }
        self.lang_code_map = {
            lang["code"]: f"{translate(lang['name'])} ({lang['code']})"
            for lang in display_langs
        }

        if not hasattr(self, "lang_combo"):
            self.lang_combo = ttk.Combobox(
                self.lang_frame,
                values=list(self.lang_display_map.keys()),
                state="readonly",
                width=20,
            )
            self.lang_combo.bind(
                "<<ComboboxSelected>>",
                lambda e: self.lang_callback(
                    self.lang_display_map.get(self.lang_combo.get())
                ),
            )
            self.lang_combo.bind(
                "<Button-1>", lambda e: self.lang_combo.event_generate("<Down>")
            )
            self.lang_combo.pack(anchor="w")
        else:
            self.lang_combo["values"] = list(self.lang_display_map.keys())

        current_lang_code = self.config_manager.get_config().get("language")
        display_val = self.lang_code_map.get(current_lang_code)
        if not display_val:
            display_val = (
                list(self.lang_display_map.keys())[0]
                if self.lang_display_map
                else "English (en)"
            )
        self.lang_combo.set(display_val)

    def _create_stat_frame(self, parent, title_key, value_var, bootstyle):
        frame = ttk.Frame(parent)
        frame.pack(side=LEFT, padx=10, anchor="s")
        label_frame = ttk.Frame(frame)
        label_frame.pack(fill=X, anchor="n")
        label = ttk.Label(label_frame, text=translate(title_key), font="-size 10")
        label.pack(side=LEFT)
        ttk.Label(
            frame,
            textvariable=value_var,
            font="-size 12 -weight bold",
            bootstyle=bootstyle,
        ).pack(fill=X, anchor="s")
        return label, frame

    def set_controls_state(self, is_active: bool):
        state = "readonly" if is_active else DISABLED
        try:
            if hasattr(self, "lang_combo"):
                self.lang_combo.config(state=state)
            if hasattr(self, "theme_combo"):
                self.theme_combo.config(state=state)
            if hasattr(self, "currency_combo"):
                self.currency_combo.config(state=state)
        except Exception as e:
            logger.error(f"Failed to set header control state: {e}")

    def update_price_tooltip(self, timestamp: int):
        if timestamp > 0:
            dt_object = datetime.fromtimestamp(timestamp)
            formatted_time = dt_object.strftime("%Y-%m-%d %H:%M:%S")
            self.price_tooltip.text = (
                f"{translate('Last Price Update: {}').format(formatted_time)}"
            )
        else:
            self.price_tooltip.text = "N/A"

    def update_network_tooltip(self, timestamp: int):
        if timestamp > 0:
            dt_object = datetime.fromtimestamp(timestamp)
            formatted_time = dt_object.strftime("%Y-%m-%d %H:%M:%S")
            tooltip_text = (
                f"{translate('Last Network Update: {}').format(formatted_time)}"
            )
            self.hashrate_tooltip.text = tooltip_text
            self.difficulty_tooltip.text = tooltip_text
        else:
            self.hashrate_tooltip.text = "N/A"
            self.difficulty_tooltip.text = "N/A"

    def re_translate(self):
        self.title_label.config(text=translate("KaspaGateway"))
        self.version_label.config(text=f"{translate('Version')} {CONFIG['version']}")
        self.price_label.config(text=translate("Price"))
        self.hashrate_label.config(text=translate("Hashrate"))
        self.difficulty_label.config(text=translate("Difficulty"))
        self.lang_label.config(text=f"{translate('Language')}:")
        self.theme_label.config(text=f"{translate('Theme')}:")
        self.currency_label.config(text=f"{translate('Currency')}:")
        self.donation_link.config(text=translate("Donations"))

        self._setup_language_dropdown()
        self._setup_currency_dropdown()

        if hasattr(self.main_window, "price_updater"):
            self.update_price_tooltip(
                self.main_window.price_updater.get_last_updated_ts()
            )
        if hasattr(self.main_window, "network_updater"):
            self.update_network_tooltip(
                self.main_window.network_updater.get_last_updated_ts()
            )
