import os
import time
import threading
import ctypes
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog
from datetime import datetime
import webbrowser

from ..infrastructure.config import AppConfig
from ..infrastructure.logger import setup_logging
from ..core_runner import CopierRunner
from ..adapters.mtp_adapter import MTPFileSource, MTPDeviceRegistry
from ..domain.models import ProgressInfo, MessageType
from ..utils import format_size, check_for_updates, format_elapsed, calculate_eta
from ..i18n import t, set_lang, get_lang, add_listener

from .constants import (
    T_GREEN,
    T_DIM,
    T_DARK,
    T_BG,
    T_PANEL,
    T_RED,
    T_FONT_NAME,
    APP_VERSION,
    GITHUB_REPO,
    GITHUB_URL,
)
from .components import DeviceFolderBrowser, SayThanksWindow, UpdateDialog
from .state import AppState
from .mixins import AnimationMixin, TooltipMixin
from ..paths import resource_path

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")


class App(ctk.CTk, AnimationMixin, TooltipMixin):
    def __init__(self):
        super().__init__()

        self.title("Media iCopy")
        self.geometry("925x600")
        self.minsize(925, 600)
        self.configure(fg_color=T_BG)
        self._center_window()

        icon_path = resource_path("assets", "logo_256x256.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)

        # Fix for taskbar icon in Windows
        try:
            myappid = "mykaro.mediaicopy.terminal.1"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        # Runner
        self.runner = None
        self.copy_thread = None
        self.tw = None
        self.app_state = AppState()

        # -- UI Elements --
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(4, weight=1)  # Log area expands

        # RobCo OS Header
        self.lbl_header = ctk.CTkLabel(
            self,
            text=t("app.title"),
            font=(T_FONT_NAME, 14, "bold"),
            text_color=T_GREEN,
        )
        self.lbl_header.grid(row=0, column=0, columnspan=3, pady=(15, 10), sticky="n")

        # Update Indicator
        self.update_info_data = None
        self.btn_update_indicator = ctk.CTkButton(
            self,
            text=t("app.update_indicator"),
            font=(T_FONT_NAME, 12, "bold"),
            fg_color=T_GREEN,
            text_color=T_BG,
            hover_color=T_DIM,
            corner_radius=0,
            command=self.open_update_dialog_manual,
        )
        self.btn_update_indicator.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="nw")
        self.btn_update_indicator.grid_remove()  # Hidden by default

        # Share Button
        share_icon_path = resource_path("assets", "share.png")
        if os.path.exists(share_icon_path):
            from PIL import Image
            self.img_share = ctk.CTkImage(
                light_image=Image.open(share_icon_path),
                dark_image=Image.open(share_icon_path),
                size=(18, 18)
            )
        else:
            self.img_share = None

        self.btn_share = ctk.CTkButton(
            self,
            text=t("app.share_btn"),
            image=self.img_share,
            compound="left",
            font=(T_FONT_NAME, 12, "bold"),
            fg_color="transparent",
            text_color=T_GREEN,
            hover_color=T_DARK,
            corner_radius=0,
            command=self.share_app,
        )
        self.btn_share.grid(row=0, column=2, padx=30, pady=(15, 10), sticky="ne")

        # 1. Device Selection
        self.lbl_device = ctk.CTkLabel(
            self, text=t("app.device_label"), font=(T_FONT_NAME, 14), text_color=T_DIM
        )
        self.lbl_device.grid(row=1, column=0, padx=30, pady=(10, 5), sticky="w")

        self.combo_device = ctk.CTkComboBox(
            self,
            values=[t("app.no_devices")],
            width=300,
            font=(T_FONT_NAME, 14),
            fg_color="#000000",
            border_color=T_DARK,
            button_color=T_DARK,
            button_hover_color=T_DIM,
            dropdown_font=(T_FONT_NAME, 14),
            text_color=T_GREEN,
            corner_radius=0,
        )
        self.combo_device.grid(row=1, column=1, padx=(0, 10), pady=(10, 5), sticky="w")

        self.btn_refresh = ctk.CTkButton(
            self,
            text=t("app.refresh_btn"),
            width=140,
            font=(T_FONT_NAME, 14),
            fg_color="transparent",
            border_width=0,
            text_color=T_GREEN,
            hover_color=T_DARK,
            corner_radius=0,
            command=self.refresh_devices,
        )
        self.btn_refresh.grid(row=1, column=2, padx=(0, 30), pady=(10, 5))

        # 2. Source Folder
        self.lbl_source = ctk.CTkLabel(
            self, text=t("app.source_label"), font=(T_FONT_NAME, 14), text_color=T_DIM
        )
        self.lbl_source.grid(row=2, column=0, padx=30, pady=(15, 5), sticky="w")

        self.entry_source = ctk.CTkEntry(
            self,
            placeholder_text=t("app.wait_input"),
            font=(T_FONT_NAME, 14),
            fg_color="#000000",
            border_color=T_DARK,
            text_color=T_GREEN,
            corner_radius=0,
        )
        self.entry_source.grid(row=2, column=1, padx=(0, 10), pady=(15, 5), sticky="ew")

        self.btn_browse_source = ctk.CTkButton(
            self,
            text=t("app.browse_btn"),
            width=140,
            font=(T_FONT_NAME, 14),
            fg_color="transparent",
            border_width=0,
            text_color=T_GREEN,
            hover_color=T_DARK,
            corner_radius=0,
            command=self.browse_iphone,
        )
        self.btn_browse_source.grid(row=2, column=2, padx=(0, 30), pady=(15, 5))

        # 3. Destination Folder
        self.lbl_dest = ctk.CTkLabel(
            self, text=t("app.dest_label"), font=(T_FONT_NAME, 14), text_color=T_DIM
        )
        self.lbl_dest.grid(row=3, column=0, padx=30, pady=(15, 5), sticky="w")

        self.entry_dest = ctk.CTkEntry(
            self,
            placeholder_text=t("app.wait_input"),
            font=(T_FONT_NAME, 14),
            fg_color="#000000",
            border_color=T_DARK,
            text_color=T_GREEN,
            corner_radius=0,
        )
        self.entry_dest.grid(row=3, column=1, padx=(0, 10), pady=(15, 5), sticky="ew")

        self.btn_browse = ctk.CTkButton(
            self,
            text=t("app.select_btn"),
            width=140,
            font=(T_FONT_NAME, 14),
            fg_color="transparent",
            border_width=0,
            text_color=T_GREEN,
            hover_color=T_DARK,
            corner_radius=0,
            command=self.browse_dest,
        )
        self.btn_browse.grid(row=3, column=2, padx=(0, 30), pady=(15, 5))

        # 4. Logs Textbox
        self.textbox = ctk.CTkTextbox(
            self,
            state="normal",
            font=(T_FONT_NAME, 13),
            fg_color="#050505",
            text_color=T_DIM,
            border_color=T_DARK,
            border_width=1,
            corner_radius=0,
        )
        self.textbox.grid(
            row=4, column=0, columnspan=3, padx=30, pady=(20, 10), sticky="nsew"
        )
        self.textbox.bind(
            "<Key>",
            lambda e: (
                "break" if not (e.state & 4 and e.keysym.lower() == "c") else None
            ),
        )

        # 5. Progress
        self.progressbar = ctk.CTkProgressBar(
            self,
            progress_color=T_GREEN,
            fg_color="#000000",
            border_color=T_DARK,
            border_width=1,
            height=12,
            corner_radius=0,
        )
        self.progressbar.grid(
            row=5, column=0, columnspan=3, padx=30, pady=(5, 5), sticky="ew"
        )
        self.progressbar.set(0)

        self.lbl_eta = ctk.CTkLabel(
            self, text=t("app.waiting"), font=(T_FONT_NAME, 14), text_color=T_DIM
        )
        self.lbl_eta.grid(row=6, column=2, padx=30, sticky="e")

        self.lbl_progress = ctk.CTkLabel(
            self, text=t("app.ready"), font=(T_FONT_NAME, 14), text_color=T_GREEN
        )
        self.lbl_progress.grid(
            row=6, column=0, columnspan=2, padx=30, pady=(0, 10), sticky="w"
        )

        # 5.5 Options
        self.options_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.options_frame.grid(
            row=7, column=0, columnspan=3, padx=30, pady=(10, 5), sticky="w"
        )

        self.chk_skip_aae = ctk.CTkCheckBox(
            self.options_frame,
            text=t("app.skip_aae"),
            font=(T_FONT_NAME, 14),
            text_color=T_DIM,
            border_color=T_DIM,
            hover_color=T_DARK,
            fg_color=T_GREEN,
            checkmark_color="#000000",
            corner_radius=0,
        )
        self.chk_skip_aae.pack(side="left")
        self.chk_skip_aae.select()

        # Tooltip icon
        self.lbl_info = ctk.CTkLabel(
            self.options_frame,
            text="[?]",
            font=(T_FONT_NAME, 14, "bold"),
            text_color=T_GREEN,
            cursor="hand2",
        )
        self.lbl_info.pack(side="left", padx=10)

        self.bind_tooltip(self.lbl_info, t("app.aae_tooltip"))

        # 5.6 Language Selection (Placeholder)
        self.lang_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.lang_frame.grid(
            row=8, column=0, columnspan=3, padx=30, pady=(5, 5), sticky="w"
        )

        self.lbl_lang = ctk.CTkLabel(
            self.lang_frame,
            text=t("app.lang_label"),
            font=(T_FONT_NAME, 14),
            text_color=T_DIM,
        )
        self.lbl_lang.pack(side="left", padx=(0, 5))

        self.combo_lang = ctk.CTkComboBox(
            self.lang_frame,
            values=["Українська", "English"],
            width=115,
            height=28,
            font=(T_FONT_NAME, 14),
            fg_color=T_BG,
            border_width=0,
            button_color=T_BG,
            text_color=T_DIM,
            dropdown_font=(T_FONT_NAME, 14),
            corner_radius=0,
        )
        current_lang_full = "English" if get_lang() == "en" else "Українська"
        self.combo_lang.set(current_lang_full)
        self.combo_lang.configure(command=self.change_language)
        self.combo_lang.pack(side="left")

        # 5.7 Say Thanks Button (Placeholder with Prompt)
        self.say_thanks_frame = ctk.CTkFrame(
            self, fg_color="transparent", corner_radius=0
        )
        self.say_thanks_frame.grid(row=9, column=0, padx=30, pady=(5, 20), sticky="w")

        self.lbl_prompt = ctk.CTkLabel(
            self.say_thanks_frame,
            text=">",
            font=(T_FONT_NAME, 16, "bold"),
            text_color=T_GREEN,
        )
        self.lbl_prompt.pack(side="left", padx=(0, 5))

        self.btn_say_thanks = ctk.CTkButton(
            self.say_thanks_frame,
            text=t("app.support_btn"),
            width=220,
            height=30,
            font=(T_FONT_NAME, 14, "bold"),
            fg_color="transparent",
            border_width=0,
            text_color=T_GREEN,
            hover_color=T_DARK,
            corner_radius=0,
            command=self.open_say_thanks,
        )
        self.btn_say_thanks.pack(side="left")

        # Signature
        self.lbl_signature = ctk.CTkLabel(
            self,
            text=t("app.signature"),
            font=(T_FONT_NAME, 14, "bold"),
            text_color=T_GREEN,
        )
        self.lbl_signature.grid(row=9, column=1, pady=(0, 10))

        # 6. Action Buttons (Resized and moved to right)
        self.btn_frame_actions = ctk.CTkFrame(
            self, fg_color="transparent", corner_radius=0
        )
        self.btn_frame_actions.grid(row=9, column=2, padx=30, pady=(0, 20), sticky="e")

        self.btn_start = ctk.CTkButton(
            self.btn_frame_actions,
            text=t("app.start_btn"),
            width=200,
            height=35,
            font=(T_FONT_NAME, 14, "bold"),
            fg_color="transparent",
            border_width=0,
            text_color=T_GREEN,
            hover_color=T_DARK,
            corner_radius=0,
            command=self.start_copy,
        )
        self.btn_start.pack(side="left", padx=(0, 10))

        self.btn_stop = ctk.CTkButton(
            self.btn_frame_actions,
            text=t("app.stop_btn"),
            width=120,
            height=35,
            font=(T_FONT_NAME, 14, "bold"),
            fg_color="transparent",
            border_width=0,
            text_color=T_RED,
            hover_color="#3b0000",
            state="disabled",
            corner_radius=0,
            command=self.stop_copy,
        )
        self.btn_stop.pack(side="left")

        # Refresh devices on start
        self.after(500, self.refresh_devices)

        # Start animations
        self.animate_say_thanks()
        self.animate_signature()
        self.animate_support_button()

        # Config & i18n initialization
        try:
            self.app_config = AppConfig.load()
        except Exception:
            self.app_config = AppConfig(dest_root=None)

        add_listener(self.rebuild_texts)

        if self.app_config and self.app_config.language != "auto":
            set_lang(self.app_config.language)
        else:
            # Refresh devices to ensure initial translation is applied
            self.refresh_devices()

        # Start update check in background
        self.after(2000, self._start_update_check)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        if self.app_state.is_copying or self.app_state.is_scanning:
            self.stop_copy()
            self.after(500, self.destroy)
        else:
            self.destroy()

    def _start_update_check(self):
        def check():
            update_info = check_for_updates(APP_VERSION, GITHUB_REPO)
            if update_info:
                self.update_info_data = update_info
                self.after(0, lambda: self.btn_update_indicator.grid())
                self.after(
                    0,
                    lambda: UpdateDialog(
                        self,
                        new_version=update_info["version"],
                        current_version=APP_VERSION,
                        download_url=update_info["url"],
                    ),
                )

        threading.Thread(target=check, daemon=True).start()

    def open_update_dialog_manual(self):
        if self.update_info_data:
            UpdateDialog(
                self,
                new_version=self.update_info_data["version"],
                current_version=APP_VERSION,
                download_url=self.update_info_data["url"],
            )

    def _center_window(self):
        """Centers the window on the screen."""
        self.update_idletasks()
        width = 925
        height = 600
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def open_say_thanks(self):
        SayThanksWindow(self)

    def change_language(self, choice: str) -> None:
        """Changes the UI language and saves it to config.

        Args:
            choice: The selected language name (e.g., 'English', 'Українська').
        """
        new_lang = "en" if choice == "English" else "uk"
        set_lang(new_lang)
        if self.app_config:
            self.app_config.language = new_lang
            self.app_config.save()

    def rebuild_texts(self):
        self.lbl_header.configure(text=t("app.title"))
        self.lbl_device.configure(text=t("app.device_label"))
        self.btn_refresh.configure(text=t("app.refresh_btn"))
        self.lbl_source.configure(text=t("app.source_label"))
        self.entry_source.configure(placeholder_text=t("app.wait_input"))
        self.btn_browse_source.configure(text=t("app.browse_btn"))
        self.lbl_dest.configure(text=t("app.dest_label"))
        self.entry_dest.configure(placeholder_text=t("app.wait_input"))
        self.btn_browse.configure(text=t("app.select_btn"))
        self.lbl_eta.configure(text=t("app.waiting"))
        self.lbl_progress.configure(text=t("app.ready"))
        self.chk_skip_aae.configure(text=t("app.skip_aae"))
        self.bind_tooltip(self.lbl_info, t("app.aae_tooltip"))
        self.lbl_lang.configure(text=t("app.lang_label"))
        self.btn_say_thanks.configure(text=t("app.support_btn"))
        self.lbl_signature.configure(text=t("app.signature"))
        self.btn_start.configure(text=t("app.start_btn"))
        self.btn_stop.configure(text=t("app.stop_btn"))

        if self.btn_update_indicator:
            self.btn_update_indicator.configure(text=t("app.update_indicator"))

        if hasattr(self, 'btn_share'):
            self.btn_share.configure(text=t("app.share_btn"))

        # Update combo values
        self.combo_lang.configure(values=["Українська", "English"])
        current_lang_full = "English" if get_lang() == "en" else "Українська"
        self.combo_lang.set(current_lang_full)

        # Refresh device list to update "No devices found" if present
        self.refresh_devices()

    def share_app(self) -> None:
        """Copies the GitHub repository link to clipboard and shows a visual confirmation."""
        self.clipboard_clear()
        self.clipboard_append(GITHUB_URL)
        
        self.btn_share.configure(text=t("app.share_copied"))
        
        def reset():
            try:
                self.btn_share.configure(text=t("app.share_btn"))
            except Exception:
                pass
                
        self.after(2000, reset)

    def refresh_devices(self):
        def scan():
            MTPDeviceRegistry.refresh_shell_cache()

            devices = MTPDeviceRegistry.list_available_devices()

            if not devices:
                devices = [t("app.no_devices")]
            self.after(0, lambda: self._apply_device_list(devices))

        threading.Thread(target=scan, daemon=True).start()

    def _apply_device_list(self, devices: list[str]) -> None:
        self.combo_device.configure(values=devices)
        if devices and devices[0] != t("app.no_devices"):
            self.combo_device.set(devices[0])
        else:
            self.combo_device.set(t("app.no_devices"))

    def browse_iphone(self) -> None:
        """Opens a dialog to browse and select source folders on the connected device."""
        device_name = self.combo_device.get().strip()
        if device_name == t("app.no_devices"):
            self.log_message("ERROR", t("app.err_no_device"))
            return

        DeviceFolderBrowser(self, device_name, self.on_iphone_folder_selected)

    def on_iphone_folder_selected(self, paths):
        self.entry_source.delete(0, "end")
        self.entry_source.insert(0, ", ".join(paths))

    def browse_dest(self) -> None:
        """Opens a folder selection dialog for the destination directory."""
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.entry_dest.delete(0, "end")
            self.entry_dest.insert(0, folder_selected)

    def log_message(
        self, level: str, msg: str, msg_type: MessageType = MessageType.GENERAL
    ) -> None:
        """Appends a formatted message to the UI log area.

        Args:
            level: The severity level ('INFO', 'WARNING', 'ERROR').
            msg: The message text to display.
            msg_type: Type of message.
        """

        def update_textbox():
            try:
                time_str = datetime.now().strftime("%H%M:%S")
                # RobCo style prefixes
                pfx = "> "
                if level == "ERROR":
                    pfx = "> [! ERR !] "
                elif level == "WARNING":
                    pfx = "> [? WRN ?] "

                full_msg = f"{pfx}{time_str} {msg.upper()}"

                is_progress = msg_type == MessageType.PROGRESS
                is_scanning = msg_type == MessageType.SCANNING

                if (is_progress and self.app_state.last_log_was_progress) or (
                    is_scanning and self.app_state.last_log_was_scanning
                ):
                    try:
                        self.textbox.delete("end-2l", "end-1l")
                    except Exception:
                        pass

                self.textbox.insert("end", f"{full_msg}\n")
                self.textbox.see("end")

                self.app_state.last_log_was_progress = is_progress
                self.app_state.last_log_was_scanning = is_scanning

                # Стабілізація: не оновлюємо статус-рядок логами сканування,
                # щоб не перебивати детальний статус із лічильником файлів
                if is_scanning:
                    return

                self.lbl_progress.configure(text=f"> {msg.upper()}")
            except Exception as e:
                import logging

                logging.getLogger(__name__).error(f"UI Log Error: {e}")

        self.after(0, update_textbox)

    def on_scan_progress(
        self, current: int, total: int, file_count: int = 0, aae_count: int = 0
    ):
        self.app_state.scan_current = current
        self.app_state.scan_total = total
        self.app_state.scan_files_found = file_count
        self.app_state.scan_aae_skipped = aae_count

        def update_ui():
            if total > 0:
                self.progressbar.set(current / total)

            elapsed = 0
            if self.app_state.start_time:
                elapsed = int(
                    (datetime.now() - self.app_state.start_time).total_seconds()
                )
            time_str = format_elapsed(elapsed)

            aae_text = (
                f" | AAE: {self.app_state.scan_aae_skipped}"
                if self.app_state.scan_aae_skipped > 0
                else ""
            )
            status_text = t(
                "app.status.scanning",
                time=time_str,
                current=current,
                total=total,
                found=self.app_state.scan_files_found,
                aae=aae_text,
            )
            self.lbl_progress.configure(text=status_text)

            if self.app_state.start_time and current > 0:
                elapsed_float = (
                    datetime.now() - self.app_state.start_time
                ).total_seconds()
                eta_sec = calculate_eta(current, total, elapsed_float)
                if eta_sec > 0:
                    eta_text = (
                        t("app.eta.min", val=eta_sec // 60)
                        if eta_sec > 60
                        else t("app.eta.sec", val=eta_sec)
                    )
                    self.lbl_eta.configure(text=t("app.status.remaining", eta=eta_text))

        self.after(0, update_ui)

    def _update_ui_timers(self):
        """Cyclic update for timers to show the app is alive."""
        if not self.app_state.is_scanning and not self.app_state.is_copying:
            return

        if self.app_state.is_scanning:
            elapsed = 0
            if self.app_state.start_time:
                elapsed = int(
                    (datetime.now() - self.app_state.start_time).total_seconds()
                )
            time_str = format_elapsed(elapsed)

            # Update status label
            aae_text = (
                f" | AAE: {self.app_state.scan_aae_skipped}"
                if self.app_state.scan_aae_skipped > 0
                else ""
            )
            status_text = t(
                "app.status.scanning",
                time=time_str,
                current=self.app_state.scan_current,
                total=self.app_state.scan_total,
                found=self.app_state.scan_files_found,
                aae=aae_text,
            )
            self.lbl_progress.configure(text=status_text)

            # Update log with heartbeat
            self.log_message(
                "INFO", t("app.log.scanning") + f" [{time_str}]", MessageType.SCANNING
            )

        elif self.app_state.is_copying:
            elapsed = 0
            if self.app_state.copy_start_time:
                elapsed = int(
                    (datetime.now() - self.app_state.copy_start_time).total_seconds()
                )
            time_str = format_elapsed(elapsed)

            # Update status label
            status_text = t(
                "app.status.progress",
                time=time_str,
                current=self.app_state.copy_current,
                total=self.app_state.copy_total,
                copied_size=format_size(self.app_state.copy_copied_bytes),
                total_size=format_size(self.app_state.copy_total_bytes),
            )
            self.lbl_progress.configure(text=status_text)

        # Schedule next update
        self.after(1000, self._update_ui_timers)

    def update_progress(self, info: ProgressInfo):
        self.app_state.is_scanning = False
        if not self.app_state.is_copying:
            self.app_state.is_copying = True
            self.app_state.copy_start_time = datetime.now()
            self.after(1000, self._update_ui_timers)

        self.app_state.copy_current = info.current_file
        self.app_state.copy_total = info.total_files
        self.app_state.copy_copied_bytes = info.copied_bytes
        self.app_state.copy_total_bytes = info.total_bytes

        def update_ui():
            if info.total_files > 0:
                self.progressbar.set(info.current_file / info.total_files)

            elapsed = 0
            if self.app_state.copy_start_time:
                elapsed = int(
                    (datetime.now() - self.app_state.copy_start_time).total_seconds()
                )
            time_str = format_elapsed(elapsed)

            status_text = t(
                "app.status.progress",
                time=time_str,
                current=info.current_file,
                total=info.total_files,
                copied_size=format_size(info.copied_bytes),
                total_size=format_size(info.total_bytes),
            )
            self.lbl_progress.configure(text=status_text)

            if self.app_state.copy_start_time:
                elapsed_float = (
                    datetime.now() - self.app_state.copy_start_time
                ).total_seconds()
                eta_sec = calculate_eta(
                    info.current_file, info.total_files, elapsed_float
                )
                if eta_sec > 0:
                    eta_text = (
                        t("app.eta.full", m=eta_sec // 60, s=eta_sec % 60)
                        if eta_sec > 60
                        else t("app.eta.sec", val=eta_sec)
                    )
                    if info.current_file >= info.total_files:
                        eta_text = t("app.status.finalizing")
                    self.lbl_eta.configure(text=t("app.status.remaining", eta=eta_text))

        self.after(0, update_ui)

    def on_finish(self, files: int, bytes_copied: int, skipped: int):
        def update_ui():
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.progressbar.set(1.0)
            size_str = format_size(bytes_copied)
            self.lbl_progress.configure(
                text=t("app.status.finished", size=size_str), text_color=T_GREEN
            )
            self.lbl_eta.configure(text=t("app.status.done"))
            self.app_state.copy_start_time = None
            self.app_state.is_scanning = False
            self.app_state.is_copying = False

        self.after(0, update_ui)

    def on_error(self, error: Exception):
        def update_ui():
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.lbl_progress.configure(text=t("app.status.error"), text_color=T_RED)
            self.app_state.is_scanning = False
            self.app_state.is_copying = False

        self.after(0, update_ui)

    def start_copy(self) -> None:
        """Validates inputs and starts the copy process in a background thread."""
        device_name = self.combo_device.get().strip()
        source_text = self.entry_source.get().strip()
        dest_folder = self.entry_dest.get().strip()

        if (
            not source_text
            or not dest_folder
            or device_name.lower() == t("app.no_devices").lower()
        ):
            self.log_message("ERROR", t("app.err_no_folders"))
            return

        from pathlib import Path

        try:
            dest_path = Path(dest_folder).resolve()
            check_path = dest_path
            while not check_path.exists() and check_path.parent != check_path:
                check_path = check_path.parent
            if not os.access(check_path, os.W_OK):
                self.log_message("ERROR", "Destination path is not writable.")
                return
        except Exception as e:
            self.log_message("ERROR", f"Invalid destination path: {e}")
            return

        source_folders = [s.strip() for s in source_text.split(",") if s.strip()]

        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.progressbar.set(0)
        self.textbox.delete("1.0", "end")
        self.app_state.start_time = datetime.now()
        self.app_state.scan_current = 0
        self.app_state.scan_total = len(source_folders)
        self.app_state.scan_files_found = 0
        self.app_state.scan_aae_skipped = 0
        self.app_state.is_scanning = True
        self.lbl_eta.configure(text=t("app.status.analyzing"))

        # Start the "alive" timer for scanning
        self.after(1000, self._update_ui_timers)

        try:
            config = AppConfig.load(
                dest_root=dest_folder,
                device_name=device_name,
                source_folders=source_folders,
                skip_aae=self.chk_skip_aae.get() == 1,
            )
        except Exception as e:
            self.log_message("ERROR", t("app.log.config_error", err=str(e)))
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            return

        setup_logging(config.log_path, config.log_level)

        self.runner = CopierRunner(config)
        self.runner.on_log = lambda l, m, t: self.log_message(l, m, t)
        self.runner.on_scan_progress = self.on_scan_progress
        self.runner.on_progress = self.update_progress
        self.runner.on_finish = self.on_finish
        self.runner.on_error = self.on_error
        self.runner.on_cancel = self.on_copy_cancelled

        self.copy_thread = threading.Thread(target=self.runner.run, daemon=True)
        self.copy_thread.start()

    def stop_copy(self) -> None:
        """Requests the current copy runner to cancel the operation gracefully."""
        if self.runner:
            self.log_message("WARNING", t("app.log.stop_request"))
            self.runner.request_cancel()
            self.btn_stop.configure(state="disabled")
            self.lbl_progress.configure(text=t("app.status.stopping"), text_color=T_DIM)
            self.lbl_eta.configure(text=t("app.status.stop_processing"))
            self.app_state.copy_start_time = None

    def on_copy_cancelled(self):
        """Called by the runner when the copy loop exits due to user cancellation."""

        def update_ui():
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.lbl_progress.configure(
                text=t("app.status.cancelled"), text_color=T_DIM
            )
            self.lbl_eta.configure(text=t("app.status.cancelled_eta"))
            self.app_state.is_scanning = False
            self.app_state.is_copying = False

        self.after(0, update_ui)
