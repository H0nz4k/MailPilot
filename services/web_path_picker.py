"""Local native file chooser for the Windows DataShip application."""
from __future__ import annotations

import sys
from pathlib import Path


def pick_local_file(initial: str, *, kind: str) -> str | None:
    if kind not in ("nssm", "dashboard"):
        raise ValueError("Neznámý typ souboru.")
    if sys.platform == "win32":
        return _pick_windows_file(initial, kind=kind)
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        try:
            root.wm_attributes("-topmost", True)
            value = filedialog.askopenfilename(
                title="Vyberte nssm.exe" if kind == "nssm" else "Vyberte šablonu dashboardu",
                initialdir=str(Path(initial).expanduser().parent),
                filetypes=[("NSSM", "nssm.exe"), ("Všechny soubory", "*")]
                if kind == "nssm" else [("HTML soubory", "*.html *.htm"), ("Všechny soubory", "*")],
            )
            return str(value) if value else None
        finally:
            root.destroy()
    except Exception as exc:
        raise ValueError("Výběr souboru není dostupný. Cestu zadejte ručně.") from exc


def _pick_windows_file(initial: str, *, kind: str) -> str | None:
    import ctypes
    from ctypes import wintypes

    class OpenFileName(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD), ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE), ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR), ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD), ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD), ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD), ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR), ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD), ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR), ("lCustData", wintypes.LPARAM),
            ("lpfnHook", ctypes.c_void_p), ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", ctypes.c_void_p), ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    path = Path(initial).expanduser()
    buffer = ctypes.create_unicode_buffer(32768)
    buffer.value = path.name if not path.is_dir() else ""
    dialog = OpenFileName()
    dialog.lStructSize = ctypes.sizeof(OpenFileName)
    ctypes.windll.user32.GetForegroundWindow.restype = wintypes.HWND
    dialog.hwndOwner = ctypes.windll.user32.GetForegroundWindow()
    dialog.lpstrFile = ctypes.cast(buffer, wintypes.LPWSTR)
    dialog.nMaxFile = len(buffer)
    dialog.lpstrInitialDir = str(path if path.is_dir() else path.parent)
    dialog.lpstrTitle = "Vyberte nssm.exe" if kind == "nssm" else "Vyberte šablonu dashboardu"
    dialog.lpstrFilter = ("NSSM (nssm.exe)\0nssm.exe\0Všechny soubory\0*.*\0\0" if kind == "nssm"
                         else "HTML soubory\0*.html;*.htm\0Všechny soubory\0*.*\0\0")
    dialog.nFilterIndex = 1
    dialog.Flags = 0x00080000 | 0x00001000 | 0x00000800 | 0x00000008  # Explorer, existing file/path, no cwd change
    choose = ctypes.windll.comdlg32.GetOpenFileNameW
    choose.argtypes = [ctypes.POINTER(OpenFileName)]
    choose.restype = wintypes.BOOL
    if choose(ctypes.byref(dialog)):
        return buffer.value
    error = ctypes.windll.comdlg32.CommDlgExtendedError()
    if error:
        raise ValueError(f"Dialog výběru souboru se nepodařilo otevřít (Windows {error}). Cestu zadejte ručně.")
    return None
