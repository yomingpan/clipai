from __future__ import annotations

import tkinter as tk
from tkinter import messagebox


def confirm_retained_data_uninstall(product: str) -> bool:
    root = tk.Tk()
    root.withdraw()
    try:
        return messagebox.askyesno(product, f"移除 {product}？\n\nAPI key、設定及資料會保留。\n請先從 Tray 退出 ClipAI。", parent=root)
    finally:
        root.destroy()


def show_maintenance_result(product: str, *, success: bool, error_code: str = "") -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        if success:
            messagebox.showinfo(product, "已移除程式，設定與資料已保留。", parent=root)
        else:
            detail = ("ClipAI 仍在執行。請從 Tray 選 Exit，關閉 ClipAI 視窗後重試。"
                      if error_code == "InstallationBusyError"
                      else "請先退出 ClipAI，再用同一個 Setup 的移除選項重試。\n\n" + error_code)
            messagebox.showerror(product, "未完成移除。\n\n" + detail, parent=root)
    finally:
        root.destroy()
