import os
import customtkinter as ctk

from ..constants import T_BG, T_GREEN


class ModalDialog(ctk.CTkToplevel):
    """Base class for centered, borderless modal dialogs."""

    def __init__(self, parent: ctk.CTkToplevel | ctk.CTk, width: int, height: int):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(fg_color=T_BG)

        self.width = width
        self.height = height

        self._center_window(parent)

        self.main_frame = ctk.CTkFrame(
            self, fg_color=T_BG, border_color=T_GREEN, border_width=1, corner_radius=0
        )
        self.main_frame.pack(fill="both", expand=True)

    def _center_window(self, parent: ctk.CTkToplevel | ctk.CTk) -> None:
        """Centers the dialog relative to its parent window and makes it modal."""
        self.update_idletasks()
        p_x = parent.winfo_rootx()
        p_y = parent.winfo_rooty()
        p_w = parent.winfo_width()
        p_h = parent.winfo_height()

        x = p_x + (p_w // 2) - (self.width // 2)
        y = p_y + (p_h // 2) - (self.height // 2)
        self.geometry(f"{self.width}x{self.height}+{x}+{y}")

        self.transient(parent)
        self.grab_set()
        self.focus_force()

        # Enforce strict transient Z-order on Windows for borderless windows
        if os.name == "nt":
            try:
                import ctypes
                import sys

                hwnd_child = ctypes.windll.user32.GetParent(self.winfo_id())
                hwnd_parent = ctypes.windll.user32.GetParent(parent.winfo_id())
                if sys.maxsize > 2**32:
                    ctypes.windll.user32.SetWindowLongPtrW(hwnd_child, -8, hwnd_parent)
                else:
                    ctypes.windll.user32.SetWindowLongW(hwnd_child, -8, hwnd_parent)
            except Exception:
                pass
