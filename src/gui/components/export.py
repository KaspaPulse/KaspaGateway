from typing import Callable

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from src.utils.i18n import translate


class ExportComponent(ttk.Frame):
    def __init__(self, parent, export_callback: Callable[[str], None]):
        super().__init__(parent, padding=(5, 5))
        self.export_callback = export_callback

        self.grid_columnconfigure(4, weight=1)

        self.label = ttk.Label(self, text=translate("Export Results:"))
        self.label.pack(side=LEFT, padx=(0, 10))

        self.csv_button = ttk.Button(
            self,
            text=translate("Save as CSV"),
            command=lambda: self.export_callback("csv"),
            bootstyle="info",
        )
        self.csv_button.pack(side=LEFT, padx=5)

        self.html_button = ttk.Button(
            self,
            text=translate("Save as HTML"),
            command=lambda: self.export_callback("html"),
            bootstyle="info",
        )
        self.html_button.pack(side=LEFT, padx=5)

        self.pdf_button = ttk.Button(
            self,
            text=translate("Save as PDF"),
            command=lambda: self.export_callback("pdf"),
            bootstyle="info",
        )
        self.pdf_button.pack(side=LEFT, padx=5)

        self.set_ui_state(False)

    def set_ui_state(self, is_active: bool):
        state = NORMAL if is_active else DISABLED
        self.csv_button.configure(state=state)
        self.html_button.configure(state=state)
        self.pdf_button.configure(state=state)

    def re_translate(self):
        self.label.config(text=translate("Export Results:"))
        self.csv_button.config(text=translate("Save as CSV"))
        self.html_button.config(text=translate("Save as HTML"))
        self.pdf_button.config(text=translate("Save as PDF"))
