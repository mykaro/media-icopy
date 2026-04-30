import customtkinter as ctk
import os
import webbrowser
from PIL import Image
from ..constants import T_GREEN, T_DIM, T_DARK, T_BG, T_FONT_NAME
from ...i18n import t, add_listener, remove_listener
from .modal import ModalDialog
from ...paths import resource_path


class SayThanksWindow(ModalDialog):
    def __init__(self, parent):
        super().__init__(parent, width=700, height=525)

        self._build_ui()

        add_listener(self.rebuild_texts)
        self.rebuild_texts()

    def _build_ui(self):
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Close button top right
        self.btn_close = ctk.CTkButton(
            self.main_frame,
            text="[ ✕ ]",
            width=30,
            height=30,
            font=(T_FONT_NAME, 14, "bold"),
            fg_color="transparent",
            border_width=0,
            text_color=T_GREEN,
            hover_color=T_DARK,
            corner_radius=0,
            command=self.destroy,
        )
        self.btn_close.place(relx=1.0, rely=0.0, anchor="ne", x=-5, y=5)

        # Header
        self.lbl_header = ctk.CTkLabel(
            self.main_frame,
            text="",
            font=(T_FONT_NAME, 14, "bold"),
            justify="center",
            text_color=T_GREEN,
        )
        self.lbl_header.grid(row=0, column=0, padx=20, pady=(30, 10))

        # Message 1
        self.lbl_msg1 = ctk.CTkLabel(
            self.main_frame,
            text="",
            justify="center",
            font=(T_FONT_NAME, 14),
            text_color=T_DIM,
        )
        self.lbl_msg1.grid(row=1, column=0, padx=20, pady=(10, 10))

        # Thin Separator
        self.separator = ctk.CTkFrame(
            self.main_frame, height=3, fg_color=T_DARK, corner_radius=0
        )
        self.separator.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        # Intro Message
        self.lbl_intro = ctk.CTkLabel(
            self.main_frame,
            text="",
            justify="center",
            font=(T_FONT_NAME, 14),
            text_color=T_DIM,
        )
        self.lbl_intro.grid(row=3, column=0, padx=20, pady=(10, 10))

        # Reddit Section
        self.lbl_reddit_hint = ctk.CTkLabel(
            self.main_frame,
            text="",
            justify="center",
            font=(T_FONT_NAME, 14),
            text_color=T_DIM,
        )
        self.lbl_reddit_hint.grid(row=4, column=0, padx=20, pady=(5, 5))

        # Індивідуальні розміри для кожного логотипу (Ширина, Висота)
        reddit_size = (100, 25)
        kofi_size = (100, 30)
        patreon_size = (150, 30)
        binance_size = (150, 30)

        self.img_reddit = ctk.CTkImage(
            light_image=Image.open(resource_path("assets", "reddit-logo.png")),
            size=reddit_size,
        )
        self.img_kofi = ctk.CTkImage(
            light_image=Image.open(resource_path("assets", "ko-fi-logo.png")),
            size=kofi_size,
        )
        self.img_patreon = ctk.CTkImage(
            light_image=Image.open(resource_path("assets", "patreon-logo.png")),
            size=patreon_size,
        )
        self.img_binance = ctk.CTkImage(
            light_image=Image.open(resource_path("assets", "binance-logo.png")),
            size=binance_size,
        )

        self.btn_reddit = ctk.CTkButton(
            self.main_frame,
            text="",
            image=self.img_reddit,
            fg_color="transparent",
            hover_color=T_DARK,
            width=reddit_size[0],
            height=reddit_size[1],
            corner_radius=0,
            command=lambda: webbrowser.open("https://www.reddit.com/user/by_mykaro/"),
        )
        self.btn_reddit.grid(row=5, column=0, padx=20, pady=(0, 15))

        # Finance Section
        self.lbl_finance_hint = ctk.CTkLabel(
            self.main_frame,
            text="",
            justify="center",
            font=(T_FONT_NAME, 14),
            text_color=T_DIM,
        )
        self.lbl_finance_hint.grid(row=6, column=0, padx=20, pady=(5, 5))

        self.finance_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.finance_frame.grid(row=7, column=0, padx=20, pady=(0, 5))

        self.btn_kofi = ctk.CTkButton(
            self.finance_frame,
            text="",
            image=self.img_kofi,
            fg_color="transparent",
            hover_color=T_DARK,
            width=kofi_size[0],
            height=kofi_size[1],
            corner_radius=0,
            command=lambda: webbrowser.open("https://ko-fi.com/bymykaro"),
        )
        self.btn_kofi.grid(row=0, column=0, padx=10)

        self.btn_patreon = ctk.CTkButton(
            self.finance_frame,
            text="",
            image=self.img_patreon,
            fg_color="transparent",
            hover_color=T_DARK,
            width=patreon_size[0],
            height=patreon_size[1],
            corner_radius=0,
            command=lambda: webbrowser.open("https://patreon.com/Mykaro"),
        )
        self.btn_patreon.grid(row=0, column=1, padx=10)

        self.btn_binance = ctk.CTkButton(
            self.finance_frame,
            text="",
            image=self.img_binance,
            fg_color="transparent",
            hover_color=T_DARK,
            width=binance_size[0],
            height=binance_size[1],
            corner_radius=0,
            command=self.copy_binance_id,
        )
        self.btn_binance.grid(row=0, column=2, padx=10)

        # Binance Status Label
        self.lbl_binance_status = ctk.CTkLabel(
            self.main_frame, text="", font=(T_FONT_NAME, 12, "bold"), text_color=T_GREEN
        )
        self.lbl_binance_status.grid(row=8, column=0, padx=20, pady=(0, 10))

        # Final thanks
        self.lbl_thanks = ctk.CTkLabel(
            self.main_frame, text="", font=(T_FONT_NAME, 14, "bold"), text_color=T_GREEN
        )
        self.lbl_thanks.grid(row=9, column=0, padx=20, pady=(0, 30))

    def destroy(self):
        remove_listener(self.rebuild_texts)
        super().destroy()

    def copy_binance_id(self):
        self.clipboard_clear()
        self.clipboard_append("451987508")
        self.lbl_binance_status.configure(text=t("thanks.binance_copied"))
        self.after(3000, lambda: self.lbl_binance_status.configure(text=""))

    def rebuild_texts(self):
        self.lbl_header.configure(text=t("thanks.header"))
        self.lbl_msg1.configure(text=t("thanks.msg1"))
        self.lbl_intro.configure(text=t("thanks.msg_intro"))
        self.lbl_reddit_hint.configure(text=t("thanks.msg_reddit"))
        self.lbl_finance_hint.configure(text=t("thanks.msg_finance"))
        self.lbl_thanks.configure(text=t("thanks.footer"))
