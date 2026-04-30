import customtkinter as ctk
import webbrowser
from ..constants import T_GREEN, T_DIM, T_DARK, T_BG, T_FONT_NAME
from ...i18n import t, add_listener, remove_listener
from .modal import ModalDialog


class UpdateDialog(ModalDialog):
    def __init__(
        self, parent, new_version: str, current_version: str, download_url: str
    ):
        super().__init__(parent, width=450, height=200)

        self.new_version = new_version
        self.current_version = current_version
        self.download_url = download_url
        self._parent = parent

        self._parent.attributes("-disabled", True)
        self._build_ui()

        add_listener(self.rebuild_texts)

    def _build_ui(self):

        # Title
        self.lbl_title = ctk.CTkLabel(
            self.main_frame,
            text=t("update.title"),
            font=(T_FONT_NAME, 16, "bold"),
            text_color=T_GREEN,
        )
        self.lbl_title.pack(pady=(20, 10))

        # Message
        self.lbl_msg = ctk.CTkLabel(
            self.main_frame,
            text=t(
                "update.message", version=self.new_version, current=self.current_version
            ),
            font=(T_FONT_NAME, 14),
            text_color=T_DIM,
            justify="center",
        )
        self.lbl_msg.pack(pady=(10, 30))

        # Buttons Frame
        self.btn_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.btn_frame.pack(pady=(0, 20))

        self.btn_download = ctk.CTkButton(
            self.btn_frame,
            text=t("update.btn_download"),
            font=(T_FONT_NAME, 14, "bold"),
            fg_color="transparent",
            border_width=1,
            border_color=T_GREEN,
            text_color=T_GREEN,
            hover_color=T_DARK,
            corner_radius=0,
            command=self._on_download,
        )
        self.btn_download.pack(side="left", padx=10)

        self.btn_skip = ctk.CTkButton(
            self.btn_frame,
            text=t("update.btn_skip"),
            font=(T_FONT_NAME, 14),
            fg_color="transparent",
            border_width=0,
            text_color=T_DIM,
            hover_color=T_DARK,
            corner_radius=0,
            command=self._close,
        )
        self.btn_skip.pack(side="left", padx=10)

    def rebuild_texts(self):
        try:
            self.lbl_title.configure(text=t("update.title"))
            self.lbl_msg.configure(
                text=t(
                    "update.message",
                    version=self.new_version,
                    current=self.current_version,
                )
            )
            self.btn_download.configure(text=t("update.btn_download"))
            self.btn_skip.configure(text=t("update.btn_skip"))
        except Exception:
            pass

    def _on_download(self):
        if self.download_url:
            webbrowser.open(self.download_url)
        self._close()

    def _close(self):
        remove_listener(self.rebuild_texts)
        self._parent.attributes("-disabled", False)
        self.destroy()
