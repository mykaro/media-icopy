import os
import threading
import customtkinter as ctk

from ..constants import T_GREEN, T_DIM, T_DARK, T_BG, T_PANEL, T_RED, T_FONT_NAME
from ...adapters.mtp_adapter import MTPFileSource
from ...i18n import t, add_listener, remove_listener, get_lang
from ...paths import resource_path


class DeviceFolderBrowser(ctk.CTkToplevel):
    def __init__(self, parent, device_name, on_select):
        super().__init__(parent)
        self.title(f"Огляд: {device_name}")
        self.geometry("450x600")
        self.configure(fg_color=T_BG)

        icon_path = resource_path("assets", "logo_256x256.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)

        self.transient(parent)
        self.grab_set()

        self._init_state(device_name, on_select)
        self._build_ui()

        add_listener(self.rebuild_texts)
        self.rebuild_texts()

        self.refresh_list()

    def _init_state(self, device_name, on_select):
        self.device_name = device_name
        self.on_select = on_select
        self.current_path = ""
        self.selected_paths = set()
        self.mtp = MTPFileSource(device_name)
        self._is_loading = False

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # RobCo Header
        self.lbl_header = ctk.CTkLabel(
            self,
            text="-DIRECTORY LISITING-\n====================",
            font=(T_FONT_NAME, 14, "bold"),
            text_color=T_GREEN,
        )
        self.lbl_header.grid(row=0, column=0, padx=20, pady=(15, 5))

        # Header Path
        self.lbl_path = ctk.CTkLabel(
            self,
            text=t("browser.path", path="/"),
            wraplength=400,
            font=(T_FONT_NAME, 14),
            text_color=T_DIM,
        )
        self.lbl_path.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="w")

        # Scrollable area for folders
        self.frame_folders = ctk.CTkScrollableFrame(
            self, fg_color=T_PANEL, border_width=1, border_color=T_DARK, corner_radius=0
        )
        self.frame_folders.grid(row=2, column=0, padx=20, pady=5, sticky="nsew")

        # Footer Buttons
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.btn_frame.grid(row=3, column=0, padx=20, pady=20, sticky="ew")

        self.btn_back = ctk.CTkButton(
            self.btn_frame,
            text=t("browser.back_btn"),
            width=120,
            font=(T_FONT_NAME, 14),
            fg_color="transparent",
            border_width=0,
            text_color=T_GREEN,
            hover_color=T_DARK,
            corner_radius=0,
            command=self.go_back,
        )
        self.btn_back.pack(side="left", padx=5)

        self.btn_select = ctk.CTkButton(
            self.btn_frame,
            text=t("browser.select_btn"),
            font=(T_FONT_NAME, 14, "bold"),
            fg_color="transparent",
            border_width=0,
            text_color=T_GREEN,
            hover_color=T_DARK,
            corner_radius=0,
            command=self.do_select,
        )
        self.btn_select.pack(side="right", padx=5)

    def refresh_list(self):
        if self._is_loading:
            return

        self._is_loading = True
        for child in self.frame_folders.winfo_children():
            child.destroy()

        self.lbl_path.configure(text=t("browser.path", path=self.current_path or "/"))

        loading_lbl = ctk.CTkLabel(
            self.frame_folders,
            text="< LOADING... >",
            font=(T_FONT_NAME, 14),
            text_color=T_GREEN,
        )
        loading_lbl.pack(pady=40)

        def fetch():
            try:
                folders = self.mtp.list_subfolders(self.current_path)
            except Exception:
                folders = []
            self.after(0, lambda: self._apply_folders(folders))

        threading.Thread(target=fetch, daemon=True).start()

    def _apply_folders(self, folders):
        self._is_loading = False
        for child in self.frame_folders.winfo_children():
            child.destroy()

        if not folders and not self.current_path:
            lbl = ctk.CTkLabel(
                self.frame_folders,
                text=t("browser.access_error"),
                font=(T_FONT_NAME, 14),
                text_color=T_RED,
                justify="left",
            )
            lbl.pack(pady=40, padx=10, anchor="w")
            return

        for folder in folders:
            full_path = f"{self.current_path}/{folder}" if self.current_path else folder

            row = ctk.CTkFrame(
                self.frame_folders, fg_color="transparent", corner_radius=0
            )
            row.pack(fill="x", pady=2)

            cb = ctk.CTkCheckBox(
                row,
                text="",
                width=24,
                border_color=T_DIM,
                hover_color=T_DARK,
                fg_color=T_GREEN,
                checkmark_color="#000000",
                corner_radius=0,
                command=lambda p=full_path: self.toggle_path(p),
            )
            if full_path in self.selected_paths:
                cb.select()
            cb.pack(side="left", padx=(5, 5))

            btn = ctk.CTkButton(
                row,
                text=f"  DIR >> {folder}",
                font=(T_FONT_NAME, 14),
                fg_color="transparent",
                border_width=0,
                text_color=T_GREEN,
                anchor="w",
                hover_color=T_PANEL,
                corner_radius=0,
                command=lambda f=folder: self.enter_folder(f),
            )
            btn.pack(side="left", fill="x", expand=True)

    def toggle_path(self, path):
        if path in self.selected_paths:
            self.selected_paths.remove(path)
        else:
            self.selected_paths.add(path)

    def enter_folder(self, name):
        if self.current_path:
            self.current_path = f"{self.current_path}/{name}"
        else:
            self.current_path = name
        self.refresh_list()

    def go_back(self):
        if not self.current_path:
            return

        parts = self.current_path.split("/")
        if len(parts) <= 1:
            self.current_path = ""
        else:
            self.current_path = "/".join(parts[:-1])
        self.refresh_list()

    def do_select(self):
        # If nothing selected with checkboxes, use current path
        final_list = (
            list(self.selected_paths) if self.selected_paths else [self.current_path]
        )
        self.on_select(final_list)
        self.destroy()

    def destroy(self):
        remove_listener(self.rebuild_texts)
        super().destroy()

    def rebuild_texts(self):
        self.title(t("browser.title", device=self.device_name))
        self.lbl_header.configure(text=t("browser.header"))
        self.lbl_path.configure(text=t("browser.path", path=self.current_path or "/"))
        self.btn_back.configure(text=t("browser.back_btn"))
        self.btn_select.configure(text=t("browser.select_btn"))
        self.refresh_list()
