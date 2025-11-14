import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import logging
from src.utils.i18n import translate

logger = logging.getLogger(__name__)

class Status(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.grid_columnconfigure(0, weight=1)
        self.label = ttk.Label(self, text=translate("Ready"), anchor="w", font="-size 10")
        self.label.grid(row=0, column=0, sticky="ew")
    
    def update_status(self, message_key: str, *args):
        try:

            log_message = message_key.format(*args) if args else message_key
            logger.info(f"Status updated: {log_message}")

            if self.winfo_exists():
                formatted_message = translate(message_key).format(*args)
                self.label.configure(text=formatted_message)
        except Exception as e:
            logger.error(f"Could not update status message for key '{message_key}': {e}", exc_info=True)

    def re_translate(self):

        current_text_key = "Ready"
        if "جاهز" in self.label.cget("text"):
             current_text_key = "Ready" # Example of mapping back, can be improved if more states are needed
        self.update_status(current_text_key)







