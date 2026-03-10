from __future__ import annotations

import threading
import tkinter as tk

import customtkinter as ctk

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class PopupPresenter:
    def show_text(self, title: str, content: str) -> None:
        def _worker() -> None:
            root = ctk.CTk()
            root.withdraw()

            window = ctk.CTkToplevel(root)
            window.title(title)
            window.geometry("760x560")
            window.minsize(540, 360)
            window.configure(fg_color=("#F7F8FA", "#111318"))

            main_frame = ctk.CTkFrame(
                window,
                fg_color=("white", "#181B22"),
                corner_radius=14,
                border_width=1,
                border_color=("#D8DEE8", "#2B3240"),
            )
            main_frame.pack(fill="both", expand=True, padx=14, pady=14)

            header_frame = ctk.CTkFrame(main_frame, fg_color="transparent", height=36)
            header_frame.pack(fill="x", padx=14, pady=(14, 6))
            header_frame.pack_propagate(False)

            title_label = ctk.CTkLabel(
                header_frame,
                text="ClipAI  " + title,
                font=("Microsoft JhengHei", 12, "bold"),
                text_color="#3B8ED0",
                anchor="w",
            )
            title_label.pack(side="left", fill="y")

            hint_label = ctk.CTkLabel(
                header_frame,
                text="Esc to close",
                font=("Microsoft JhengHei", 10),
                text_color=("gray45", "gray60"),
                anchor="e",
            )
            hint_label.pack(side="right", fill="y")

            text_container = ctk.CTkFrame(
                main_frame,
                corner_radius=10,
                border_width=1,
                border_color=("#D8DEE8", "#2B3240"),
                fg_color=("#FCFCFD", "#141922"),
            )
            text_container.pack(fill="both", expand=True, padx=14, pady=(0, 10))

            text_widget = tk.Text(
                text_container,
                font=("Microsoft JhengHei", 11),
                wrap="word",
                padx=14,
                pady=14,
                borderwidth=0,
                highlightthickness=0,
                bg=window._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["fg_color"]),
                fg=window._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["text_color"]),
                insertbackground=window._apply_appearance_mode(ctk.ThemeManager.theme["CTkTextbox"]["text_color"]),
            )
            text_widget.pack(fill="both", expand=True, padx=2, pady=2)
            text_widget.insert("1.0", content)
            text_widget.config(state="disabled")

            footer_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
            footer_frame.pack(fill="x", padx=14, pady=(0, 14))

            close_button = ctk.CTkButton(
                footer_frame,
                text="Close",
                width=96,
                command=window.destroy,
                font=("Microsoft JhengHei", 12, "bold"),
                fg_color="#3B8ED0",
                hover_color="#2B6E9E",
            )
            close_button.pack(side="right")

            def _close(event=None) -> None:
                del event
                try:
                    window.destroy()
                finally:
                    root.quit()
                    root.destroy()

            window.protocol("WM_DELETE_WINDOW", _close)
            window.bind("<Escape>", _close)
            window.after(60, lambda: window.focus_force())
            window.after(100, lambda: text_widget.focus_set())
            window.lift()
            window.attributes("-topmost", True)
            window.after(300, lambda: window.attributes("-topmost", False))
            root.mainloop()

        threading.Thread(target=_worker, daemon=True).start()
