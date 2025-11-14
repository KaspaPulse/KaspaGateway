from __future__ import annotations

import logging
import threading
import os
import json
import base64
import queue
import time
import tkinter as tk
import webbrowser
import calendar as py_calendar
from tkinter import filedialog, messagebox
from typing import (
    TYPE_CHECKING, Dict, Any, Optional, Set, List, Callable, Tuple, cast, Iterator
)
from collections import defaultdict
from datetime import datetime, date, timedelta

import duckdb
import pandas as pd
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledText
from ttkbootstrap.toast import ToastNotification

from src.config.config import CONFIG, get_active_api_config
from src.export import (
    export_analysis_to_html, export_analysis_to_pdf, export_analysis_to_csv
)
from src.gui.components.export import ExportComponent
from src.utils.i18n import translate, get_all_translations_for_key
from src.utils.profiling import log_performance

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.gui.main_window import MainWindow

# --- FilterControls component is now embedded inside this file ---

KASPA_MINDATE = date(2021, 11, 7)
TODAY = date.today()

class ManualCalendarPopup(ttk.Toplevel):
    """
    A custom Toplevel window that displays a calendar for date selection,
    including quick-select presets.
    """
    def __init__(self, parent: ttk.Frame, target_label: ttk.Label, start_date: Optional[date] = None):
        super().__init__(parent)
        self.title(translate("Select Date"))
        self.filter_controls: _AnalysisFilterControls = parent  # type: ignore
        self.target_label = target_label
        self.selected_date: Optional[date] = None

        if start_date is None or not (KASPA_MINDATE <= start_date <= TODAY):
            start_date = TODAY
        
        self.year: int = start_date.year
        self.month: int = start_date.month

        self.transient(parent.winfo_toplevel())
        self.after(20, self._center_window)
        
        self.header_frame = ttk.Frame(self)
        self.header_frame.pack(pady=5, fill=X, padx=5)

        self.prev_month_button = ttk.Button(self.header_frame, text="<", command=self.prev_month, bootstyle="secondary")
        self.prev_month_button.pack(side=LEFT, padx=5)

        self.month_year_label = ttk.Label(self.header_frame, font="-weight bold")
        self.month_year_label.pack(side=LEFT, expand=True, fill=X)

        self.next_month_button = ttk.Button(self.header_frame, text=">", command=self.next_month, bootstyle="secondary")
        self.next_month_button.pack(side=RIGHT, padx=5)

        self.days_frame = ttk.Frame(self)
        self.days_frame.pack(pady=5, padx=5)

        self.day_buttons: List[List[ttk.Button]] = []
        self._create_day_widgets()
        
        ttk.Separator(self, orient=HORIZONTAL).pack(fill=X, padx=10, pady=5)
        
        presets_frame = ttk.Frame(self)
        presets_frame.pack(pady=5, padx=5, fill=X)
        self._create_preset_buttons(presets_frame)
        
        self.draw_calendar()
        self.grab_set()
        self.wait_window()

    def _center_window(self) -> None:
        """Centers the popup window relative to its parent."""
        try:
            self.update_idletasks()
            toplevel = self.master.winfo_toplevel()
            if toplevel.winfo_viewable() == 0:
                self.after(20, self._center_window)
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
            ttk.Label(self.days_frame, text=day, anchor=CENTER).grid(row=0, column=i, sticky="nsew")

        for r in range(6):
            row_buttons: List[ttk.Button] = []
            for c in range(7):
                btn = ttk.Button(self.days_frame, text="", width=4, bootstyle="light")
                btn.grid(row=r + 1, column=c, padx=1, pady=1)
                row_buttons.append(btn)
            self.day_buttons.append(row_buttons)

    def _create_preset_buttons(self, parent: ttk.Frame) -> None:
        """Creates the quick-select preset buttons."""
        presets_top = [("Last 3 Days", 3), ("Last Week", 7), ("Last Month", 30)]
        presets_bottom = [("Last 3 Months", 90), ("Last 6 Months", 182), ("Last Year", 365)]
        
        top_frame = ttk.Frame(parent)
        top_frame.pack(fill=X)
        bottom_frame = ttk.Frame(parent)
        bottom_frame.pack(fill=X, pady=(5,0))

        for text_key, num_days in presets_top:
            cmd = lambda d=num_days: self._set_date_range_and_close(days=d)
            btn = ttk.Button(top_frame, text=translate(text_key), command=cmd, bootstyle="outline-secondary")
            btn.pack(side=LEFT, padx=(0, 5), fill=X, expand=True)

        for text_key, num_days in presets_bottom:
            cmd = lambda d=num_days: self._set_date_range_and_close(days=d)
            btn = ttk.Button(bottom_frame, text=translate(text_key), command=cmd, bootstyle="outline-secondary")
            btn.pack(side=LEFT, padx=(0, 5), fill=X, expand=True)

    def _set_date_range_and_close(self, days: int) -> None:
        """Sets the date range in the parent FilterControls and closes."""
        start_date = TODAY - timedelta(days=days-1)
        if start_date < KASPA_MINDATE:
            start_date = KASPA_MINDATE
        self.filter_controls.start_date_label.config(text=start_date.strftime("%Y-%m-%d"))
        self.filter_controls.end_date_label.config(text=TODAY.strftime("%Y-%m-%d"))
        self.destroy()

    def _update_nav_buttons_state(self) -> None:
        """Disables month navigation buttons if out of valid range."""
        prev_month = self.month - 1 if self.month > 1 else 12
        prev_year = self.year if self.month > 1 else self.year - 1
        if prev_year < KASPA_MINDATE.year or (prev_year == KASPA_MINDATE.year and prev_month < KASPA_MINDATE.month):
            self.prev_month_button.config(state=DISABLED)
        else:
            self.prev_month_button.config(state=NORMAL)
            
        next_month = self.month + 1 if self.month < 12 else 1
        next_year = self.year if self.month < 12 else self.year + 1
        if next_year > TODAY.year or (next_year == TODAY.year and next_month > TODAY.month):
            self.next_month_button.config(state=DISABLED)
        else:
            self.next_month_button.config(state=NORMAL)

    def draw_calendar(self) -> None:
        """Draws the calendar buttons for the current month and year."""
        self._update_nav_buttons_state()
        month_name = py_calendar.month_name[self.month]
        self.month_year_label.config(text=f"{translate(month_name)} {self.year}")

        cal = py_calendar.monthcalendar(self.year, self.month)
        for r, week in enumerate(cal):
            for c, day in enumerate(week):
                btn = self.day_buttons[r][c]
                if day == 0:
                    btn.config(text="", state=DISABLED, command=None)
                else:
                    current_day = date(self.year, self.month, day)
                    cmd = lambda d=day: self.on_day_click(d)
                    if not (KASPA_MINDATE <= current_day <= TODAY):
                        btn.config(text=str(day), state=DISABLED, command=None)
                    else:
                        btn.config(text=str(day), state=NORMAL, command=cmd)
        
        for r in range(len(cal), 6):
            for c in range(7):
                self.day_buttons[r][c].config(text="", state=DISABLED, command=None)

    def on_day_click(self, day: int) -> None:
        """Handles a day button click."""
        self.selected_date = date(self.year, self.month, day)
        self.on_select()
    
    def prev_month(self) -> None:
        """Moves to the previous month."""
        self.month -= 1
        if self.month == 0:
            self.month = 12
            self.year -= 1
        self.draw_calendar()

    def next_month(self) -> None:
        """Moves to the next month."""
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

class _AnalysisFilterControls(ttk.Labelframe):
    """
    A private FilterControls widget dedicated to the NormalAnalysisTab.
    """
    def __init__(self, parent: ttk.Frame, filter_callback: Callable[[], None], reset_callback: Optional[Callable[[], None]] = None):
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
        """Builds the UI using a grid layout."""
        
        # Configure the grid columns
        self.grid_columnconfigure(2, weight=1) # Make search field expandable

        # --- Row 0 ---
        
        # From Date (Col 0)
        from_date_frame = ttk.Frame(self)
        from_date_frame.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="w")
        self.from_date_label = ttk.Label(from_date_frame, text=translate("From Date:"))
        self.from_date_label.pack(side=LEFT, padx=(0, 5))
        start_date_frame_inner = ttk.Frame(from_date_frame)
        start_date_frame_inner.pack(side=LEFT)
        self.start_date_label = ttk.Label(start_date_frame_inner, text=KASPA_MINDATE.strftime("%Y-%m-%d"), width=12, anchor=CENTER, relief="solid", borderwidth=1)
        self.start_date_label.pack(side=LEFT)
        self.start_date_button = ttk.Button(start_date_frame_inner, text="📅", command=lambda: self._open_calendar(self.start_date_label), bootstyle="outline", width=2)
        self.start_date_button.pack(side=LEFT)

        # Type (Col 1)
        type_frame = ttk.Frame(self)
        type_frame.grid(row=0, column=1, padx=(5, 5), pady=5, sticky="w")
        self.type_label = ttk.Label(type_frame, text=translate("Type:"))
        self.type_label.pack(side=LEFT, padx=(0, 5))
        self.type_combo = ttk.Combobox(type_frame, values=[translate("ALL"), translate("coinbase"), translate("transfer")], state="readonly", width=12)
        self.type_combo.set(translate("ALL"))
        self.type_combo.pack(side=LEFT)

        # Search (Col 2, spanning 3 columns)
        self.search_entry = ttk.Entry(self)
        self.search_entry.grid(row=0, column=2, columnspan=3, padx=(10, 5), pady=5, sticky="ew")

        # --- Row 1 ---

        # To Date (Col 0)
        to_date_frame = ttk.Frame(self)
        to_date_frame.grid(row=1, column=0, padx=(0, 5), pady=5, sticky="w")
        self.to_date_label = ttk.Label(to_date_frame, text=translate("To Date:"))
        self.to_date_label.pack(side=LEFT, padx=(0, 5))
        end_date_frame_inner = ttk.Frame(to_date_frame)
        end_date_frame_inner.pack(side=LEFT)
        self.end_date_label = ttk.Label(end_date_frame_inner, text=TODAY.strftime("%Y-%m-%d"), width=12, anchor=CENTER, relief="solid", borderwidth=1)
        self.end_date_label.pack(side=LEFT)
        self.end_date_button = ttk.Button(end_date_frame_inner, text="📅", command=lambda: self._open_calendar(self.end_date_label), bootstyle="outline", width=2)
        self.end_date_button.pack(side=LEFT)

        # Direction (Col 1)
        direction_frame = ttk.Frame(self)
        direction_frame.grid(row=1, column=1, padx=(5, 5), pady=5, sticky="w")
        self.direction_label = ttk.Label(direction_frame, text=translate("Direction"))
        self.direction_label.pack(side=LEFT, padx=(0, 5))
        self.direction_combo = ttk.Combobox(direction_frame, values=[translate("ALL"), translate("incoming"), translate("outgoing")], state="readonly", width=12)
        self.direction_combo.set(translate("ALL"))
        self.direction_combo.pack(side=LEFT)

        # Buttons Frame (Col 2, sticky WEST to be adjacent to Direction)
        buttons_frame = ttk.Frame(self)
        buttons_frame.grid(row=1, column=2, padx=(10, 0), pady=5, sticky="w")
        
        self.filter_button = ttk.Button(buttons_frame, text=translate("Filter"), command=self.filter_callback, bootstyle="primary")
        self.filter_button.pack(side=LEFT, padx=(0, 5))

        self.reset_button = ttk.Button(buttons_frame, text=translate("Reset Filter"), command=self._reset_filters_ui_and_callback, bootstyle="secondary")
        self.reset_button.pack(side=LEFT)

    def _open_calendar(self, target_label: ttk.Label) -> None:
        if self.start_date_button.cget('state') == DISABLED:
            return
        try:
            current_date_str = target_label.cget("text")
            start_date = datetime.strptime(current_date_str, "%Y-%m-%d").date()
        except ValueError:
            start_date = date.today()
        
        ManualCalendarPopup(self, target_label, start_date)

    def _reset_filters_ui_and_callback(self) -> None:
        self.start_date_label.config(text=KASPA_MINDATE.strftime("%Y-%m-%d"))
        self.end_date_label.config(text=TODAY.strftime("%Y-%m-%d"))
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
        self.placeholder_color = 'grey'
        self.default_fg_color = self.search_entry.cget("foreground")
        self.search_entry.insert(0, self.placeholder)
        self.search_entry.config(foreground=self.placeholder_color)
        self.placeholder_active = True

    def _bind_events(self) -> None:
        self.search_entry.bind('<FocusIn>', self._on_focus_in)
        self.search_entry.bind('<FocusOut>', self._on_focus_out)
        
    def _on_focus_in(self, event: Optional[tk.Event]) -> None:
        if self.placeholder_active:
            self.search_entry.delete(0, "end")
            self.search_entry.config(foreground=self.default_fg_color)
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
            "start_date": start_dt,
            "end_date": end_dt,
            "type_filter": self.type_combo.get(),
            "direction_filter": self.direction_combo.get(),
            "search_query": search_query
        }

    def set_input_state(self, is_active: bool) -> None:
        state = NORMAL if is_active else DISABLED
        for widget in [self.type_combo, self.direction_combo, self.search_entry, self.start_date_button, self.end_date_button]:
            try:
                widget.configure(state=state)
            except Exception:
                pass
        
        if not is_active:
            self._on_focus_out(None)
    
    def set_action_buttons_state(self, is_active: bool) -> None:
        state = NORMAL if is_active else DISABLED
        for widget in [self.filter_button, self.reset_button]:
            widget.configure(state=state)

    def re_translate(self) -> None:
        self.config(text=" " + translate("Filter") + " ")
        self.from_date_label.config(text=translate("From Date:"))
        self.to_date_label.config(text=translate("To Date:"))
        self.type_label.config(text=translate("Type:"))
        self.direction_label.config(text=translate("Direction"))
        self.filter_button.config(text=translate("Filter"))
        self.reset_button.config(text=translate("Reset Filter"))
        
        self.type_combo['values'] = [translate("ALL"), translate("coinbase"), translate("transfer")]
        self.direction_combo['values'] = [translate("ALL"), translate("incoming"), translate("outgoing")]
        
        current_state = self.search_entry.cget("state")
        self.search_entry.config(state=NORMAL)
        if self.placeholder_active:
            self.search_entry.delete(0, "end")
        self._setup_placeholder()
        self.search_entry.config(state=current_state)

# --- End of embedded FilterControls component ---


class NormalAnalysisTab(ttk.Frame):
    """
    View/Controller for the "Standard Analysis" tab.
    It performs analysis on the currently filtered set of transactions
    and displays summaries and a filterable counterparty list.
    """
    main_window: 'MainWindow'
    analysis_results: Dict[str, Any]
    main_address: str
    is_analysis_running: bool
    normal_cancel_event: threading.Event
    BATCH_LOAD_SIZE: int

    run_analysis_button: ttk.Button
    cancel_analysis_button: ttk.Button
    normal_analysis_prog_bar: ttk.Progressbar
    normal_export_component: ExportComponent
    normal_address_label: ttk.Label
    normal_summary_labelframe: ttk.Labelframe
    normal_summary_labels: Dict[str, ttk.Label]
    normal_filter_controls: _AnalysisFilterControls
    normal_tree_labelframe: ttk.Labelframe
    normal_tree: ttk.Treeview
    normal_context_menu: tk.Menu

    def __init__(
        self,
        parent: ttk.Frame,
        main_window: 'MainWindow'
    ) -> None:
        super().__init__(parent)
        self.main_window: 'MainWindow' = main_window
        self.pack(fill=BOTH, expand=True, padx=0, pady=0)

        self.analysis_results: Dict[str, Any] = {}
        self.main_address: str = ""
        self.is_analysis_running: bool = False
        self.normal_cancel_event = threading.Event()
        self.BATCH_LOAD_SIZE: int = 100

        self._build_normal_analysis_tab(self)
        self.set_controls_state(True)

    def _build_normal_analysis_tab(self, parent_frame: ttk.Frame) -> None:
        parent_frame.grid_rowconfigure(3, weight=1)
        parent_frame.grid_columnconfigure(0, weight=1)

        controls_frame = ttk.Frame(parent_frame)
        controls_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        self.run_analysis_button = ttk.Button(
            controls_frame,
            text=translate("Run Analysis"),
            command=self.run_analysis,
            state=DISABLED,
            bootstyle="primary"
        )
        self.run_analysis_button.pack(side=LEFT, padx=(0, 5))

        self.cancel_analysis_button = ttk.Button(
            controls_frame,
            text=translate("Cancel Analysis"),
            command=self._cancel_normal_analysis,
            state=DISABLED,
            bootstyle="danger"
        )
        self.cancel_analysis_button.pack(side=LEFT, padx=(0, 10))

        self.normal_address_label = ttk.Label(
            controls_frame, text="—", anchor="w", font="-size 9", bootstyle="secondary"
        )
        self.normal_address_label.pack(side=LEFT, padx=10)

        self.normal_analysis_prog_bar = ttk.Progressbar(
            controls_frame,
            mode='indeterminate',
            bootstyle="info-striped",
            length=150
        )
        self.normal_analysis_prog_bar.pack(side=LEFT, padx=5, fill=X, expand=True)
        self.normal_analysis_prog_bar.pack_forget()

        self.normal_export_component = ExportComponent(
            controls_frame, self.export_normal_analysis_data
        )
        self.normal_export_component.pack(side=RIGHT, padx=(10, 0))

        top_area_frame = ttk.Frame(parent_frame)
        top_area_frame.grid(row=2, column=0, sticky="ew", pady=5)
        top_area_frame.grid_columnconfigure(0, weight=1)
        top_area_frame.grid_columnconfigure(1, weight=1)

        self.normal_summary_labelframe = ttk.Labelframe(
            top_area_frame, text=f" {translate('Summary')} ", padding=10
        )
        self.normal_summary_labelframe.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.normal_summary_labels = {}
        self._build_normal_summary_area(self.normal_summary_labelframe)

        self.normal_filter_controls = _AnalysisFilterControls(
            top_area_frame, self.run_analysis
        )
        self.normal_filter_controls.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        self._build_normal_tree_view(parent_frame)
        self._build_normal_context_menu()

        self.show_normal_placeholder(
            translate("Load an address to see transactions.")
        )

    def _build_normal_context_menu(self) -> None:
        """Creates the right-click context menu for the treeview."""
        self.normal_context_menu = tk.Menu(self, tearoff=0)
        self._re_translate_normal_context_menu()
        self.normal_tree.bind("<Button-3>", self._show_normal_context_menu)

    def _show_normal_context_menu(self, event: tk.Event) -> None:
        """Shows the context menu on right-click if an item is valid."""
        item_id: str = self.normal_tree.identify_row(event.y)
        if not item_id:
            return

        self.normal_tree.selection_set(item_id)

        tags: List[str] = self.normal_tree.item(item_id, "tags")
        if 'child' in tags or 'placeholder' in tags:
            return

        values: Tuple[str, ...] = self.normal_tree.item(item_id, "values")
        if not values or not values[0]:
            return

        self.normal_context_menu.post(event.x_root, event.y_root)

    def _normal_add_selected_to_my_addresses(self) -> None:
        """Saves the selected counterparty address to the user's address book."""
        sel: Tuple[str, ...] = self.normal_tree.selection()
        if not sel:
            return

        item: Dict[str, Any] = self.normal_tree.item(sel[0])
        values: List[str] = item['values']

        if len(values) > 0 and values[0]:
            address: str = values[0]
            known_name: str = self.main_window.address_names_map.get(address, '')
            display_name: str = self.normal_tree.item(sel[0], "text")
            name_to_save: str = (
                known_name if known_name
                else (display_name if "..." not in display_name else "")
            )

            if self.main_window.address_manager.save_address(address, name_to_save):
                ToastNotification(
                    title=translate("Address Saved"),
                    message=f"{address[:15]}... {translate('Add to My Addresses')}",
                    bootstyle=SUCCESS
                ).show_toast()
                if (hasattr(self.main_window, 'settings_tab') and
                        self.main_window.settings_tab.address_tab_initialized and
                        self.main_window.settings_tab.address_tab):
                    self.main_window.settings_tab.address_tab.refresh_address_list()
                self.main_window.explorer_tab.input_component.refresh_address_dropdown()
            else:
                ToastNotification(
                    title=translate("Error"),
                    message=translate("Failed to save address."),
                    bootstyle=DANGER
                ).show_toast()

    def _normal_copy_selected_address(self) -> None:
        """Copies the selected counterparty address to the clipboard."""
        sel: Tuple[str, ...] = self.normal_tree.selection()
        if not sel:
            return
        values: List[str] = self.normal_tree.item(sel[0], "values")

        if len(values) > 0 and values[0]:
            address: str = values[0]
            self.clipboard_clear()
            self.clipboard_append(address)
            ToastNotification(
                title=translate("Copy Address"),
                message=f"{address[:20]}... {translate('copied to clipboard.')}",
                bootstyle=INFO
            ).show_toast()

    def _build_normal_summary_item(
        self, parent: ttk.Frame, title_key: str, value_key: str
    ) -> ttk.Frame:
        """Helper to create a single summary statistic item."""
        frame = ttk.Frame(parent, padding=5)
        title_label = ttk.Label(
            frame, text=translate(title_key), anchor="center", font="-size 8"
        )
        title_label.pack(fill=X)
        value_label = ttk.Label(
            frame,
            text="—",
            font="-size 10 -weight bold",
            anchor="center",
            bootstyle="secondary"
        )
        value_label.pack(fill=X)
        self.normal_summary_labels[value_key] = value_label
        return frame

    def _build_normal_summary_area(self, parent: ttk.Frame) -> None:
        """Constructs the grid of summary statistics."""
        parent.grid_columnconfigure(list(range(6)), weight=1, uniform="group1")

        # Row 0
        self._build_normal_summary_item(
            parent, "Total Inflow (KAS)", "Total Inflow (KAS)"
        ).grid(row=0, column=0, sticky='nsew')
        self._build_normal_summary_item(
            parent, "Total Outflow (KAS)", "Total Outflow (KAS)"
        ).grid(row=0, column=1, sticky='nsew')
        self._build_normal_summary_item(
            parent, "Net Flow (KAS)", "Net Flow (KAS)"
        ).grid(row=0, column=2, sticky='nsew')
        self._build_normal_summary_item(
            parent, "Avg Inflow (KAS)", "Avg Inflow (KAS)"
        ).grid(row=0, column=3, sticky='nsew')
        self._build_normal_summary_item(
            parent, "Avg Outflow (KAS)", "Avg Outflow (KAS)"
        ).grid(row=0, column=4, sticky='nsew')
        self._build_normal_summary_item(
            parent, "Total Transactions", "Total Transactions"
        ).grid(row=0, column=5, sticky='nsew')

        # Row 1
        self._build_normal_summary_item(
            parent, "Largest Inflow (KAS)", "Largest Inflow (KAS)"
        ).grid(row=1, column=0, sticky='nsew')
        self._build_normal_summary_item(
            parent, "Largest Outflow (KAS)", "Largest Outflow (KAS)"
        ).grid(row=1, column=1, sticky='nsew')
        self._build_normal_summary_item(
            parent, "Unique Counterparties", "Unique Counterparties"
        ).grid(row=1, column=2, sticky='nsew')
        self._build_normal_summary_item(
            parent, "First Transaction", "First Transaction"
        ).grid(row=1, column=3, sticky='nsew')
        self._build_normal_summary_item(
            parent, "Last Transaction", "Last Transaction"
        ).grid(row=1, column=4, sticky='nsew')
        self._build_normal_summary_item(
            parent, "Duration (Days)", "Duration (Days)"
        ).grid(row=1, column=5, sticky='nsew')

    def _build_normal_tree_view(self, parent: ttk.Frame) -> None:
        """Constructs the counterparty breakdown Treeview."""
        self.normal_tree_labelframe = ttk.Labelframe(
            parent, text=f" {translate('Counterparty Breakdown')} ", padding=5
        )
        self.normal_tree_labelframe.grid(
            row=3, column=0, sticky="nsew", padx=5, pady=(0, 5)
        )
        self.normal_tree_labelframe.grid_rowconfigure(0, weight=1)
        self.normal_tree_labelframe.grid_columnconfigure(0, weight=1)

        self.normal_tree = ttk.Treeview(
            self.normal_tree_labelframe,
            show="tree headings",
            bootstyle="primary",
            columns=("c1", "c2", "c3", "c4", "c5", "c6", "c7")
        )
        vsb = ttk.Scrollbar(
            self.normal_tree_labelframe,
            orient=VERTICAL,
            command=self.normal_tree.yview
        )
        hsb = ttk.Scrollbar(
            self.normal_tree_labelframe,
            orient=HORIZONTAL,
            command=self.normal_tree.xview
        )
        self.normal_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.normal_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.normal_tree.bind('<Double-1>', self._on_normal_tree_double_click)
        self.normal_tree.bind("<<TreeviewOpen>>", self._on_normal_tree_open)
        self.normal_tree.bind("<<TreeviewClose>>", self._on_normal_tree_close)

        self._configure_normal_tree_headings()
        self.normal_tree.tag_configure('child', font='-size 8')
        self.normal_tree.tag_configure('placeholder', foreground='gray')

    def _update_normal_analysis_controls(self) -> None:
        """Updates the state of analysis controls based on app state."""
        if not hasattr(self, 'run_analysis_button'):
            return

        is_data_available: bool = bool(self.main_address)
        is_running: bool = self.is_analysis_running
        self.run_analysis_button.config(
            state=NORMAL if is_data_available and not is_running else DISABLED
        )
        self.cancel_analysis_button.config(
            state=NORMAL if is_running else DISABLED
        )
        self.normal_filter_controls.set_input_state(
            is_data_available and not is_running
        )
        self.normal_filter_controls.set_action_buttons_state(
            is_data_available and not is_running
        )
        self.normal_export_component.set_ui_state(
            bool(self.analysis_results) and not is_running
        )

    def set_controls_state(self, active: bool) -> None:
        """Enables or disables all controls in this tab."""
        if not hasattr(self, 'run_analysis_button'):
            return
            
        is_normal_running: bool = self.is_analysis_running
        is_data_available: bool = bool(self.main_address)
        is_app_processing: bool = (
            self.main_window.transaction_manager.is_fetching
        )

        can_run_normal: bool = (
            active and
            is_data_available and
            not is_normal_running and
            not is_app_processing
        )
        try:
            self.run_analysis_button.config(
                state=NORMAL if can_run_normal else DISABLED
            )
            self.cancel_analysis_button.config(
                state=NORMAL if is_normal_running else DISABLED
            )
            if hasattr(self, 'normal_filter_controls'):
                self.normal_filter_controls.set_input_state(can_run_normal)
                self.normal_filter_controls.set_action_buttons_state(can_run_normal)
            if hasattr(self, 'normal_export_component'):
                self.normal_export_component.set_ui_state(
                    active and bool(self.analysis_results) and not is_normal_running
                )
        except tk.TclError as e:
            logger.warning(f"Error setting control state in NormalAnalysisTab: {e}")

    def refresh_headers(self) -> None:
        """Forces a refresh of treeview headers (e.g., for currency change)."""
        if self.winfo_exists():
            self._configure_normal_tree_headings()

    def update_data(self, main_address: Optional[str]) -> None:
        """
        Called by the main window when the address changes.
        Updates the UI to reflect the new address.
        """
        self.main_address = main_address or ""
        if hasattr(self, 'normal_address_label'):
            self.normal_address_label.config(text=self.main_address or "—")

        if not self.main_address:
            self.clear_normal_analysis()
            self.show_normal_placeholder(
                translate("Load an address to see transactions.")
            )

        is_data_available: bool = (
            bool(self.main_address) and
            not self.main_window.transaction_manager.is_fetching
        )
        self.set_controls_state(is_data_available)

    def _cancel_normal_analysis(self) -> None:
        """Sets the event to cancel the analysis worker."""
        self.normal_cancel_event.set()

    def run_analysis(self) -> None:
        """Starts the background thread for standard analysis."""
        if not self.main_address or self.is_analysis_running:
            return

        self.is_analysis_running = True
        self.normal_cancel_event.clear()

        self.clear_normal_analysis(clear_address=False)
        self.show_normal_placeholder(
            translate("Loading analysis..."), clear_address=False
        )

        self.set_controls_state(True)
        self.main_window._set_ui_for_processing(True)
        self.normal_analysis_prog_bar.pack(
            side=LEFT, padx=5, fill=X, expand=True
        )
        self.normal_analysis_prog_bar.start()

        filters: Dict[str, Any] = self.normal_filter_controls.get_filters()
        threading.Thread(
            target=self._normal_analysis_worker,
            args=(filters,),
            daemon=True,
            name="NormalAnalysisWorker"
        ).start()

    @log_performance
    def _normal_analysis_worker(self, filters: Dict[str, Any]) -> None:
        """
        Worker thread to fetch and process data for standard analysis.
        """
        try:
            df_list: List[Dict[str, Any]] = self.main_window.tx_db.filter_transactions(
                address=self.main_address, **filters
            )
            if self.normal_cancel_event.is_set():
                raise InterruptedError("Analysis cancelled.")

            if not df_list:
                if self.winfo_exists():
                    self.after(0, self.update_normal_ui, {}, False)
                return

            df = pd.DataFrame(df_list)
            if df.empty:
                if self.winfo_exists():
                    self.after(0, self.update_normal_ui, {}, False)
                return

            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
            df = df.sort_values('datetime', ascending=True).reset_index(drop=True)
            df['flow'] = df.apply(
                lambda row: row['amount'] if row['direction'] == 'incoming' else -row['amount'],
                axis=1
            )
            df['balance'] = df['flow'].cumsum()
            df_for_sql = df.set_index('datetime')

            if self.normal_cancel_event.is_set():
                raise InterruptedError("Analysis cancelled.")

            con = duckdb.connect()
            con.register('filtered_df', df)
            summary_query = """
            SELECT
                COUNT(*) AS total_transactions,
                SUM(CASE WHEN direction = 'incoming' THEN amount ELSE 0 END) AS total_inflow,
                SUM(CASE WHEN direction = 'outgoing' THEN amount ELSE 0 END) AS total_outflow,
                MAX(CASE WHEN direction = 'incoming' THEN amount ELSE 0 END) AS max_inflow,
                MAX(CASE WHEN direction = 'outgoing' THEN amount ELSE 0 END) AS max_outflow,
                AVG(CASE WHEN direction = 'incoming' THEN amount ELSE NULL END) AS avg_inflow,
                AVG(CASE WHEN direction = 'outgoing' THEN amount ELSE NULL END) AS avg_outflow,
                MIN(datetime) AS first_tx_date,
                MAX(datetime) AS last_tx_date
            FROM filtered_df
            """
            summary_df = con.execute(summary_query).fetchdf()
            summary: pd.Series = summary_df.iloc[0]

            if self.normal_cancel_event.is_set():
                raise InterruptedError("Analysis cancelled.")

            counterparties: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for row_dict in df.to_dict('records'):
                if row_dict.get('type') == 'coinbase':
                    counterparties["Coinbase / Mining"].append(row_dict)
                else:
                    is_incoming: bool = row_dict['direction'] == 'incoming'
                    addr_str: str = row_dict.get('from_address' if is_incoming else 'to_address', '')
                    addresses: List[str] = str(addr_str).split(', ')
                    for addr in addresses:
                        if (addr and
                            addr != self.main_address and
                            addr != 'N/A (Coinbase)'):
                            counterparties[addr].append(row_dict)

            if self.normal_cancel_event.is_set():
                raise InterruptedError("Analysis cancelled.")

            first_tx_date = pd.to_datetime(summary['first_tx_date'])
            last_tx_date = pd.to_datetime(summary['last_tx_date'])
            duration: int = (last_tx_date - first_tx_date).days + 1 if pd.notna(first_tx_date) else 0

            summary_snapshot: Dict[str, str] = {
                "Total Inflow (KAS)": f"{summary['total_inflow']:,.2f}",
                "Total Outflow (KAS)": f"{summary['total_outflow']:,.2f}",
                "Net Flow (KAS)": f"{(summary['total_inflow'] - summary['total_outflow']):,.2f}",
                "Avg Inflow (KAS)": f"{summary['avg_inflow']:,.2f}" if pd.notna(summary['avg_inflow']) else "0.00",
                "Avg Outflow (KAS)": f"{summary['avg_outflow']:,.2f}" if pd.notna(summary['avg_outflow']) else "0.00",
                "Total Transactions": f"{summary['total_transactions']:,}",
                "Largest Inflow (KAS)": f"{summary['max_inflow']:,.2f}" if pd.notna(summary['max_inflow']) else "0.00",
                "Largest Outflow (KAS)": f"{summary['max_outflow']:,.2f}" if pd.notna(summary['max_outflow']) else "0.00",
                "Unique Counterparties": f"{len(counterparties):,}",
                "Duration (Days)": f"{duration:,}",
                "First Transaction": first_tx_date.strftime('%Y-%m-%d') if pd.notna(first_tx_date) else "N/A",
                "Last Transaction": last_tx_date.strftime('%Y-%m-%d') if pd.notna(last_tx_date) else "N/A",
            }

            currency: str = self.main_window.currency_var.get()
            price: float = (
                self.main_window.price_updater.get_current_prices()
                .get(currency.lower(), 0.0)
            )

            final_results: Dict[str, Any] = {
                'source_df': df_for_sql,
                'counterparties': counterparties,
                'currency': currency,
                'price': price,
                'summary': summary_snapshot
            }

            if self.winfo_exists():
                self.after(0, self.update_normal_ui, final_results, True)

        except InterruptedError:
            logger.info("Analysis was cancelled by the user.")
            if self.winfo_exists():
                self.after(0, self.update_normal_ui, {'cancelled': True}, False)
        except Exception as e:
            logger.error(f"Analysis worker failed: {e}", exc_info=True)
            if self.winfo_exists():
                self.after(0, self.update_normal_ui, {'error': str(e)}, False)
        finally:
            self.is_analysis_running = False
            if self.winfo_exists():
                self.after(0, self.main_window._set_ui_for_processing, False)
                self.after(0, self.set_controls_state, True)
                self.after(0, self.normal_analysis_prog_bar.stop)
                self.after(0, self.normal_analysis_prog_bar.pack_forget)

    def on_currency_change(self) -> None:
        """Handles UI updates when the global currency is changed."""
        if not self.winfo_exists():
            return

        self.refresh_headers()

        if self.analysis_results and not self.analysis_results.get('cancelled'):
            logger.info("Currency changed, updating normal analysis tab values.")
            
            new_currency: str = self.main_window.currency_var.get()
            new_price: float = (
                self.main_window.price_updater.get_current_prices()
                .get(new_currency.lower(), 0.0)
            )
            self.analysis_results['currency'] = new_currency
            self.analysis_results['price'] = new_price

            self.run_analysis()

    @log_performance
    def update_normal_ui(
        self,
        results: Dict[str, Any],
        is_final: bool = False,
        open_nodes: Optional[Set[str]] = None
    ) -> None:
        """
        Progressively updates the UI with new analysis results.
        """
        self.analysis_results.update(results)

        if results.get('cancelled'):
            self.show_normal_placeholder(
                translate("Analysis cancelled by user."), clear_address=False
            )
            return
        if results.get('error'):
            self.show_normal_placeholder(
                results.get('error', 'Unknown error'), clear_address=False
            )
            return
        if not results or 'summary' not in results:
            self.show_normal_placeholder(
                translate("No transactions to analyze."), clear_address=False
            )
            return

        self.normal_export_component.set_ui_state(True)

        summary_data: Dict[str, Any] = results.get('summary', {})
        for key, label in self.normal_summary_labels.items():
            label.config(text=str(summary_data.get(key, "—")))

        self._update_normal_treeview_progressively(
            results.get('counterparties', {})
        )

        if open_nodes:
            for item_id in open_nodes:
                if self.normal_tree.exists(item_id):
                    self.normal_tree.item(item_id, open=True)

    def _clear_normal_tree(self) -> None:
        """Clears all items from the counterparty tree."""
        if hasattr(self, 'normal_tree'):
            for item in self.normal_tree.get_children():
                try:
                    self.normal_tree.delete(item)
                except tk.TclError:
                    pass

    def _update_normal_treeview_progressively(
        self, counterparties: Dict[str, List[Dict[str, Any]]]
    ) -> None:
        """
        Intelligently updates the treeview: inserts new rows
        or updates existing ones without clearing the whole tree.
        """
        if not hasattr(self, 'normal_tree'):
            return

        currency: str = self.analysis_results.get('currency', 'USD')
        price: float = self.analysis_results.get('price', 0.0)

        placeholder_id = "placeholder_id"
        if self.normal_tree.exists(placeholder_id):
            self.normal_tree.delete(placeholder_id)

        for address, tx_list in counterparties.items():
            tx_count: int = len(tx_list)
            net_flow: float
            display_name: str

            if address == "Coinbase / Mining":
                net_flow = sum(tx['amount'] for tx in tx_list)
                display_name = translate("Coinbase / Mining")
            else:
                net_flow = sum(
                    tx['amount'] for tx in tx_list
                    if tx['direction'] == 'incoming'
                ) - sum(
                    tx['amount'] for tx in tx_list
                    if tx['direction'] == 'outgoing'
                )
                known_name: str = (
                    self.main_window.address_names_map.get(address, '')
                )
                display_name = (
                    known_name if known_name
                    else f"{address[:15]}...{address[-5:]}"
                )

            value: float = net_flow * price
            values_tuple: Tuple[str, ...] = (
                address if address != "Coinbase / Mining" else "",
                f"{tx_count}",
                f"{net_flow:,.2f}",
                f"{value:,.2f} {currency.upper()}",
                "", "", ""
            )

            if self.normal_tree.exists(address):
                self.normal_tree.item(
                    address, text=display_name, values=values_tuple
                )
            else:
                parent_id: str = self.normal_tree.insert(
                    "",
                    "end",
                    iid=address,
                    text=display_name,
                    values=values_tuple,
                    open=False
                )
                self.normal_tree.insert(
                    parent_id, "end", text="Loading...", iid=f"child_{address}"
                )

    def _on_normal_tree_open(self, event: Any) -> None:
        """Loads child transactions when a counterparty node is expanded."""
        item_id: str = self.normal_tree.focus()
        if not item_id:
            return

        child_nodes: Tuple[str, ...] = self.normal_tree.get_children(item_id)
        if not child_nodes:
            return

        first_child_id: str = child_nodes[0]
        if first_child_id != f"child_{item_id}":
            return

        self.normal_tree.delete(first_child_id)

        tx_list: List[Dict[str, Any]] = (
            self.analysis_results.get('counterparties', {}).get(item_id, [])
        )
        if not tx_list:
            self.normal_tree.insert(
                item_id,
                "end",
                text=translate("No transactions for this counterparty."),
                tags=('child', 'placeholder')
            )
            return

        price: float = self.analysis_results.get('price', 0.0)
        currency: str = self.analysis_results.get('currency', 'USD')

        sorted_txs: List[Dict[str, Any]] = sorted(
            tx_list, key=lambda x: x['timestamp'], reverse=True
        )
        tx_iterator: Iterator[Dict[str, Any]] = iter(sorted_txs)

        self.after(
            10, self._load_normal_analysis_batch,
            item_id, tx_iterator, price, currency
        )

    def _load_normal_analysis_batch(
        self,
        item_id: str,
        tx_iterator: Iterator[Dict[str, Any]],
        price: float,
        currency: str
    ) -> None:
        """Progressively loads transaction rows into the expanded tree node."""
        if not self.normal_tree.exists(item_id):
            logger.warning(f"Batch load cancelled: Parent item {item_id} no longer exists.")
            return

        for _ in range(self.BATCH_LOAD_SIZE):
            try:
                tx = next(tx_iterator)
                txid: str = tx.get('txid', '')
                value: float = tx['amount'] * price
                self.normal_tree.insert(
                    item_id,
                    "end",
                    iid=txid,
                    text=tx['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
                    values=(
                        txid,
                        translate(tx['direction'].capitalize()),
                        f"{tx['amount']:,.2f}",
                        f"{value:,.2f} {currency.upper()}"
                        if tx.get(f"value_{currency.lower()}") is not None else "N/A",
                        tx.get('block_height', 'N/A'),
                        translate(tx.get('type', 'N/A').capitalize()),
                        ""
                    ),
                    tags=('child',)
                )
            except StopIteration:
                return
            except Exception as e:
                logger.error(f"Error during batch insert: {e}")
                return

        self.after(
            20, self._load_normal_analysis_batch,
            item_id, tx_iterator, price, currency
        )

    def _on_normal_tree_close(self, event: Any) -> None:
        """When closing a node, clear children and re-add placeholder."""
        item_id: str = self.normal_tree.focus()
        if not item_id or not self.normal_tree.get_children(item_id):
            return
        if not self.analysis_results.get('counterparties', {}).get(item_id):
            return

        first_child_id: str = self.normal_tree.get_children(item_id)[0]
        if first_child_id == f"child_{item_id}":
            return

        for child in self.normal_tree.get_children(item_id):
            self.normal_tree.delete(child)
        self.normal_tree.insert(
            item_id, "end", text="Loading...", iid=f"child_{item_id}"
        )

    def clear_normal_analysis(self, clear_address: bool = True) -> None:
        """Clears all data, charts, and summaries from the tab."""
        self._clear_normal_tree()

        if hasattr(self, 'normal_summary_labels'):
            for label in self.normal_summary_labels.values():
                label.config(text="—")

        if hasattr(self, 'normal_export_component'):
            self.normal_export_component.set_ui_state(False)
        if hasattr(self, 'normal_filter_controls'):
            self.normal_filter_controls.set_input_state(False)
            self.normal_filter_controls.set_action_buttons_state(False)

        if clear_address:
            self.main_address = ""
            if hasattr(self, 'normal_address_label'):
                self.normal_address_label.config(text="—")
        self.analysis_results.clear()

    def show_normal_placeholder(
        self, message: str, clear_address: bool = True
    ) -> None:
        """Clears the tab and shows a placeholder message in the tree."""
        self.clear_normal_analysis(clear_address=clear_address)
        if hasattr(self, 'normal_tree'):
            self.normal_tree.insert(
                "", "end", text=message, tags=('placeholder',), iid="placeholder_id"
            )

    def _on_normal_tree_double_click(self, event: Any) -> None:
        """Handles double-click on the tree to open explorer."""
        item_id: str = self.normal_tree.focus()
        if not item_id:
            return

        tags: List[str] = self.normal_tree.item(item_id, "tags")
        if 'child' in tags:
            values: List[str] = self.normal_tree.item(item_id, "values")
            txid: str = values[0]
            if txid:
                try:
                    url: str = get_active_api_config()['explorer']['transaction'].format(txid=txid)
                    webbrowser.open(url, new=2)
                except KeyError:
                    logger.warning("Explorer transaction URL not configured.")
        elif 'placeholder' not in tags:
            values = self.normal_tree.item(item_id)['values']
            if values and values[0]:
                address: str = values[0]
                try:
                    url = get_active_api_config()['explorer']['address'].format(kaspaAddress=address)
                    webbrowser.open(url, new=2)
                except KeyError:
                    logger.warning("Explorer address URL not configured.")

    def _configure_normal_tree_headings(self) -> None:
        """Sets or updates the treeview column headings with translations."""
        if not hasattr(self, 'normal_tree'):
            return

        currency: str = self.main_window.currency_var.get().upper()
        self.normal_tree.heading(
            "#0", text=f"{translate('Known Name')} / {translate('Date/Time')}"
        )
        self.normal_tree.heading(
            "c1", text=f"{translate('Address')} / {translate('Transaction ID')}"
        )
        self.normal_tree.heading(
            "c2", text=f"{translate('TXs')} / {translate('Direction')}"
        )
        self.normal_tree.heading(
            "c3",
            text=f"{translate('Net Flow (KAS)')} / {translate('Amount (KAS)')}"
        )
        self.normal_tree.heading("c4", text=f"{translate('Value')} ({currency})")
        self.normal_tree.heading("c5", text=translate("Block Score"))
        self.normal_tree.heading("c6", text=translate("Type"))
        self.normal_tree.heading("c7", text="")

        self.normal_tree.column("#0", width=180, stretch=False)
        self.normal_tree.column("c1", width=350, stretch=True)
        self.normal_tree.column("c2", width=80, stretch=False, anchor='center')
        self.normal_tree.column("c3", width=150, stretch=False, anchor='e')
        self.normal_tree.column("c4", width=150, stretch=False, anchor='e')
        self.normal_tree.column("c5", width=120, stretch=False, anchor='e')
        self.normal_tree.column("c6", width=100, stretch=False, anchor='center')
        self.normal_tree.column("c7", width=0, stretch=False, minwidth=0)

    def _re_translate_normal_context_menu(self) -> None:
        """Updates the text of the context menu items."""
        if not hasattr(self, 'normal_context_menu'):
            return
        self.normal_context_menu.delete(0, END)
        self.normal_context_menu.add_command(
            label=translate("Add to My Addresses"),
            command=self._normal_add_selected_to_my_addresses
        )
        self.normal_context_menu.add_command(
            label=translate("Copy Address"),
            command=self._normal_copy_selected_address
        )

    def re_translate(self) -> None:
        """Reloads all translatable text in the tab."""
        if not hasattr(self, 'run_analysis_button'):
            return

        self.run_analysis_button.config(text=translate("Run Analysis"))
        self.cancel_analysis_button.config(text=translate("Cancel Analysis"))
        self.normal_summary_labelframe.config(text=f" {translate('Summary')} ")
        self.normal_tree_labelframe.config(
            text=f" {translate('Counterparty Breakdown')} "
        )
        
        if hasattr(self, 'normal_filter_controls'):
            self.normal_filter_controls.re_translate()
        if hasattr(self, 'normal_export_component'):
            self.normal_export_component.re_translate()

        for widget in self.normal_summary_labelframe.winfo_children():
            widget.destroy()
        self._build_normal_summary_area(self.normal_summary_labelframe)

        self._configure_normal_tree_headings()
        self._re_translate_normal_context_menu()

        if self.analysis_results:
            self.update_normal_ui(self.analysis_results, is_final=True)
        else:
            self.show_normal_placeholder(
                translate("Load an address to see transactions.")
            )

    @log_performance
    def export_normal_analysis_data(self, export_format: str) -> None:
        """Handles the export data button press."""
        if not self.analysis_results:
            ToastNotification(
                title=translate("Export Results:"),
                message=translate("No data to export."),
                bootstyle=WARNING
            ).show_toast()
            return

        addr_short: str = (
            self.main_address.split(":")[-1][:8]
            if self.main_address else "analysis"
        )
        ts: str = datetime.now().strftime('%Y%m%d_%H%M%S')
        initial_filename: str = (
            f"kaspa_analysis_{addr_short}_{ts}.{export_format}"
        )
        export_dir: str = (
            self.main_window.config_manager.get_config()
            .get('paths', {}).get('export', '.')
        )
        os.makedirs(export_dir, exist_ok=True)

        file_path: Optional[str] = filedialog.asksaveasfilename(
            initialfile=initial_filename,
            defaultextension=f".{export_format}",
            filetypes=[(f"{export_format.upper()} files", f"*.{export_format}")],
            title=f"{translate('Save as')} {export_format.upper()}",
            initialdir=export_dir
        )

        if not file_path:
            return

        self.main_window.status.update_status(
            f"Exporting to {export_format.upper()}..."
        )
        
        export_args: Dict[str, Any] = {
            "file_path": file_path,
            "kaspa_address": self.main_address,
            "address_name": self.main_window.address_names_map.get(
                self.main_address, ""
            ),
            "currency": self.main_window.currency_var.get(),
            "counterparties": self.analysis_results.get('counterparties', {}),
            "known_names_map": self.main_window.address_names_map,
            "analysis_data": {
                "summary": self.analysis_results.get('summary')
            }
        }

        threading.Thread(
            target=self._export_normal_worker,
            args=(export_format, export_args),
            daemon=True,
            name="NormalExportWorker"
        ).start()

    @log_performance
    def _export_normal_worker(
        self, export_format: str, export_args: Dict[str, Any]
    ) -> None:
        """
        Background thread to perform the data export.
        """
        try:
            export_func_map: Dict[str, Callable[..., Tuple[bool, str, str]]] = {
                'csv': export_analysis_to_csv,
                'html': export_analysis_to_html,
                'pdf': export_analysis_to_pdf
            }
            export_func = export_func_map.get(export_format)
            
            if not export_func:
                raise ValueError(f"No export function for format: {export_format}")

            if export_format == 'csv':
                export_args.pop('analysis_data', None)

            success, msg_key, details = export_func(**export_args)
            final_msg: str = (
                f"{translate(msg_key)}: {details}" if details
                else translate(msg_key)
            )
            if self.winfo_exists():
                if success:
                    self.after(
                        100,
                        self.main_window.prompt_to_open_file,
                        export_args["file_path"],
                        final_msg
                    )
                else:
                    self.after(0, lambda: messagebox.showerror(translate("Error"), final_msg))
        except Exception as e:
            logger.error(f"Analysis export to {export_format} failed", exc_info=True)
            if self.winfo_exists():
                self.after(0, lambda: ToastNotification(
                    title=translate("Error"),
                    message=f"{translate('Check logs for details.')} - {e}",
                    bootstyle=DANGER,
                    duration=3000
                ).show_toast())
        finally:
            if self.winfo_exists():
                self.after(0, self.main_window.status.update_status, "Ready")
