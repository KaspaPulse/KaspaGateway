from __future__ import annotations

import calendar as py_calendar
import logging
import os
import queue
import threading
import tkinter as tk
import webbrowser
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.toast import ToastNotification

from src.config.config import CONFIG
from src.export import export_df_to_csv, export_df_to_html, export_df_to_pdf
from src.gui.components import ExportComponent, Results
from src.gui.input import Input
from src.utils.i18n import get_all_translations_for_key, translate
from src.utils.profiling import log_performance

if TYPE_CHECKING:
    from src.gui.address_manager import AddressManager
    from src.gui.config_manager import ConfigManager
    from src.gui.main_window import MainWindow
    from src.gui.transaction_manager import TransactionManager

logger = logging.getLogger(__name__)

KASPA_MINDATE = date(2021, 11, 7)



class ManualCalendarPopup(ttk.Toplevel):
    """
    A custom Toplevel window that displays a calendar for date selection,
    including quick-select presets.
    """

    def __init__(
        self,
        parent: ttk.Frame,
        target_label: ttk.Label,
        start_date: Optional[date] = None,
    ):
        super().__init__(parent)
        self.title(translate("Select Date"))
        self.filter_controls = parent
        self.target_label = target_label

        if start_date is None or not (KASPA_MINDATE <= start_date <= TODAY):
            start_date = TODAY

        self.year: int = start_date.year
        self.month: int = start_date.month

        self.transient(parent.winfo_toplevel())
        self.after(20, self._center_window)

        self.header_frame = ttk.Frame(self)
        self.header_frame.pack(pady=5, fill=X, padx=5)

        self.prev_month_button = ttk.Button(
            self.header_frame, text="<", command=self.prev_month, bootstyle="secondary"
        )
        self.prev_month_button.pack(side=LEFT, padx=5)
        self.month_year_label = ttk.Label(self.header_frame, font="-weight bold")
        self.month_year_label.pack(side=LEFT, expand=True, fill=X)

        self.next_month_button = ttk.Button(
            self.header_frame, text=">", command=self.next_month, bootstyle="secondary"
        )
        self.next_month_button.pack(side=RIGHT, padx=5)
        self.days_frame = ttk.Frame(self)
        self.days_frame.pack(pady=5, padx=5)
        self.day_buttons = []
        self._create_day_widgets()

        ttk.Separator(self, orient=HORIZONTAL).pack(fill=X, padx=10, pady=5)

        presets_frame = ttk.Frame(self)
        presets_frame.pack(pady=5, padx=5, fill=X)
        self._create_preset_buttons(presets_frame)

        self.draw_calendar()

    def _center_window(self) -> None:
        try:
            self.update_idletasks()
            tl = self.master.winfo_toplevel()
            if tl.winfo_viewable() == 0:
                return

            toplevel.update_idletasks()
            main_x = toplevel.winfo_x()
            main_y = toplevel.winfo_y()
            main_width = toplevel.winfo_width()
            main_height = toplevel.winfo_height()
            s_width = self.winfo_reqwidth()
            s_height = self.winfo_reqheight()
            x = main_x + (main_width // 2) - (s_width // 2)
            y = main_y + (main_height // 2) - (s_height // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass  # Failsafe if window is destroyed

    def _create_day_widgets(self) -> None:
        """Creates the grid of day labels and buttons."""
        days = py_calendar.weekheader(2).split()
        for i, day in enumerate(days):
            ttk.Label(self.days_frame, text=day, anchor=CENTER).grid(
                row=0, column=i, sticky="nsew"
            )

    def _create_day_widgets(self) -> None:
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i, day in enumerate(days):
            ttk.Label(self.days_frame, text=day, anchor=CENTER).grid(
                row=0, column=i, sticky="nsew"
            )
        for r in range(6):
            row_buttons = []
            for c in range(7):
                btn = ttk.Button(self.days_frame, text="", width=4, bootstyle="light")
                btn.grid(row=r + 1, column=c, padx=1, pady=1)
                row_buttons.append(btn)
            self.day_buttons.append(row_buttons)

    def _create_preset_buttons(self, parent: ttk.Frame) -> None:
        """Creates the quick-select preset buttons."""
        presets_top = [("Last 3 Days", 3), ("Last Week", 7), ("Last Month", 30)]
        presets_bottom = [
            ("Last 3 Months", 90),
            ("Last 6 Months", 182),
            ("Last Year", 365),
        ]

        top_frame = ttk.Frame(parent)
        top_frame.pack(fill=X)
        bottom_frame = ttk.Frame(parent)
        bottom_frame.pack(fill=X, pady=(5, 0))

        for text_key, num_days in presets_top:
            cmd = lambda d=num_days: self._set_date_range_and_close(days=d)
            btn = ttk.Button(
                top_frame,
                text=translate(text_key),
                command=cmd,
                bootstyle="outline-secondary",
            )
            btn.pack(side=LEFT, padx=(0, 5), fill=X, expand=True)

        for text_key, num_days in presets_bottom:
            cmd = lambda d=num_days: self._set_date_range_and_close(days=d)
            btn = ttk.Button(
                bottom_frame,
                text=translate(text_key),
                command=cmd,
                bootstyle="outline-secondary",
            )
            btn.pack(side=LEFT, padx=(0, 5), fill=X, expand=True)

    def _set_date_range_and_close(self, days: int) -> None:
        """Sets the date range in the parent FilterControls and closes."""
        start_date = TODAY - timedelta(days=days - 1)
        if start_date < KASPA_MINDATE:
            start_date = KASPA_MINDATE
        self.filter_controls.start_date_label.config(
            text=start_date.strftime("%Y-%m-%d")
        )
        self.filter_controls.end_date_label.config(text=TODAY.strftime("%Y-%m-%d"))
        self.destroy()

    def _update_nav_buttons_state(self) -> None:
        """Disables month navigation buttons if out of valid range."""
        prev_month = self.month - 1 if self.month > 1 else 12
        prev_year = self.year if self.month > 1 else self.year - 1
        if prev_year < KASPA_MINDATE.year or (
            prev_year == KASPA_MINDATE.year and prev_month < KASPA_MINDATE.month
        ):
            self.prev_month_button.config(state=DISABLED)
        else:
            self.prev_month_button.config(state=NORMAL)

        next_month = self.month + 1 if self.month < 12 else 1
        next_year = self.year if self.month < 12 else self.year + 1
        if next_year > TODAY.year or (
            next_year == TODAY.year and next_month > TODAY.month
        ):
            self.next_month_button.config(state=DISABLED)
        else:
            self.next_month_button.config(state=NORMAL)

    def draw_calendar(self) -> None:
        self.month_year_label.config(text=f"{self.month_names[self.month]} {self.year}")
        cal = py_calendar.monthcalendar(self.year, self.month)
        for r, week in enumerate(cal):
            for c, day in enumerate(week):
                btn = self.day_buttons[r][c]
                if day == 0:
                    btn.config(text="", state=DISABLED, command=None)
                else:
                    d = date(self.year, self.month, day)
                    cmd = lambda d=day: self.on_day_click(d)
                    if not (KASPA_MINDATE <= d <= date.today()):
                        btn.config(text=str(day), state=DISABLED, command=None)
                    else:
                        btn.config(text=str(day), state=NORMAL, command=cmd)

        for r in range(len(cal), 6):
            for c in range(7):
                self.day_buttons[r][c].config(text="", state=DISABLED, command=None)

    def on_day_click(self, day: int) -> None:
        self.selected_date = date(self.year, self.month, day)
        self.on_select()

    def prev_month(self) -> None:
        self.month -= 1
        if self.month == 0:
            self.month = 12
            self.year -= 1
        self.draw_calendar()

    def next_month(self) -> None:
        self.month += 1
        if self.month == 13:
            self.month = 1
            self.year += 1
        self.draw_calendar()

    def on_select(self) -> None:
        """Sets the target label's text and closes the window."""
        if self.selected_date:
            self.target_label.config(text=self.selected_date.strftime("%Y-%m-%d"))
        self.destroy()


class _ExplorerFilterControls(ttk.Labelframe):
    """
    A private FilterControls widget dedicated to the Explorer Tab.
    """

    def __init__(
        self,
        parent: ttk.Frame,
        filter_callback: Callable[[], None],
        reset_callback: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent, text=" " + translate("Filter") + " ", padding=10)
        self.filter_callback = filter_callback
        self.reset_callback = reset_callback
        self.placeholder_active: bool = False

        self.start_date_label: ttk.Label
        self.end_date_label: ttk.Label
        self.type_combo: ttk.Combobox
        self.direction_combo: ttk.Combobox
        self.search_entry: ttk.Entry
        self.start_date_button: ttk.Button
        self.end_date_button: ttk.Button
        self.filter_button: ttk.Button
        self.reset_button: ttk.Button

        self._build_ui()
        self._setup_placeholder()
        self._bind_events()
        self.set_input_state(True)
        self.set_action_buttons_state(True)

    def _build_ui(self) -> None:
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=X, expand=True, pady=(0, 5))
        
        self.from_date_label = ttk.Label(top_frame, text=translate("From Date:"))
        self.from_date_label.pack(side=LEFT, padx=(0, 5), pady=5)

        start_date_frame = ttk.Frame(top_frame)
        start_date_frame.pack(side=LEFT, padx=(0, 10), pady=5)
        self.start_date_label = ttk.Label(
            start_date_frame,
            text=KASPA_MINDATE.strftime("%Y-%m-%d"),
            width=12,
            anchor=CENTER,
            relief="solid",
            borderwidth=1,
        )
        self.start_date_label.pack(side=LEFT)
        self.start_date_button = ttk.Button(
            start_date_frame,
            text="📅",
            command=lambda: self._open_calendar(self.start_date_label),
            bootstyle="outline",
            width=2,
        )
        self.start_date_button.pack(side=LEFT)

        self.to_date_label = ttk.Label(top_frame, text=translate("To Date:"))
        self.to_date_label.pack(side=LEFT, padx=(0, 5), pady=5)

        end_date_frame = ttk.Frame(top_frame)
        end_date_frame.pack(side=LEFT, padx=(0, 10), pady=5)
        self.end_date_label = ttk.Label(
            end_date_frame,
            text=TODAY.strftime("%Y-%m-%d"),
            width=12,
            anchor=CENTER,
            relief="solid",
            borderwidth=1,
        )
        self.end_date_label.pack(side=LEFT)
        self.end_date_button = ttk.Button(
            end_date_frame,
            text="📅",
            command=lambda: self._open_calendar(self.end_date_label),
            bootstyle="outline",
            width=2,
        )
        self.end_date_button.pack(side=LEFT)

        self.type_label = ttk.Label(top_frame, text=translate("Type:"))
        self.type_label.pack(side=LEFT, padx=(0, 5), pady=5)
        self.type_combo = ttk.Combobox(
            top_frame,
            values=[translate("ALL"), translate("coinbase"), translate("transfer")],
            state="readonly",
            width=10,
        )
        self.type_combo.set(translate("ALL"))
        self.type_combo.pack(side=LEFT, padx=(0, 10), pady=5)

        self.direction_label = ttk.Label(top_frame, text=translate("Direction"))
        self.direction_label.pack(side=LEFT, padx=(0, 5), pady=5)
        self.direction_combo = ttk.Combobox(
            top_frame,
            values=[translate("ALL"), translate("incoming"), translate("outgoing")],
            state="readonly",
            width=10,
        )
        self.direction_combo.set(translate("ALL"))
        self.direction_combo.pack(side=LEFT, padx=(0, 10), pady=5)

        # Pack buttons to the RIGHT first, so they anchor to the right side
        self.reset_button = ttk.Button(
            top_frame,
            text=translate("Reset Filter"),
            command=self._reset_filters_ui_and_callback,
            bootstyle="secondary",
        )
        self.reset_button.pack(side=RIGHT, padx=(5, 0), pady=5)

        self.filter_button = ttk.Button(
            top_frame,
            text=translate("Filter"),
            command=self.filter_callback,
            bootstyle="primary",
        )
        self.filter_button.pack(side=RIGHT, padx=(0, 5), pady=5)
        
        self.search_entry = ttk.Entry(top_frame)
        self.search_entry.pack(side=RIGHT, fill=X, expand=True, pady=5)

    def _open_calendar(self, target_label: ttk.Label) -> None:
        if self.start_date_button.cget("state") == DISABLED:
            return
        try:
            current_date_str = target_label.cget("text")
            start_date = datetime.strptime(current_date_str, "%Y-%m-%d").date()
        except ValueError:
            start_date = date.today()

        ManualCalendarPopup(self, target_label, start_date)

    def _reset_filters_ui_and_callback(self) -> None:
        self.start_date_label.config(text=KASPA_MINDATE.strftime("%Y-%m-%d"))
        self.end_date_label.config(text=date.today().strftime("%Y-%m-%d"))
        self.type_combo.set(translate("ALL"))
        self.direction_combo.set(translate("ALL"))
        self.search_entry.delete(0, "end")
        self._on_focus_out(None)
        if self.reset_callback:
            self.reset_callback()
        else:
            self.filter_callback()

    def _setup_placeholder(self) -> None:
        self.placeholder = translate("Search by Address/Transaction...")
        self.placeholder_color = "grey"
        self.default_fg_color = self.search_entry.cget("foreground")
        self.search_entry.insert(0, self.placeholder)
        self.search_entry.config(foreground=self.placeholder_color)
        self.placeholder_active = True

    def _bind_events(self) -> None:
        self.search_entry.bind("<FocusIn>", self._on_focus_in)
        self.search_entry.bind("<FocusOut>", self._on_focus_out)

    def _on_focus_in(self, event: Optional[tk.Event]) -> None:
        if self.placeholder_active:
            self.search_entry.delete(0, "end")
            self.search_entry.config(
                foreground=self.master.style.lookup("TEntry", "foreground")
            )
            self.placeholder_active = False

    def _on_focus_out(self, event: Optional[tk.Event]) -> None:
        if not self.search_entry.get():
            self._setup_placeholder()

    def get_filters(self) -> Dict[str, Any]:
        start_date_str = self.start_date_label.cget("text")
        end_date_str = self.end_date_label.cget("text")

        start_date_obj = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date_obj = datetime.strptime(end_date_str, "%Y-%m-%d").date()

        start_dt = datetime.combine(start_date_obj, datetime.min.time())
        end_dt = datetime.combine(end_date_obj, datetime.max.time())

        search_text = self.search_entry.get().strip()
        search_query = search_text if not self.placeholder_active else None

        return {
            "start_date": datetime.strptime(s, "%Y-%m-%d"),
            "end_date": datetime.combine(
                datetime.strptime(e, "%Y-%m-%d").date(), datetime.max.time()
            ),
            "type_filter": self.type_combo.get(),
            "direction_filter": self.direction_combo.get(),
            "search_query": search_query,
        }

    def set_input_state(self, is_active: bool) -> None:
        state = NORMAL if is_active else DISABLED
        for widget in [
            self.type_combo,
            self.direction_combo,
            self.search_entry,
            self.start_date_button,
            self.end_date_button,
        ]:
            try:
                w.configure(state=s)
            except Exception:
                pass

        if not is_active:
            self._on_focus_out(None)

    def set_action_buttons_state(self, is_active: bool) -> None:
        state = NORMAL if is_active else DISABLED
        for widget in [self.filter_button, self.reset_button]:
            widget.configure(state=state)

    def re_translate(self) -> None:
        self.config(text=f" {translate('Filter')} ")
        self.from_date_label.config(text=translate("From Date:"))
        self.to_date_label.config(text=translate("To Date:"))
        self.filter_button.config(text=translate("Filter"))
        self.reset_button.config(text=translate("Reset Filter"))

        self.type_combo["values"] = [
            translate("ALL"),
            translate("coinbase"),
            translate("transfer"),
        ]
        self.direction_combo["values"] = [
            translate("ALL"),
            translate("incoming"),
            translate("outgoing"),
        ]

        current_state = self.search_entry.cget("state")
        self.search_entry.config(state=NORMAL)
        if self.placeholder_active:
            self.search_entry.delete(0, "end")
            self._setup_placeholder()
        self.search_entry.config(state=current_state)


# --- End of embedded FilterControls component ---


class ExplorerTab(ttk.Frame):
    """
    The Explorer Tab allows users to load an address, fetch transactions,
    filter them, and export the results.
    """

    main_window: "MainWindow"
    config_manager: "ConfigManager"
    transaction_manager: "TransactionManager"
    address_manager: "AddressManager"
    input_component: Input
    explorer_filter_controls: _ExplorerFilterControls
    results_component: Results
    export_component: ExportComponent
    font_size_label: ttk.Label
    font_size_var: ttk.IntVar
    font_size_spinbox: ttk.Spinbox

    def __init__(self, parent: ttk.Frame, main_window: "MainWindow") -> None:
        super().__init__(parent)
        self.main_window: "MainWindow" = main_window
        self.config_manager = main_window.config_manager
        self.transaction_manager = main_window.transaction_manager
        self.address_manager = main_window.address_manager
        self.tx_db = main_window.tx_db

        # UI Components
        self.input_component: Optional[Input] = None
        self.explorer_filter_controls: Optional[_ExplorerFilterControls] = None
        self.results_component: Optional[Results] = None
        self.export_component: Optional[ExportComponent] = None
        self.font_size_label: Optional[ttk.Label] = None
        self.font_size_spinbox: Optional[ttk.Spinbox] = None
        self.font_size_var = ttk.IntVar(value=CONFIG.get("table_font_size", 9))

        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.input_component = Input(
            self, self.main_window, self.transaction_manager, self.address_manager
        )
        self.input_component.pack(fill=X, padx=5, pady=5)

        self.explorer_filter_controls = _ExplorerFilterControls(
            self, self.apply_explorer_filters, self.reset_explorer_filters_display
        )
        self.explorer_filter_controls.pack(fill=X, padx=5, pady=5)

        self.results_component = Results(
            self, self.main_window.cancel_event, self.main_window.currency_var.get()
        )
        self.results_component.pack(fill=BOTH, expand=True, padx=5, pady=5)

        # Bottom frame for Export AND Font Control
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=X, padx=5, pady=5)
        bottom_frame.grid_columnconfigure(1, weight=1)  # Spacer

        self.export_component = ExportComponent(bottom_frame, self.export_data)
        self.export_component.grid(row=0, column=0, sticky="w")

        # Font size controls
        font_size_frame = ttk.Frame(bottom_frame)
        font_size_frame.grid(row=0, column=2, sticky="e")
        self.font_size_label = ttk.Label(
            font_size_frame, text=f"{translate('Transaction Table Font Size')}:"
        )
        self.font_size_label.pack(side=LEFT, padx=(0, 5))

        self.font_size_spinbox = ttk.Spinbox(
            font_size_frame,
            from_=6,
            to=20,
            width=5,
            textvariable=self.font_size_var,
            command=self._on_font_size_change,
        )
        self.font_size_spinbox.pack(side=LEFT)

        # Init font size
        self.results_component.update_font_size(self.font_size_var.get())

    def set_controls_state(self, active: bool) -> None:
        if not self.winfo_exists():
            return
        is_valid_address = self.main_window.current_address is not None
        home_has_data = self.results_component.has_data()

        self.input_component.set_ui_state(not active)
        self.explorer_filter_controls.set_input_state(active and is_valid_address)
        self.explorer_filter_controls.set_action_buttons_state(
            active and is_valid_address
        )

        can_filter = active and is_valid_address
        self.explorer_filter_controls.set_input_state(can_filter)
        self.explorer_filter_controls.set_action_buttons_state(can_filter)
        self.export_component.set_ui_state(active and home_has_data)

        try:
            self.font_size_spinbox.config(state=NORMAL if active else DISABLED)
        except tk.TclError:
            pass

    def re_translate(self) -> None:
        self.input_component.re_translate()
        self.explorer_filter_controls.re_translate()
        self.results_component.re_translate()
        self.export_component.re_translate()
        self.font_size_label.config(text=f"{translate('Transaction Table Font Size')}:")

    def apply_explorer_filters(self) -> None:
        if self.transaction_manager.is_fetching:
            ToastNotification(
                title=translate("Fetch Active"),
                message=translate("Please wait for the current fetch to complete."),
                bootstyle=INFO,
                duration=3000,
            ).show_toast()
            return

        if not self.main_window.current_address:
            self.results_component.show_placeholder(
                translate("Load an address to see transactions.")
            )
            return

        self.main_window.status.update_status(translate("Applying filters..."))
        self.main_window._set_ui_for_processing(True)
        filters = self.explorer_filter_controls.get_filters()
        addr = self.main_window.current_address

        def worker() -> None:
            try:
                filtered_data_list: List[Dict[str, Any]] = (
                    self.main_window.tx_db.filter_transactions(
                        address=address, **filters
                    )
                )
                filtered_df = pd.DataFrame(filtered_data_list)

                if self.winfo_exists():
                    self.main_window.after(
                        0, self._display_callback, pd.DataFrame(data)
                    )
            except Exception as e:
                logger.error(f"Filter error: {e}")
                self.main_window.after(
                    0, self.main_window._set_ui_for_processing, False
                )

        threading.Thread(target=worker, daemon=True).start()

    def _display_callback(self, df: pd.DataFrame) -> None:
        self.results_component.display_data(df, self.main_window.currency_var.get())
        self.main_window.status.update_status("Ready")
        self.main_window._set_ui_for_processing(False)

    def export_data(self, export_format: str) -> None:
        """Initiates an export for the Explorer tab's data."""
        df_to_export: pd.DataFrame = (
            self.results_component.get_current_view_data_as_df()
        )

        if df.empty:
            ToastNotification(
                title=translate("Export Results:"),
                message=translate("No data to export."),
                bootstyle=WARNING,
                duration=3000,
            ).show_toast()
            return

        addr_short: str = (
            self.main_window.current_address.split(":")[-1][:8]
            if self.main_window.current_address
            else "export"
        )
        ts: str = datetime.now().strftime("%Y%m%d_%H%M%S")
        initial_filename: str = f"kaspa_tx_{addr_short}_{ts}.{export_format}"
        export_dir: str = CONFIG.get("paths", {}).get("export", ".")
        os.makedirs(export_dir, exist_ok=True)

        file_path = filedialog.asksaveasfilename(
            initialfile=initial_filename,
            defaultextension=f".{export_format}",
            filetypes=[(f"{export_format.upper()} files", f"*.{export_format}")],
            title=f"{translate('Save as')} {export_format.upper()}",
            initialdir=export_dir,
        )

        if not file_path:
            # Unlock UI if cancelled
            self.main_window.set_busy_state(False)
            return

        self.main_window.status.update_status(
            f"Exporting to {export_format.upper()}..."
        )
        self.main_window._set_ui_for_processing(True)
        self.main_window.is_exporting = True
        address_name: str = (
            self.main_window.address_names_map.get(self.main_window.current_address, "")
            if self.main_window.current_address
            else ""
        )

        export_args = {
            "df": df,
            "file_path": file_path,
            "kaspa_address": self.main_window.current_address,
            "address_name": self.main_window.address_names_map.get(
                self.main_window.current_address, ""
            ),
            "currency": self.main_window.currency_var.get(),
            "known_names_map": self.main_window.address_names_map,
        }

        threading.Thread(
            target=self._export_explorer_tab_worker,
            args=(export_format, export_args),
            daemon=True,
        ).start()

    @log_performance
    def _export_explorer_tab_worker(
        self, export_format: str, export_args: Dict[str, Any]
    ) -> None:
        """Background thread to handle the file I/O for exporting."""
        addr: Optional[str] = self.main_window.current_address
        f_path: str = export_args["file_path"]
        logger.info(
            f"Exporting {len(export_args['df'])} records for address '{addr}' to {export_format.upper()} at {f_path}"
        )

    def _export_worker(self, export_format: str, export_args: Dict[str, Any]) -> None:
        """Background thread to perform the data export."""
        try:
            export_map: Dict[str, Callable[..., Tuple[bool, str, str]]] = {
                "csv": export_df_to_csv,
                "html": export_df_to_html,
                "pdf": export_df_to_pdf,
            }
            export_func: Optional[Callable[..., Tuple[bool, str, str]]] = (
                export_map.get(export_format)
            )

            if not export_func:
                raise ValueError(
                    f"No export function found for format: {export_format}"
                )

            success, msg_key, details = export_func(**export_args)

            final_msg: str = (
                f"{translate(msg_key)}: {details}" if details else translate(msg_key)
            )

            if self.winfo_exists():
                if success:
                    logger.info(f"Export successful. File saved to {f_path}")
                    self.main_window.after(
                        100, self.main_window.prompt_to_open_file, f_path, final_msg
                    )
                else:
                    self.main_window.after(
                        0, lambda: messagebox.showerror(translate("Error"), final_msg)
                    )

        except Exception as e:
            logger.error(f"Export worker failed: {e}", exc_info=True)
            if self.winfo_exists():
                self.main_window.after(
                    0,
                    lambda: ToastNotification(
                        title=translate("Error"),
                        message=translate("Check logs for details."),
                        bootstyle=DANGER,
                        duration=3000,
                    ).show_toast(),
                )
        finally:
            # UNLOCK UI regardless of success or failure
            if self.winfo_exists():
                self.main_window.after(
                    0, self.main_window.status.update_status, "Ready"
                )
                self.main_window.after(
                    0, self.main_window._set_ui_for_processing, False
                )

    def _on_font_size_change(self) -> None:
        new_size = self.font_size_var.get()
        self.results_component.update_font_size(new_size)
        config = self.config_manager.get_config()
        config["table_font_size"] = new_size
        self.config_manager.save_config(config)

    def set_new_transaction_dataset(self, all_txs_df: pd.DataFrame) -> None:
        """Proxy to set a new dataframe in the Results component."""
        self.results_component.display_data(
            all_txs_df, self.main_window.currency_var.get()
        )

    def set_new_transaction_dataset(self, df: pd.DataFrame) -> None:
        self.results_component.display_data(df, self.main_window.currency_var.get())

    def append_transaction_data(self, df: pd.DataFrame) -> None:
        self.results_component.append_transactions(df)