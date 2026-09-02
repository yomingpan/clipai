from __future__ import annotations

from collections.abc import Callable
import tkinter as tk

import customtkinter as ctk

from ClipAI.core.commands import CloseAbout, OpenGitHub
from ClipAI.ui.tray import create_tray_image
from ClipAI.ui.window_icons import CUSTOMTKINTER_ICON_DELAY_MS, install_clipai_window_icons


class AboutDialog:
    """Static application information surface."""

    def __init__(self, master, command_sink: Callable[[object], None], native_window_surface, *, version: str, github_url: str) -> None:
        self._command_sink = command_sink
        self._native_window_surface = native_window_surface
        self._window_icon_handles: tuple[int, ...] = ()
        self._window = ctk.CTkToplevel(master)
        self._window.title("About ClipAI")
        self._window.geometry("760x650")
        self._window.minsize(680, 580)
        self._window.protocol("WM_DELETE_WINDOW", self._request_close)
        self._window.bind("<Escape>", lambda _event: self._request_close())
        self._window.grid_columnconfigure(1, weight=1)
        self._window.grid_rowconfigure(10, weight=1)
        heading_font = ctk.CTkFont(family="Microsoft JhengHei", size=16, weight="bold")
        body_font = ctk.CTkFont(family="Microsoft JhengHei", size=13)
        title_font = ctk.CTkFont(family="Microsoft JhengHei", size=26, weight="bold")
        icon = ctk.CTkImage(
            light_image=create_tray_image(size=128),
            dark_image=create_tray_image(size=128),
            size=(128, 128),
        )
        ctk.CTkLabel(self._window, image=icon, text="").grid(
            row=0, column=0, rowspan=5, padx=(28, 24), pady=28, sticky="n"
        )
        ctk.CTkLabel(
            self._window, text="ClipAI", anchor="w", font=title_font
        ).grid(row=0, column=1, padx=(0, 28), pady=(30, 2), sticky="ew")
        details = ctk.CTkFrame(self._window, fg_color=("#F5F7FA", "#2B2B2B"), corner_radius=8)
        details.grid(row=1, column=1, rowspan=3, padx=(0, 28), pady=(12, 2), sticky="ew")
        details.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(details, text=f"版本：{version}", anchor="w", font=body_font).grid(
            row=0, column=0, columnspan=2, padx=14, pady=(10, 1), sticky="ew"
        )
        ctk.CTkLabel(details, text="建議 Python：3.12.x（支援 3.10–3.13）", anchor="w", font=body_font).grid(
            row=1, column=0, columnspan=2, padx=14, pady=1, sticky="ew"
        )
        ctk.CTkLabel(details, text="平台：Windows 11 開發", anchor="w", font=body_font).grid(
            row=2, column=0, padx=14, pady=1, sticky="w"
        )
        self._github_button = ctk.CTkButton(
            details,
            text=f"GitHub：{github_url}",
            command=lambda: self._command_sink(OpenGitHub(github_url)),
            fg_color="transparent",
            text_color=("#0969DA", "#58A6FF"),
            hover_color=("#E8F1FB", "#1F3B56"),
            font=ctk.CTkFont(underline=True),
            border_width=0,
            anchor="w",
            height=24,
        )
        self._github_button.grid(row=2, column=1, padx=(10, 8), pady=1, sticky="w")
        ctk.CTkFrame(details, height=8, fg_color="transparent").grid(row=3, column=0, columnspan=2)
        ctk.CTkLabel(
            self._window,
            text="核心理念",
            anchor="w",
            font=heading_font,
        ).grid(row=4, column=1, padx=(0, 28), pady=(22, 0), sticky="ew")
        ctk.CTkLabel(
            self._window,
            text="把阻力交給 AI，把方向留給人。",
            anchor="w",
            font=body_font,
        ).grid(row=5, column=1, padx=(0, 28), pady=(4, 0), sticky="ew")
        ctk.CTkLabel(
            self._window,
            text="使用方式",
            anchor="w",
            font=heading_font,
        ).grid(row=6, column=1, padx=(0, 28), pady=(20, 0), sticky="ew")
        ctk.CTkLabel(
            self._window,
            text=(
                "• 新手入門：長按 Alt 500 毫秒呼叫統一入口，從這裡開始體驗。\n"
                "• 進階使用：參考系統匣上的 Keyboard Shortcuts，查看完整快捷鍵。\n"
                "• 提醒：部分軟體可能有按鍵衝突，請避開衝突快捷鍵；\n"
                "  快捷鍵仍是最快速、最絲滑的 AI 互動方式。"
            ),
            anchor="w",
            justify="left",
            font=body_font,
            wraplength=520,
        ).grid(row=7, column=1, padx=(0, 28), pady=(4, 0), sticky="new")
        ctk.CTkLabel(
            self._window,
            text="隱私與資料處理",
            anchor="w",
            font=heading_font,
        ).grid(row=8, column=1, padx=(0, 28), pady=(20, 0), sticky="ew")
        ctk.CTkLabel(
            self._window,
            text=(
                "開源軟體資料使用依方案而定：付費方案通常不訓練模型，開源版本則可能，請務必確認條款。\n"
                "聲音輸入輸出依賴瀏覽器，隱私保護受瀏覽器條款規範。"
            ),
            anchor="w",
            justify="left",
            font=body_font,
            wraplength=520,
        ).grid(row=9, column=1, padx=(0, 28), pady=(4, 0), sticky="new")
        buttons = ctk.CTkFrame(self._window, fg_color="transparent")
        buttons.grid(row=10, column=1, padx=(0, 28), pady=(22, 26), sticky="se")
        self._update_button = ctk.CTkButton(buttons, text="檢查更新（尚未提供）", state="disabled", width=170)
        self._update_button.grid(row=0, column=0, padx=(0, 10))
        ctk.CTkButton(buttons, text="關閉", command=self._request_close, width=100).grid(row=0, column=1)
        self._window.after(CUSTOMTKINTER_ICON_DELAY_MS, self._apply_window_icons)

    def _request_close(self) -> None:
        self._command_sink(CloseAbout())

    def close(self) -> None:
        if self._window.winfo_exists():
            self._window.destroy()

    def _apply_window_icons(self) -> None:
        try:
            self._window_icon_handles = install_clipai_window_icons(self._window, self._native_window_surface)
        except (OSError, tk.TclError):
            pass
