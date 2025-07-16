
"""PhotoSuiteLauncher
Unified launch pad for photo processing and service utilities built from FaceDetection, AIPhotoDescriptionGenerator and related tools.
Run: python PhotoSuiteLauncher.py
"""
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess, sys, os
from pathlib import Path

SCRIPTS = {
    "Обработка фото": "FaceDetection.py",
    "AI описания и переименование": "AIPhotoDescriptionGenerator.py",
    "Просмотр БД": "FaceDBViewer.py",
    "Обновление векторов лиц": "FaceVectorUpdater.py",
    "Очистка базы": "FaceDB_Cleaner.py",
    "NA ➔ ID": "NA-to-ID.py",
}

class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Photo Suite – Unified Tool")
        self.root.geometry("600x400")
        self.create_widgets()

    def create_widgets(self):
        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Выберите модуль:", font=('Arial', 14, 'bold')).pack(pady=(0,15))

        for label, script in SCRIPTS.items():
            btn = ttk.Button(frame, text=label, style='Accent.TButton',
                             command=lambda s=script, l=label: self.launch(s, l))
            btn.pack(fill=tk.X, pady=5)

        ttk.Label(frame, text="v1.0 • July 2025", font=('Arial', 8)).pack(side=tk.BOTTOM, pady=(20,0))

    def launch(self, script, label):
        path = Path(script)
        if not path.exists():
            messagebox.showerror("Ошибка", f"Файл {script} не найден рядом с Launcher.")
            return
        try:
            subprocess.Popen([sys.executable, str(path)])
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось запустить {label}: {e}")

def main():
    root = tk.Tk()
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass
    style.configure('Accent.TButton', font=('Arial', 10, 'bold'))
    app = LauncherApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
