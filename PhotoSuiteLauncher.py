# -*- coding: utf-8 -*-
"""
PhotoSuiteLauncher
A modern, multilingual launchpad for photo‑processing and service utilities.
Version: 2.9 – Ensured launched modules open maximised on Windows
Run: python PhotoSuiteLauncher.py
"""
import sys
import subprocess
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

# --- Optional Windows‑specific imports (only loaded when needed) ---
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

# --- Configuration ---
VERSION = "2.9"

# Maps programmatic keys to script filenames and their corresponding icon files.
SCRIPTS = {
    "photo_processing": {"script": "FaceDetection.py", "icon": "photo_processing.png"},
    "ai_description": {"script": "AIPhotoDescriptionGenerator.py", "icon": "ai_description.png"},
    "db_viewer": {"script": "FaceDBViewer.py", "icon": "db_viewer.png"},
    "vector_updater": {"script": "FaceVectorUpdater.py", "icon": "vector_updater.png"},
    "db_cleaner": {"script": "FaceDB_Cleaner.py", "icon": "db_cleaner.png"},
    "na_to_id": {"script": "NA-to-ID.py", "icon": "na_to_id.png"},
}

TRANSLATIONS = {
    "EN": {
        "title": "Photo Suite – Unified Tool", "select_module": "Select a module to launch:",
        "photo_processing": "Photo Processing", "ai_description": "AI Description &\nRenaming",
        "db_viewer": "DB Viewer", "vector_updater": "Update Face\nVectors", "db_cleaner": "Clean Database",
        "na_to_id": "NA ➔ ID", "error_title": "Error", "starting": "Starting...",
        "file_not_found": "File {script} not found in the application directory.",
        "failed_to_launch": "Failed to launch {label}: {e}", "version": "v{version} • July 2025"
    },
    "RU": {
        "title": "Фото‑Инструменты – Единый Запуск", "select_module": "Выберите модуль для запуска:",
        "photo_processing": "Обработка фото", "ai_description": "AI Описания и\nпереименование",
        "db_viewer": "Просмотр БД", "vector_updater": "Обновление\nвекторов лиц", "db_cleaner": "Очистка базы",
        "na_to_id": "NA ➔ ID", "error_title": "Ошибка", "starting": "Запускается...",
        "file_not_found": "Файл {script} не найден рядом с программой.",
        "failed_to_launch": "Не удалось запустить {label}: {e}", "version": "v{version} • Июль 2025"
    }
}


class LauncherApp:
    """Main launcher UI with tile animation and localisation."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.current_lang = "EN"
        self.script_keys = list(SCRIPTS.keys())
        self.animation_running = False

        self.icons = self._load_icons()
        if not self.icons:
            root.destroy()
            return

        self._configure_styles()
        self.widgets = {}
        self._create_widgets()
        self._update_ui(self.current_lang)

    # ---------------------------------------------------------------------
    #  Windows window‑management helper
    # ---------------------------------------------------------------------
    def _maximize_process_windows(self, pid: int, retries: int = 20, delay: float = 0.4):
        """Enumerate all top‑level windows belonging to *pid* and maximise them.

        Runs in a background thread to avoid blocking the Tk mainloop.
        Only executed on Windows.
        """
        if sys.platform != "win32":
            return  # noop on POSIX systems

        def worker():
            user32 = ctypes.windll.user32
            EnumWindows = user32.EnumWindows
            GetWindowThreadProcessId = user32.GetWindowThreadProcessId
            IsWindowVisible = user32.IsWindowVisible
            ShowWindow = user32.ShowWindow
            SW_MAXIMIZE = 3  # Constant from WinUser.h

            # Callback prototype for EnumWindows
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

            for _ in range(retries):
                handles = []

                def _callback(hwnd, lParam):
                    pid_buf = wintypes.DWORD()
                    GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
                    if pid_buf.value == pid and IsWindowVisible(hwnd):
                        handles.append(hwnd)
                    return True  # continue enumeration

                EnumWindows(WNDENUMPROC(_callback), 0)

                if handles:
                    for hwnd in handles:
                        ShowWindow(hwnd, SW_MAXIMIZE)
                    return  # maximised, done

                time.sleep(delay)

        threading.Thread(target=worker, daemon=True).start()

    # ---------------------------------------------------------------------
    #  Tk‑inter styling / assets
    # ---------------------------------------------------------------------
    def _configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('TFrame', background='#F0F0F0')
        style.configure('TLabel', background='#F0F0F0', foreground='#333333', font=('Segoe UI', 10))
        style.configure('Header.TLabel', font=('Segoe UI', 16, 'bold'))
        style.configure('Footer.TLabel', font=('Segoe UI', 8), foreground='#666666')
        style.configure('Module.TButton', font=('Segoe UI', 11), padding=10, background='#FFFFFF',
                        foreground='#333333', borderwidth=1, relief='flat', justify='center')
        style.map('Module.TButton', background=[('active', '#E5F1FB')],
                  relief=[('pressed', 'solid'), ('!pressed', 'flat')])

        # Combobox list colours
        self.root.option_add('*TCombobox*Listbox*Background', '#FFFFFF')
        self.root.option_add('*TCombobox*Listbox*Foreground', '#333333')
        self.root.option_add('*TCombobox*Listbox*selectBackground', '#0078D7')
        self.root.option_add('*TCombobox*Listbox*selectForeground', '#FFFFFF')
        style.configure('TCombobox', fieldbackground='#FFFFFF', background='#FFFFFF', foreground='#333333',
                        arrowcolor='#555555', relief='solid', borderwidth=1)

    def _load_icons(self):
        loaded_icons = {}
        icon_dir = Path('icons')
        if not icon_dir.is_dir():
            messagebox.showerror('Ошибка', "Папка 'icons' не найдена.")
            return None

        for key, data in SCRIPTS.items():
            icon_path = icon_dir / data['icon']
            try:
                image = Image.open(icon_path).resize((64, 64), Image.LANCZOS)
                loaded_icons[key] = ImageTk.PhotoImage(image)

                large = Image.open(icon_path).resize((96, 96), Image.LANCZOS)
                loaded_icons[f"{key}_large"] = ImageTk.PhotoImage(large)
            except Exception:
                messagebox.showerror('Ошибка иконки', f'Не удалось загрузить иконку: {icon_path}')
                return None
        return loaded_icons

    # ---------------------------------------------------------------------
    #  UI construction
    # ---------------------------------------------------------------------
    def _create_widgets(self):
        self.root.geometry('620x500')
        self.root.resizable(False, False)
        self.root.configure(bg='#F0F0F0')

        main = ttk.Frame(self.root, padding=20)
        main.pack(fill=tk.BOTH, expand=True)

        # Header (title + language selector)
        header = ttk.Frame(main)
        header.pack(fill=tk.X, pady=(0, 20))

        self.widgets['title'] = ttk.Label(header, style='Header.TLabel')
        self.widgets['title'].pack(side=tk.LEFT, anchor='w')

        lang_frame = ttk.Frame(header)
        lang_frame.pack(side=tk.RIGHT, anchor='e')
        ttk.Label(lang_frame, text='Language:', font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 5))
        self.widgets['lang_combo'] = ttk.Combobox(lang_frame, values=['EN', 'RU'], state='readonly', width=5)
        self.widgets['lang_combo'].set(self.current_lang)
        self.widgets['lang_combo'].pack(side=tk.LEFT)
        self.widgets['lang_combo'].bind('<<ComboboxSelected>>', self._on_language_change)

        # Tiles grid
        self.widgets['grid'] = ttk.Frame(main)
        self.widgets['grid'].pack(fill=tk.BOTH, expand=True)

        for i in range(3):
            self.widgets['grid'].columnconfigure(i, weight=1, uniform='col')
        for i in range(2):
            self.widgets['grid'].rowconfigure(i, weight=1, uniform='row')

        self.widgets['buttons'] = {}
        for i, key in enumerate(self.script_keys):
            r, c = divmod(i, 3)
            btn = ttk.Button(self.widgets['grid'], image=self.icons[key], compound=tk.TOP,
                              style='Module.TButton', command=lambda k=key: self._launch(k))
            btn.grid(row=r, column=c, padx=10, pady=10, sticky='nsew')
            self.widgets['buttons'][key] = btn

        # Footer
        self.widgets['footer'] = ttk.Label(main, style='Footer.TLabel', anchor='center')
        self.widgets['footer'].pack(side=tk.BOTTOM, pady=(20, 0))

    # ------------------------------------------------------------------
    #  Localisation helpers
    # ------------------------------------------------------------------
    def _on_language_change(self, _):
        if not self.animation_running:
            new_lang = self.widgets['lang_combo'].get()
            if new_lang != self.current_lang:
                self.current_lang = new_lang
                self._update_ui(new_lang)

    def _update_ui(self, lang):
        T = TRANSLATIONS[lang]
        self.root.title(T['title'])
        self.widgets['title'].config(text=T['select_module'])
        self.widgets['footer'].config(text=T['version'].format(version=VERSION))
        for key, btn in self.widgets['buttons'].items():
            btn.config(text=T[key])

    # ------------------------------------------------------------------
    #  Animation + launch logic
    # ------------------------------------------------------------------
    def _animate_widget(self, widget, sx, sy, ex, ey, ss, es, step=0, steps=30, cb=None):
        if step > steps:
            if cb:
                cb()
            return

        prog = 1 - (1 - (step / steps)) ** 3  # ease‑out cubic
        nx = sx + (ex - sx) * prog
        ny = sy + (ey - sy) * prog
        nw = ss[0] + (es[0] - ss[0]) * prog
        nh = ss[1] + (es[1] - ss[1]) * prog
        widget.place(x=nx, y=ny, width=nw, height=nh)
        self.root.after(10, self._animate_widget, widget, sx, sy, ex, ey, ss, es, step + 1, steps, cb)

    def _launch(self, script_key):
        if self.animation_running:
            return
        self.animation_running = True

        # Disable all buttons
        for b in self.widgets['buttons'].values():
            b.config(state=tk.DISABLED)

        btn = self.widgets['buttons'][script_key]
        grid = self.widgets['grid']
        sx, sy = btn.winfo_x(), btn.winfo_y()
        w, h = btn.winfo_width(), btn.winfo_height()

        # Animated placeholder frame
        frame = tk.Frame(grid, bg='#F0F0F0', highlightthickness=1, highlightbackground='#CCCCCC')
        tk.Label(frame, image=self.icons[f'{script_key}_large'], bg='#F0F0F0').pack(expand=True, pady=(10, 5))
        tk.Label(frame, text=TRANSLATIONS[self.current_lang]['starting'], font=('Segoe UI', 10, 'bold'),
                 bg='#F0F0F0', fg='#005a9e').pack(pady=(0, 10))
        frame.place(x=sx, y=sy, width=w, height=h)
        btn.grid_remove()

        tw, th = int(w * 1.5), int(h * 1.5)
        cx = (grid.winfo_width() - tw) / 2
        cy = (grid.winfo_height() - th) / 2

        def restore():
            frame.destroy()
            btn.grid()
            for b in self.widgets['buttons'].values():
                b.config(state=tk.NORMAL)
            self.animation_running = False

        def ret_anim():
            self._animate_widget(frame, cx, cy, sx, sy, (tw, th), (w, h), cb=restore)

        def after_center():
            self.root.after(5000, ret_anim)

        self._animate_widget(frame, sx, sy, cx, cy, (w, h), (tw, th), cb=after_center)

        # ------------------------------------------------------------
        #  Launch external script
        # ------------------------------------------------------------
        script_file = SCRIPTS[script_key]['script']
        script_path = Path(__file__).parent / script_file

        try:
            if not script_path.exists():
                raise FileNotFoundError

            if sys.platform == 'win32':
                # Console launched maximised; Tk window handled separately below.
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 3  # SW_MAXIMIZE
                proc = subprocess.Popen([sys.executable, str(script_path)], startupinfo=si)

                # Ensure any GUI windows belonging to *proc* are maximised too.
                self._maximize_process_windows(proc.pid)
            else:
                subprocess.Popen([sys.executable, str(script_path)])

        except Exception as e:
            restore()
            T_err = TRANSLATIONS[self.current_lang]
            if isinstance(e, FileNotFoundError):
                messagebox.showerror(T_err['error_title'], T_err['file_not_found'].format(script=script_file))
            else:
                lbl = T_err[script_key].replace('\n', ' ')
                messagebox.showerror(T_err['error_title'], T_err['failed_to_launch'].format(label=lbl, e=e))


# -------------------------------------------------------------------------
#  Entry point
# -------------------------------------------------------------------------

def main():
    root = tk.Tk()
    try:
        from PIL import Image, ImageTk  # noqa: F401 – imported to provoke ImportError if missing
    except ImportError:
        messagebox.showerror('Dependency Error', 'Pillow library not found.\nPlease install it using: pip install Pillow')
        root.destroy()
        return

    app = LauncherApp(root)
    if app.icons:
        root.mainloop()


if __name__ == '__main__':
    main()
