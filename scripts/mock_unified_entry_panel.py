"""Throwaway UI prototype for the unified ClipAI side panel.

Question: which information hierarchy best helps a user discover the three
ClipAI intentions while preserving a fast keyboard path?

This file is intentionally disconnected from the application runtime.
"""

from __future__ import annotations

import customtkinter as ctk


BG = "#17191C"
PANEL = "#2B2B2B"
SURFACE = "#36393D"
SURFACE_HOVER = "#42474D"
TEXT = "#F0F3F6"
MUTED = "#AAB4BF"
FAINT = "#727C86"
BLUE = "#1F6AA5"
BLUE_HOVER = "#2879B8"
GREEN = "#236B38"


SCENES: dict[str, tuple[str, tuple[dict[str, str], ...]]] = {
    "看懂": (
        "把內容變成你真正理解的東西",
        (
            {"icon": "◎", "title": "English Companion", "desc": "讀懂英文、學會怎麼說", "key": "1"},
            {"icon": "◌", "title": "讀懂這段", "desc": "用簡單方式說清楚", "key": "2"},
            {"icon": "文", "title": "翻譯成繁體中文", "desc": "保留原意，轉成自然中文", "key": "3"},
            {"icon": "#", "title": "抽取核心關鍵字", "desc": "快速抓住內容骨架", "key": "4"},
        ),
    ),
    "寫得出": (
        "把腦中的意思變成可以使用的文字",
        (
            {"icon": "✦", "title": "Capture an Expression", "desc": "找出可直接使用的表達", "key": "1"},
            {"icon": "↗", "title": "私下口吻改寫", "desc": "改成自然、像你會說的話", "key": "2"},
            {"icon": "≡", "title": "縮短內容", "desc": "保留意思，讓文字更俐落", "key": "3"},
            {"icon": "T", "title": "語音成稿編輯器", "desc": "把口語整理成可用文字", "key": "4"},
        ),
    ),
    "想清楚": (
        "把模糊的感覺變成可以判斷的結構",
        (
            {"icon": "◇", "title": "概念命名", "desc": "校準概念邊界，再找到名稱", "key": "1"},
            {"icon": "?", "title": "提出一個值得思考的問題", "desc": "推進下一層判斷", "key": "2"},
            {"icon": "→", "title": "最小行動", "desc": "把想法落成下一步", "key": "3"},
            {"icon": "△", "title": "權衡透視", "desc": "看見選擇背後的代價", "key": "4"},
        ),
    ),
}

RECENT = (
    {"icon": "◎", "title": "English Companion", "desc": "剛剛使用", "key": "1", "scene": "看懂"},
    {"icon": "✦", "title": "Capture an Expression", "desc": "昨天使用", "key": "1", "scene": "寫得出"},
    {"icon": "?", "title": "提出一個值得思考的問題", "desc": "最近使用", "key": "2", "scene": "想清楚"},
)


class MockUnifiedEntryPanel:
    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("ClipAI Unified Entry · UI Mock")
        self.root.geometry("1240x760+40+40")
        self.root.minsize(1060, 680)
        self.root.configure(fg_color=BG)
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))

        self.variant = "A"
        self.scene = "看懂"
        self.query = ""
        self._build_host()
        self._build_panel()
        self._build_switcher()
        self._render()
        self.root.deiconify()
        self.root.update_idletasks()
        self.root.lift()
        self.root.focus_force()

    def _build_host(self) -> None:
        host = ctk.CTkFrame(self.root, fg_color=BG)
        host.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            host,
            text="ClipAI",
            text_color="#5E6872",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).place(relx=0.08, rely=0.08)
        ctk.CTkLabel(
            host,
            text="工作區預覽 · 這裡代表使用者原本正在看的內容",
            text_color="#48515A",
            font=ctk.CTkFont(size=13),
        ).place(relx=0.08, rely=0.15)

        canvas = ctk.CTkFrame(host, fg_color="#202328", corner_radius=16)
        canvas.place(relx=0.08, rely=0.25, relwidth=0.78, relheight=0.58)
        ctk.CTkLabel(
            canvas,
            text="Select a sentence, press the ClipAI shortcut, and continue thinking.",
            text_color="#68737D",
            font=ctk.CTkFont(size=17),
            wraplength=560,
            justify="left",
        ).place(relx=0.08, rely=0.16)
        ctk.CTkLabel(
            canvas,
            text=(
                "The goal is not to make every decision for you.\n"
                "It is to reduce the friction between noticing something\n"
                "and knowing what to do with it."
            ),
            text_color="#3F4850",
            font=ctk.CTkFont(size=15),
            wraplength=560,
            justify="left",
        ).place(relx=0.08, rely=0.29)
        ctk.CTkLabel(
            canvas,
            text="MOCK HOST SURFACE",
            text_color="#35404A",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).place(relx=0.08, rely=0.88)

    def _build_panel(self) -> None:
        self.panel = ctk.CTkFrame(self.root, width=390, fg_color=PANEL, corner_radius=0)
        self.panel.pack(side="right", fill="y")
        self.panel.pack_propagate(False)
        self.panel.grid_columnconfigure(0, weight=1)
        self.panel.grid_rowconfigure(4, weight=1)

        header = ctk.CTkFrame(self.panel, fg_color="transparent")
        header.grid(row=0, column=0, padx=22, pady=(23, 14), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="ClipAI", text_color=TEXT, anchor="w", font=ctk.CTkFont(size=21, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text="統一入口", text_color=FAINT, anchor="e", font=ctk.CTkFont(size=12)).grid(row=0, column=1, sticky="e")
        ctk.CTkButton(header, text="×", width=28, height=28, fg_color="transparent", hover_color=SURFACE, text_color=MUTED, command=self.root.destroy).grid(row=0, column=2, padx=(12, 0))

        self.search = ctk.CTkEntry(
            self.panel,
            height=38,
            placeholder_text="找功能或輸入意圖...",
            border_width=1,
            border_color="#4A5056",
            fg_color="#222528",
            text_color=TEXT,
        )
        self.search.grid(row=1, column=0, padx=22, sticky="ew")
        self.search.bind("<KeyRelease>", lambda _event: self._on_search())

        self.status = ctk.CTkLabel(self.panel, text="Mock · 只展示 UI，不會執行 Action", text_color=FAINT, anchor="w", font=ctk.CTkFont(size=11))
        self.status.grid(row=2, column=0, padx=24, pady=(8, 3), sticky="ew")

        self.content = ctk.CTkScrollableFrame(self.panel, fg_color="transparent", scrollbar_button_color="#4B535B", scrollbar_button_hover_color="#64717B")
        self.content.grid(row=4, column=0, padx=14, pady=(3, 8), sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)

        self.footer = ctk.CTkFrame(self.panel, fg_color="#25282B", corner_radius=0, height=57)
        self.footer.grid(row=5, column=0, sticky="ew")
        self.footer.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.footer, text="按住 Ctrl + Alt，再按功能鍵", text_color=MUTED, anchor="w", font=ctk.CTkFont(size=11)).grid(row=0, column=0, padx=22, pady=(11, 0), sticky="w")
        ctk.CTkLabel(self.footer, text="更多功能   ·   快捷鍵設定", text_color=FAINT, anchor="w", font=ctk.CTkFont(size=10)).grid(row=1, column=0, padx=22, pady=(1, 10), sticky="w")

    def _build_switcher(self) -> None:
        bar = ctk.CTkFrame(self.root, fg_color="#111315", corner_radius=18, border_width=1, border_color="#353A3F")
        bar.place(relx=0.43, rely=0.93, anchor="center")
        ctk.CTkButton(bar, text="‹", width=35, height=30, fg_color="transparent", hover_color=SURFACE, command=lambda: self._change_variant(-1)).pack(side="left", padx=(4, 0), pady=4)
        self.variant_label = ctk.CTkLabel(bar, text="A · 意圖優先", width=160, text_color=TEXT, font=ctk.CTkFont(size=12, weight="bold"))
        self.variant_label.pack(side="left", padx=5)
        ctk.CTkButton(bar, text="›", width=35, height=30, fg_color="transparent", hover_color=SURFACE, command=lambda: self._change_variant(1)).pack(side="left", padx=(0, 4), pady=4)
        self.root.bind("<Left>", lambda _event: self._change_variant(-1))
        self.root.bind("<Right>", lambda _event: self._change_variant(1))

    def _clear_content(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def _section_label(self, text: str, *, muted: bool = False) -> None:
        ctk.CTkLabel(self.content, text=text, text_color=FAINT if muted else MUTED, anchor="w", font=ctk.CTkFont(size=11, weight="bold")).pack(fill="x", padx=9, pady=(12, 6))

    def _action_row(self, action: dict[str, str], *, selected: bool = False) -> None:
        row = ctk.CTkFrame(self.content, fg_color=BLUE if selected else SURFACE, corner_radius=10)
        row.pack(fill="x", padx=5, pady=3)
        row.bind("<Button-1>", lambda _event, title=action["title"]: self._choose_action(title))

        icon = ctk.CTkLabel(row, text=action["icon"], width=27, text_color="#BFDFFF" if selected else "#8DA8BC", font=ctk.CTkFont(size=16, weight="bold"))
        icon.pack(side="left", padx=(12, 4), pady=10)
        copy = ctk.CTkFrame(row, fg_color="transparent")
        copy.pack(side="left", fill="x", expand=True, pady=9)
        ctk.CTkLabel(copy, text=action["title"], text_color=TEXT, anchor="w", font=ctk.CTkFont(size=13, weight="bold")).pack(fill="x")
        ctk.CTkLabel(copy, text=action["desc"], text_color="#C3CBD3" if selected else MUTED, anchor="w", font=ctk.CTkFont(size=11)).pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(row, text=f"{action['key']}", width=24, height=24, corner_radius=5, fg_color="#4B535B" if not selected else "#4D8BC0", text_color=TEXT, font=ctk.CTkFont(size=11, weight="bold")).pack(side="right", padx=11)

    def _tabs(self) -> None:
        tabs = ctk.CTkFrame(self.content, fg_color="transparent")
        tabs.pack(fill="x", padx=4, pady=(4, 4))
        for scene in SCENES:
            button = ctk.CTkButton(tabs, text=scene, height=32, corner_radius=7, fg_color=BLUE if scene == self.scene else "transparent", hover_color=BLUE_HOVER, text_color=TEXT if scene == self.scene else MUTED, command=lambda value=scene: self._select_scene(value))
            button.pack(side="left", expand=True, fill="x", padx=2)

    def _render(self) -> None:
        self._clear_content()
        if self.variant == "A":
            self.variant_label.configure(text="A · 意圖優先")
            self._section_label("你現在想做什麼？")
            self._tabs()
            description, actions = SCENES[self.scene]
            ctk.CTkLabel(self.content, text=description, text_color=MUTED, anchor="w", justify="left", wraplength=330, font=ctk.CTkFont(size=12)).pack(fill="x", padx=9, pady=(7, 7))
            for action in actions:
                self._action_row(action)
        elif self.variant == "B":
            self.variant_label.configure(text="B · 最近優先")
            self._section_label("最近使用")
            for action in RECENT:
                self._action_row(action)
            self._section_label("三個方向", muted=True)
            self._tabs()
            description, actions = SCENES[self.scene]
            ctk.CTkLabel(self.content, text=description, text_color=MUTED, anchor="w", wraplength=330, font=ctk.CTkFont(size=12)).pack(fill="x", padx=9, pady=(7, 7))
            for action in actions[:3]:
                self._action_row(action)
        else:
            self.variant_label.configure(text="C · 快捷鍵優先")
            self._section_label("按鍵地圖")
            ctk.CTkLabel(self.content, text="Ctrl + Alt + 1–4 直接啟動常用功能", text_color=MUTED, anchor="w", font=ctk.CTkFont(size=12)).pack(fill="x", padx=9, pady=(0, 7))
            for scene, (_description, actions) in SCENES.items():
                ctk.CTkLabel(self.content, text=scene, text_color="#8EC5FF", anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(fill="x", padx=9, pady=(10, 2))
                for action in actions[:3]:
                    self._action_row(action)

        if self.query:
            self._filter_rows()

    def _filter_rows(self) -> None:
        query = self.query.casefold()
        for row in self.content.winfo_children():
            text = " ".join(label.cget("text") for label in row.winfo_children() if isinstance(label, ctk.CTkLabel))
            if text and query not in text.casefold() and not isinstance(row, ctk.CTkFrame):
                row.pack_forget()

    def _on_search(self) -> None:
        self.query = self.search.get().strip()
        self._render()
        if self.query:
            self.status.configure(text=f"正在 mock 搜尋：{self.query}", text_color="#8EC5FF")
        else:
            self.status.configure(text="Mock · 只展示 UI，不會執行 Action", text_color=FAINT)

    def _select_scene(self, scene: str) -> None:
        self.scene = scene
        self._render()

    def _choose_action(self, title: str) -> None:
        self.status.configure(text=f"已選取：{title} · Mock 未執行", text_color="#8DE8BC")

    def _change_variant(self, delta: int) -> None:
        variants = ("A", "B", "C")
        self.variant = variants[(variants.index(self.variant) + delta) % len(variants)]
        self._render()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    MockUnifiedEntryPanel().run()
