from __future__ import annotations

import tkinter as tk
from tkinter import messagebox


def choose_uninstall(product: str) -> bool | None:
    root = tk.Tk()
    root.title(product)
    root.resizable(False, False)
    delete_data = tk.BooleanVar(root, value=False)
    choice: bool | None = None
    tk.Label(root, text=f"移除 {product}\n請先從 Tray 選 Exit，關閉 ClipAI。", padx=24, pady=16).pack()
    tk.Radiobutton(root, text="移除程式，保留設定與資料（預設）", variable=delete_data, value=False).pack(anchor="w", padx=24)
    tk.Radiobutton(root, text="完整移除：刪除設定、API key 與所有 ClipAI 資料", variable=delete_data, value=True).pack(anchor="w", padx=24)
    tk.Label(root, text="包含紀錄、快取與自訂內容。刪除後無法復原。", padx=24, pady=8).pack()
    def confirm() -> None:
        nonlocal choice
        if delete_data.get() and not messagebox.askyesno(
            product, "確定永久刪除設定、API key 與所有 ClipAI 資料？\n刪除後無法復原。", default="no", parent=root):
            return
        choice = delete_data.get()
        root.destroy()
    buttons = tk.Frame(root)
    buttons.pack(pady=16)
    tk.Button(buttons, text="取消", command=root.destroy).pack(side="left", padx=8)
    tk.Button(buttons, text="移除", command=confirm).pack(side="left", padx=8)
    try:
        root.mainloop()
        return choice
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


def show_maintenance_result(product: str, *, success: bool, error_code: str = "", delete_user_data: bool = False) -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        if success:
            messagebox.showinfo(product, "已移除程式、設定、API key 與 ClipAI 資料。" if delete_user_data
                                else "已移除程式，設定與資料已保留。", parent=root)
        else:
            detail = ("ClipAI 仍在執行。請從 Tray 選 Exit，關閉 ClipAI 視窗後重試。"
                      if error_code == "InstallationBusyError"
                      else "請先退出 ClipAI，再用同一個 Setup 的移除選項重試。\n\n" + error_code)
            messagebox.showerror(product, "未完成移除。\n\n" + detail, parent=root)
    finally:
        root.destroy()
