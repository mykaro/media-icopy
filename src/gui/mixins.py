import tkinter as tk
from .constants import T_GREEN, T_BG, T_DARK, T_PANEL, T_FONT_NAME


class AnimationMixin:
    """Provides UI animation methods for the main App."""

    def animate_say_thanks(self, step=0):
        """Pulsing animation for the prompt '>' before Support button"""
        try:
            # Toggle prompt visibility (blink)
            colors = [T_GREEN, T_BG]
            idx = step % 2

            self.lbl_prompt.configure(text_color=colors[idx])

            # Blink interval: 500ms for terminal cursor effect
            self.after(500, lambda: self.animate_say_thanks(step + 1))
        except tk.TclError:
            pass

    def animate_support_button(self):
        """Flashes the support button background every 5 seconds for 1 second"""
        try:

            def flash_on():
                try:
                    self.btn_say_thanks.configure(fg_color=T_DARK)
                    self.after(1000, flash_off)
                except tk.TclError:
                    pass

            def flash_off():
                try:
                    self.btn_say_thanks.configure(fg_color="transparent")
                    self.after(4000, flash_on)
                except tk.TclError:
                    pass

            # Initial start after 5 seconds
            self.after(3000, flash_on)
        except tk.TclError:
            pass

    def animate_signature(self):
        """Typing effect for signature, restarts every 10 seconds"""
        full_text = "Developed by Mykaro"

        def type_char(idx=0):
            try:
                if idx <= len(full_text):
                    # Add terminal cursor "_" during typing
                    cursor = "_" if idx < len(full_text) else ""
                    self.lbl_signature.configure(text=full_text[:idx] + cursor)
                    self.after(100, lambda: type_char(idx + 1))
                else:
                    # Wait 10 seconds and restart
                    self.after(10000, self.animate_signature)
            except tk.TclError:
                pass

        try:
            self.lbl_signature.configure(text="")
            self.after(100, lambda: type_char(0))
        except tk.TclError:
            pass


class TooltipMixin:
    """Provides tooltip functionality for UI elements."""

    def bind_tooltip(self, widget, text):
        widget.tooltip_text = text
        if hasattr(widget, "_tooltip_bound"):
            return

        def enter(event):
            if hasattr(widget, "tooltip_text"):
                x = widget.winfo_rootx() + 25
                y = widget.winfo_rooty() + 20
                self.tw = tk.Toplevel(widget)
                self.tw.wm_overrideredirect(True)
                self.tw.wm_geometry(f"+{x}+{y}")
                self.tw.configure(bg=T_BG)
                label = tk.Label(
                    self.tw,
                    text=widget.tooltip_text,
                    justify="left",
                    background=T_PANEL,
                    foreground=T_GREEN,
                    relief="solid",
                    borderwidth=1,
                    font=(T_FONT_NAME, 12),
                )
                label.pack(ipadx=5, ipady=5)

        def leave(event):
            if hasattr(self, "tw") and self.tw:
                self.tw.destroy()
                self.tw = None

        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)
        widget._tooltip_bound = True
