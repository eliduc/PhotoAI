"""
AI Photo Description Generator
Программа для генерации описаний фотографий через LLM API

Версия: 2.0.0
- Добавлена функция переименования (копирования) файлов на основе AI-описаний.
- Автоматическое определение пути для сохранения переименованных файлов.
- Обработка конфликтов имен файлов.
- Добавлена иконка для копирования лога.
- UI/UX адаптирован под новый функционал.
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import os
import sqlite3
from datetime import datetime
from PIL import Image, ImageTk
import cv2
import numpy as np
import threading
import queue
import json
import base64
import configparser
from pathlib import Path
import re
from io import BytesIO
import warnings
import shutil
from collections import Counter

# Версия программы
VERSION = "2.0.0"

# Подавляем предупреждения от Pillow о некорректных JPEG
warnings.filterwarnings("ignore", message=".*Invalid SOS parameters.*")
warnings.filterwarnings("ignore", message=".*Corrupt JPEG data.*")
Image.MAX_IMAGE_PIXELS = None  # Разрешаем загрузку больших изображений

# OpenAI
try:
    import openai
except ImportError:
    openai = None

# Anthropic
try:
    import anthropic
except ImportError:
    anthropic = None

# Google Generative AI (Gemini)
try:
    import google.generativeai as genai
except ImportError:
    genai = None


class EditDescriptionDialog(tk.Toplevel):
    """Диалог для редактирования описаний"""
    def __init__(self, parent, image_path, short_desc, long_desc, image_data=None):
        super().__init__(parent)
        self.parent = parent
        self.result = None
        
        self.title("Редактирование описаний")
        self.geometry("800x600")
        self.resizable(True, True)
        
        self.transient(parent)
        self.grab_set()
        
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        image_frame = ttk.LabelFrame(main_frame, text="Изображение", padding="5")
        image_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        
        if image_data is not None:
            image = Image.fromarray(cv2.cvtColor(image_data, cv2.COLOR_BGR2RGB))
        else:
            image = Image.open(image_path)
        
        image.thumbnail((300, 200), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        
        image_label = ttk.Label(image_frame, image=photo)
        image_label.image = photo
        image_label.pack()
        
        ttk.Label(image_frame, text=os.path.basename(image_path), font=('Arial', 9)).pack()
        
        desc_frame = ttk.Frame(main_frame)
        desc_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(desc_frame, text="Краткое описание:").pack(anchor=tk.W, pady=(10, 5))
        
        self.short_desc_var = tk.StringVar(value=short_desc)
        self.short_entry = ttk.Entry(desc_frame, textvariable=self.short_desc_var, width=60)
        self.short_entry.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(desc_frame, text="Подробное описание:").pack(anchor=tk.W, pady=(0, 5))
        
        text_frame = ttk.Frame(desc_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.long_text = tk.Text(text_frame, wrap=tk.WORD, height=10, relief=tk.SOLID, borderwidth=1)
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.long_text.yview)
        self.long_text.configure(yscrollcommand=scroll.set)
        
        self.long_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.long_text.insert('1.0', long_desc)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Отмена", command=self.cancel).pack(side=tk.RIGHT, padx=5)
        
        self.center_window()
        
    def center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f'+{x}+{y}')
        
    def save(self):
        short = self.short_desc_var.get().strip()
        if not short:
            messagebox.showwarning("Предупреждение", "Краткое описание не может быть пустым", parent=self)
            return
        
        self.result = {
            'short': short,
            'long': self.long_text.get('1.0', tk.END).strip()
        }
        self.destroy()
        
    def cancel(self):
        self.result = None
        self.destroy()


class ProcessedImagesDialog(tk.Toplevel):
    """Диалог для обработанных изображений с показом текущих описаний"""
    def __init__(self, parent, image_path, existing_short_desc, existing_long_desc):
        super().__init__(parent)
        self.parent = parent
        self.result = None
        self.apply_to_all = False
        
        self.title("Изображение уже обработано")
        self.geometry("600x450")
        self.resizable(True, True)
        
        self.transient(parent); self.grab_set()
        
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        message = f"Изображение '{os.path.basename(image_path)}' уже имеет описания.\nОбработать его заново?"
        ttk.Label(main_frame, text=message, wraplength=550).pack(pady=10)

        if existing_short_desc or existing_long_desc:
            desc_frame = ttk.LabelFrame(main_frame, text="Существующие описания", padding=10)
            desc_frame.pack(fill=tk.BOTH, expand=True, pady=10)

            ttk.Label(desc_frame, text="Краткое:", font=('Arial', 9, 'bold')).pack(anchor=tk.W)
            ttk.Label(desc_frame, text=existing_short_desc, wraplength=500, justify=tk.LEFT).pack(anchor=tk.W, fill=tk.X, pady=(0,10))

            ttk.Label(desc_frame, text="Подробное:", font=('Arial', 9, 'bold')).pack(anchor=tk.W)
            text_area = scrolledtext.ScrolledText(desc_frame, height=5, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
            text_area.insert('1.0', existing_long_desc)
            text_area.config(state=tk.DISABLED)
            text_area.pack(fill=tk.BOTH, expand=True)

        self.apply_to_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(main_frame, text="Применить это решение для всех последующих изображений",
                       variable=self.apply_to_all_var).pack(pady=(10,0))
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(15, 0))
        
        ttk.Button(button_frame, text="Да, обработать", command=self.process).pack(side=tk.LEFT, padx=5, expand=True)
        ttk.Button(button_frame, text="Нет, пропустить", command=self.skip).pack(side=tk.LEFT, padx=5, expand=True)
        ttk.Button(button_frame, text="Отмена", command=self.cancel).pack(side=tk.RIGHT, padx=5, expand=True)
        
        self.center_window()
        
    def center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f'+{x}+{y}')
        
    def process(self): self.result = 'process'; self.apply_to_all = self.apply_to_all_var.get(); self.destroy()
    def skip(self): self.result = 'skip'; self.apply_to_all = self.apply_to_all_var.get(); self.destroy()
    def cancel(self): self.result = 'cancel'; self.destroy()


class AIPhotoDescriptor:
    def __init__(self, root):
        self.root = root
        self.root.title(f"AI Photo Description Generator v{VERSION}")
        self.root.geometry("1400x900")

        # --- Стили ---
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use('clam')
        except tk.TclError: pass
        self.style.configure('TLabelFrame.Label', font=('Arial', 10, 'bold'))
        self.style.configure('TNotebook.Tab', font=('Arial', 12, 'bold'), padding=[10, 5])
        self.style.configure('Status.TLabel', font=('Arial', 11, 'bold'), padding=5)
        self.style.configure('Idle.Status.TLabel', background='lightblue', foreground='black')
        self.style.configure('Processing.Status.TLabel', background='lightyellow', foreground='black')
        self.style.configure('Complete.Status.TLabel', background='lightgreen', foreground='black')
        self.style.configure('Error.Status.TLabel', background='lightcoral', foreground='black')
        self.style.configure('Accent.TButton', font=('Arial', 10, 'bold'), foreground='navy')
        
        self.update_queue = queue.Queue()
        
        self.db_path = tk.StringVar()
        self.rename_dest_dir = tk.StringVar()
        self.selected_llm = tk.StringVar()
        self.process_mode = tk.StringVar(value="single")
        self.processed_mode = tk.StringVar(value="skip")
        self.description_language = tk.StringVar(value="ru")
        self.processing = False
        self.llm_clients = {}
        self.available_llms = []
        self.processed_decision_for_all = None
        
        self.init_llm_clients()
        self.create_widgets()
        self.process_queue()
        
        ttk.Label(self.root, text=f"v{VERSION}", font=('Arial', 9)).place(relx=0.99, y=5, anchor='ne')
        self.update_status("Готов к работе", 'idle')
        
    def init_llm_clients(self):
        keys_file = "keys-ai.ini"
        if not os.path.exists(keys_file):
            messagebox.showwarning("Предупреждение", f"Файл {keys_file} не найден. API не будут работать.")
            return
            
        config = configparser.ConfigParser()
        config.read(keys_file)
        if 'Keys' not in config: return
            
        if 'OpenAI' in config['Keys'] and config['Keys']['OpenAI'] and openai:
            try:
                self.llm_clients['OpenAI'] = openai.OpenAI(api_key=config['Keys']['OpenAI'])
                self.available_llms.append('OpenAI')
            except Exception as e: print(f"Ошибка OpenAI: {e}")
                
        if 'ANTHROPIC' in config['Keys'] and config['Keys']['ANTHROPIC'] and anthropic:
            try:
                self.llm_clients['Anthropic'] = anthropic.Anthropic(api_key=config['Keys']['ANTHROPIC'])
                self.available_llms.append('Anthropic')
            except Exception as e: print(f"Ошибка Anthropic: {e}")
                
        if 'GEMINI' in config['Keys'] and config['Keys']['GEMINI'] and genai:
            try:
                genai.configure(api_key=config['Keys']['GEMINI'])
                self.llm_clients['Gemini'] = genai.GenerativeModel('gemini-1.5-flash')
                self.available_llms.append('Gemini')
            except Exception as e: print(f"Ошибка Gemini: {e}")
                
    def create_widgets(self):
        main_notebook = ttk.Notebook(self.root)
        main_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        process_frame = ttk.Frame(main_notebook)
        main_notebook.add(process_frame, text="Обработка")
        self.create_process_tab(process_frame)
        
    def create_process_tab(self, parent):
        parent.grid_rowconfigure(3, weight=1)
        parent.grid_columnconfigure(0, weight=3)
        parent.grid_columnconfigure(1, weight=2)

        settings_frame = ttk.LabelFrame(parent, text="Настройки", padding="10")
        settings_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        settings_frame.columnconfigure(1, weight=1)
        ttk.Label(settings_frame, text="База данных:").grid(row=0, column=0, sticky=tk.W, pady=5)
        db_entry_frame = ttk.Frame(settings_frame)
        db_entry_frame.grid(row=0, column=1, columnspan=2, sticky=tk.EW)
        ttk.Entry(db_entry_frame, textvariable=self.db_path, width=60).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(db_entry_frame, text="Обзор", command=self.browse_db).pack(side=tk.LEFT)
        config_frame = ttk.Frame(settings_frame)
        config_frame.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=5)
        ttk.Label(config_frame, text="LLM:").pack(side=tk.LEFT, padx=(0, 5))
        self.llm_combo = ttk.Combobox(config_frame, textvariable=self.selected_llm, values=self.available_llms, state="readonly", width=15)
        self.llm_combo.pack(side=tk.LEFT, padx=5)
        if self.available_llms: self.llm_combo.current(0)
        ttk.Label(config_frame, text="Язык:").pack(side=tk.LEFT, padx=(20, 5))
        ttk.Radiobutton(config_frame, text="Русский", variable=self.description_language, value="ru").pack(side=tk.LEFT)
        ttk.Radiobutton(config_frame, text="English", variable=self.description_language, value="en").pack(side=tk.LEFT, padx=10)
        modes_frame = ttk.Frame(settings_frame)
        modes_frame.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=5)
        mode_frame = ttk.LabelFrame(modes_frame, text="Режим обработки", padding=5)
        mode_frame.pack(side=tk.LEFT, fill=tk.X, padx=(0, 10))
        ttk.Radiobutton(mode_frame, text="По одному фото", variable=self.process_mode, value="single").pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="Пакетная обработка", variable=self.process_mode, value="batch").pack(anchor=tk.W)
        processed_frame = ttk.LabelFrame(modes_frame, text="Уже обработанные", padding=5)
        processed_frame.pack(side=tk.LEFT, fill=tk.X)
        ttk.Radiobutton(processed_frame, text="Пропускать", variable=self.processed_mode, value="skip").pack(anchor=tk.W)
        ttk.Radiobutton(processed_frame, text="Обрабатывать заново", variable=self.processed_mode, value="process").pack(anchor=tk.W)
        ttk.Radiobutton(processed_frame, text="Спрашивать", variable=self.processed_mode, value="ask").pack(anchor=tk.W)
        
        control_frame = ttk.Frame(parent)
        control_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        self.start_btn = ttk.Button(control_frame, text="🚀 Начать обработку", command=self.start_processing, style="Accent.TButton")
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(control_frame, text="🛑 Остановить", command=self.stop_processing, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Обновить имена файлов", command=self.toggle_rename_frame).pack(side=tk.LEFT, padx=5)
        self.exit_btn = ttk.Button(control_frame, text="Выход", command=self.root.destroy)
        self.exit_btn.pack(side=tk.RIGHT, padx=5)
        
        self.rename_frame = ttk.LabelFrame(parent, text="Переименование файлов", padding="10")
        self.rename_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        ttk.Label(self.rename_frame, text="Директория для файлов с новыми именами:").grid(row=0, column=0, sticky=tk.W, pady=2)
        rename_entry_frame = ttk.Frame(self.rename_frame)
        rename_entry_frame.grid(row=1, column=0, sticky=tk.EW, pady=2)
        ttk.Entry(rename_entry_frame, textvariable=self.rename_dest_dir, width=80).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))
        ttk.Button(rename_entry_frame, text="Обзор...", command=self.browse_rename_dest).pack(side=tk.LEFT)
        self.rename_frame.columnconfigure(0, weight=1)
        ttk.Button(self.rename_frame, text="Начать переименование", command=self.start_renaming_process, style="Accent.TButton").grid(row=2, column=0, pady=(10,0), sticky=tk.W)
        self.rename_frame.grid_remove() # Скрываем по умолчанию

        image_frame = ttk.LabelFrame(parent, text="Текущее изображение", padding="10")
        image_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=10)
        self.image_label = ttk.Label(image_frame)
        self.image_label.pack(expand=True, fill=tk.BOTH)
        
        log_frame = ttk.LabelFrame(parent, text="Лог обработки", padding="10")
        log_frame.grid(row=3, column=1, sticky="nsew", padx=10, pady=10)
        self.log_text = scrolledtext.ScrolledText(log_frame, width=50, height=30, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.copy_btn = ttk.Button(log_frame, text="📋", width=3, command=self.copy_log_to_clipboard)
        self.copy_btn.place(relx=1.0, rely=0, x=-5, y=5, anchor="ne")

        self.status_bar = ttk.Label(self.root, text="", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def update_status(self, message, status_type):
        self.update_queue.put(('status', (message, status_type)))

    def copy_log_to_clipboard(self):
        content = self.log_text.get('1.0', tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.update_status("Лог скопирован в буфер обмена.", 'idle')

    def browse_db(self):
        filename = filedialog.askopenfilename(title="Выберите базу данных", filetypes=[("SQLite DB", "*.db"), ("Все файлы", "*.*")])
        if filename:
            self.db_path.set(filename)
            self.update_database_schema()
            self.check_dogs_support()

    def browse_rename_dest(self):
        directory = filedialog.askdirectory(title="Выберите директорию для сохранения")
        if directory:
            self.rename_dest_dir.set(directory)

    def toggle_rename_frame(self):
        if not self.db_path.get() or not os.path.exists(self.db_path.get()):
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочую базу данных.")
            return
        if self.rename_frame.winfo_viewable():
            self.rename_frame.grid_remove()
        else:
            self.rename_frame.grid()
            self.propose_rename_directory()

    def propose_rename_directory(self):
        self.log("Анализ путей для определения директории по умолчанию...")
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT filepath FROM images WHERE filepath IS NOT NULL")
                paths = [row[0] for row in cursor.fetchall()]
            if not paths:
                self.log("В БД нет путей к файлам.")
                return
            
            dir_counts = Counter(os.path.dirname(p) for p in paths)
            most_common_dir = dir_counts.most_common(1)[0][0]
            
            dest_path = os.path.join(most_common_dir, "New Names")
            self.rename_dest_dir.set(dest_path)
            self.log(f"Предложена директория для переименования: {dest_path}")
        except Exception as e:
            self.log(f"Ошибка при определении директории: {e}")

    def check_dogs_support(self):
        with sqlite3.connect(self.db_path.get()) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('dogs', 'dog_detections')")
                if len(cursor.fetchall()) == 2: self.log("База данных поддерживает собак.")
                else: self.log("База данных не содержит информации о собаках.")
            except Exception as e: self.log(f"Ошибка проверки поддержки собак: {e}")

    def update_database_schema(self):
        if not os.path.exists(self.db_path.get()): return
        with sqlite3.connect(self.db_path.get()) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("PRAGMA table_info(images)")
                columns = [col[1] for col in cursor.fetchall()]
                new_cols = {'ai_short_description': 'TEXT', 'ai_long_description': 'TEXT', 'ai_processed_date': 'TEXT', 'ai_llm_used': 'TEXT', 'ai_language': 'TEXT'}
                for col, col_type in new_cols.items():
                    if col not in columns:
                        cursor.execute(f'ALTER TABLE images ADD COLUMN {col} {col_type}')
                        self.log(f"Добавлено поле {col} в таблицу images.")
                conn.commit()
            except Exception as e: self.log(f"Ошибка обновления схемы БД: {e}")

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.update_queue.put(('log', f"[{timestamp}] {message}\n"))

    def update_image(self, image_path):
        self.update_queue.put(('image', image_path))

    def display_image(self, image_path):
        try:
            image = Image.open(image_path)
            self.image_label.update_idletasks()
            w, h = self.image_label.winfo_width(), self.image_label.winfo_height()
            if w <= 1 or h <= 1: w, h = 500, 500
            image.thumbnail((w - 20, h - 20), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self.image_label.config(image=photo); self.image_label.image = photo
        except Exception as e: self.log(f"Ошибка отображения: {e}")

    def process_queue(self):
        try:
            while True:
                action, data = self.update_queue.get_nowait()
                if action == 'log':
                    self.log_text.config(state=tk.NORMAL)
                    self.log_text.insert(tk.END, data)
                    self.log_text.config(state=tk.DISABLED)
                    self.log_text.see(tk.END)
                elif action == 'image': self.display_image(data)
                elif action == 'status':
                    message, status_type = data
                    self.status_bar.config(text=message)
                    style_map = {'idle': 'Idle.Status.TLabel', 'processing': 'Processing.Status.TLabel', 'complete': 'Complete.Status.TLabel', 'error': 'Error.Status.TLabel'}
                    self.status_bar.config(style=style_map.get(status_type, 'Idle.Status.TLabel'))
                elif action == 'enable_buttons':
                    self.start_btn.config(state=tk.NORMAL)
                    self.stop_btn.config(state=tk.DISABLED)
                elif action == 'show_edit_dialog': self.show_edit_dialog_main(data)
                elif action == 'show_processed_dialog': self.show_processed_dialog_main(data)
                elif action == 'show_error': messagebox.showerror("Ошибка", data)
                elif action == 'show_info': messagebox.showinfo("Информация", data)
        except queue.Empty: pass
        finally: self.root.after(100, self.process_queue)

    def get_image_base64(self, image_path):
        try:
            with Image.open(image_path) as img:
                if img.mode not in ('RGB', 'L'): img = img.convert('RGB')
                max_size = 2048
                if img.width > max_size or img.height > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                    self.log(f"  Изображение уменьшено до {img.width}x{img.height}")
                buffer = BytesIO()
                fmt = 'PNG' if image_path.lower().endswith('.png') else 'JPEG'
                img.save(buffer, format=fmt, quality=85, optimize=True)
                buffer.seek(0)
                return base64.b64encode(buffer.read()).decode('utf-8')
        except Exception as e:
            self.log(f"  Предупреждение при оптимизации: {e}. Пробуем напрямую.")
            with open(image_path, "rb") as image_file: return base64.b64encode(image_file.read()).decode('utf-8')

    def transliterate(self, text):
        translit_dict = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya','А':'A','Б':'B','В':'V','Г':'G','Д':'D','Е':'E','Ё':'Yo','Ж':'Zh','З':'Z','И':'I','Й':'Y','К':'K','Л':'L','М':'M','Н':'N','О':'O','П':'P','Р':'R','С':'S','Т':'T','У':'U','Ф':'F','Х':'H','Ц':'Ts','Ч':'Ch','Ш':'Sh','Щ':'Sch','Ъ':'','Ы':'Y','Ь':'','Э':'E','Ю':'Yu','Я':'Ya'}
        result = ''.join([translit_dict.get(char, char) for char in text if char.isalnum() or char in ' '])
        return re.sub(r'\s+', '_', result).strip('_')

    def sanitize_filename(self, filename):
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        return filename[:200]

    def get_persons_for_image(self, image_id):
        with sqlite3.connect(self.db_path.get()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT COALESCE(p.short_name, pd.local_short_name) FROM person_detections pd LEFT JOIN persons p ON pd.person_id = p.id WHERE pd.image_id = ? AND COALESCE(p.short_name, pd.local_short_name) IS NOT NULL ORDER BY pd.person_index", (image_id,))
            return [row[0] for row in cursor.fetchall()]

    def get_dogs_for_image(self, image_id):
        with sqlite3.connect(self.db_path.get()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dog_detections'")
            if not cursor.fetchone(): return []
            cursor.execute("SELECT DISTINCT d.name FROM dog_detections dd LEFT JOIN dogs d ON dd.dog_id = d.id WHERE dd.image_id = ? AND d.name IS NOT NULL ORDER BY dd.dog_index", (image_id,))
            return [row[0] for row in cursor.fetchall()]

    def get_language_specific_prompt(self, person_names, dog_names):
        lang = self.description_language.get()
        if lang == "ru":
            base_prompt = "Проанализируй это изображение и предоставь описания на русском языке.\n\nТы ДОЛЖЕН ответить ТОЛЬКО JSON объектом со структурой:\n{\"short\": \"краткое описание на русском\", \"long\": \"подробное описание изображения на русском\"}\n\nПравила для краткого описания:\n- Краткое описание сцены на русском языке.\n- Используй пробелы между словами (НЕ подчеркивания).\n- Максимум 100 символов.\n- На правильном русском языке.\n- Это описание будет использовано как имя файла, поэтому оно должно быть лаконичным и информативным."
        else:
            base_prompt = "Analyze this image and provide descriptions in English.\n\nYou MUST respond with ONLY a JSON object with the structure:\n{\"short\": \"short description in English\", \"long\": \"detailed description of the image in English\"}\n\nRules for the short description:\n- Brief description of the scene in English.\n- Use spaces between words (NOT underscores).\n- Maximum 100 characters.\n- In proper English.\n- This description will be used as a filename, so it should be concise and informative."

        if person_names:
            names_str = ", ".join(person_names)
            if lang == "ru": base_prompt += f"\n\nЛюди на этом изображении: {names_str}\nВАЖНО: Включи эти имена в свои описания, транскрибируя с английского, если нужно (например: Keith → Кит)."
            else: base_prompt += f"\n\nPeople in this image: {names_str}\nIMPORTANT: Include these names, transcribing from Cyrillic if needed (e.g., Женя → Zhenia)."
        if dog_names:
            dogs_str = ", ".join(dog_names)
            if lang == "ru": base_prompt += f"\n\nСобаки на этом изображении: {dogs_str}\nВАЖНО: Включи эти клички собак в свои описания и обращайся с ними как с важными участниками фото."
            else: base_prompt += f"\n\nDogs in this image: {dogs_str}\nIMPORTANT: Include these dog names and treat them as important participants in the photo."
        return base_prompt

    def parse_llm_response(self, content, llm_name):
        self.log(f"  Парсинг ответа от {llm_name}...")
        try:
            cleaned_content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(cleaned_content)
        except json.JSONDecodeError:
            self.log("  Не удалось распарсить JSON, пробуем regex...")
            short_match = re.search(r'"short"\s*:\s*"([^"]+)"', content)
            long_match = re.search(r'"long"\s*:\s*"((?:[^"\\]|\\.)*)"', content, re.DOTALL)
            if short_match and long_match: return {"short": short_match.group(1), "long": long_match.group(1).replace('\\n', '\n')}
            raise Exception(f"{llm_name} вернул ответ не в формате JSON: {content[:200]}...")

    def generate_description(self, image_path, person_names, dog_names):
        llm_map = {
            'OpenAI': self.generate_description_openai,
            'Anthropic': self.generate_description_anthropic,
            'Gemini': self.generate_description_gemini
        }
        selected_llm = self.selected_llm.get()
        if selected_llm in llm_map:
            return llm_map[selected_llm](image_path, person_names, dog_names)
        raise Exception(f"Неизвестная LLM: {selected_llm}")

    def generate_description_openai(self, image_path, person_names, dog_names):
        client = self.llm_clients['OpenAI']
        prompt = self.get_language_specific_prompt(person_names, dog_names)
        image_base64 = self.get_image_base64(image_path)
        try:
            response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}]}], max_tokens=1000, response_format={"type": "json_object"})
            return self.parse_llm_response(response.choices[0].message.content, "OpenAI")
        except Exception as e: raise Exception(f"OpenAI API error: {e}")

    def generate_description_anthropic(self, image_path, person_names, dog_names):
        client = self.llm_clients['Anthropic']
        prompt = self.get_language_specific_prompt(person_names, dog_names)
        image_base64 = self.get_image_base64(image_path)
        try:
            response = client.messages.create(model="claude-3-haiku-20240307", max_tokens=1000, messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_base64}}]}])
            return self.parse_llm_response(response.content[0].text, "Anthropic")
        except Exception as e: raise Exception(f"Anthropic API error: {e}")

    def generate_description_gemini(self, image_path, person_names, dog_names):
        model = self.llm_clients['Gemini']
        prompt = self.get_language_specific_prompt(person_names, dog_names)
        try:
            image = Image.open(image_path)
            response = model.generate_content([prompt, image])
            return self.parse_llm_response(response.text, "Gemini")
        except Exception as e: raise Exception(f"Gemini API error: {e}")

    def show_edit_dialog_main(self, data):
        image_path, short_desc, long_desc, callback = data
        image_data = cv2.imread(image_path)
        dialog = EditDescriptionDialog(self.root, image_path, short_desc, long_desc, image_data)
        self.root.wait_window(dialog)
        callback(dialog.result)

    def show_processed_dialog_main(self, data):
        image_path, short_desc, long_desc, callback = data
        dialog = ProcessedImagesDialog(self.root, image_path, short_desc, long_desc)
        self.root.wait_window(dialog)
        callback(dialog.result, dialog.apply_to_all)

    def get_existing_description(self, image_id):
        with sqlite3.connect(self.db_path.get()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ai_short_description, ai_long_description FROM images WHERE id = ?", (image_id,))
            return cursor.fetchone() or (None, None)

    def is_image_processed(self, image_id):
        with sqlite3.connect(self.db_path.get()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM images WHERE id = ? AND ai_short_description IS NOT NULL", (image_id,))
            return cursor.fetchone() is not None

    def start_action_thread(self, target_func, *args):
        if self.processing: return
        self.processing = True
        self.update_status("Обработка...", "processing")
        thread = threading.Thread(target=target_func, args=args, daemon=True)
        thread.start()

    def end_action_thread(self, status_msg="Готов к работе.", status_type="idle"):
        self.processing = False
        self.update_status(status_msg, status_type)

    def process_images_thread(self):
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                images = conn.execute('SELECT id, filepath FROM images ORDER BY id').fetchall()
            
            total = len(images)
            self.log(f"Найдено изображений в БД: {total}")
            self.processed_decision_for_all = None
            
            for i, (image_id, image_path) in enumerate(images):
                if not self.processing: break
                self.update_status(f"Обработка описаний {i+1}/{total}", 'processing')
                if not os.path.exists(image_path):
                    self.log(f"Файл не найден, пропуск: {image_path}"); continue
                
                self.log(f"\nОбработка: {os.path.basename(image_path)}")
                self.update_image(image_path)
                
                decision = 'process'
                if self.is_image_processed(image_id):
                    mode = self.processed_decision_for_all or self.processed_mode.get()
                    if mode == 'skip': decision = 'skip'
                    elif mode == 'ask':
                        short_d, long_d = self.get_existing_description(image_id)
                        dialog_event = threading.Event()
                        dialog_res = {}
                        def cb(res, apply_all): dialog_res.update({'res':res, 'apply_all':apply_all}); dialog_event.set()
                        self.update_queue.put(('show_processed_dialog', (image_path, short_d, long_d, cb)))
                        dialog_event.wait()
                        decision = dialog_res.get('res')
                        if dialog_res.get('apply_all'): self.processed_decision_for_all = decision

                if decision == 'cancel': self.log("Обработка отменена."); break
                if decision == 'skip': self.log("Пропущено."); continue
                
                person_names = self.get_persons_for_image(image_id)
                dog_names = self.get_dogs_for_image(image_id)
                self.log(f"  Люди: {person_names or 'нет'}. Собаки: {dog_names or 'нет'}.")
                
                try:
                    self.log(f"  Запрос к {self.selected_llm.get()}...")
                    descriptions = self.generate_description(image_path, person_names, dog_names)
                    short_desc, long_desc = descriptions['short'], descriptions['long']
                    self.log("  Ответ получен.")

                    if self.process_mode.get() == 'single':
                        dialog_event = threading.Event()
                        dialog_res = {}
                        def cb(res): dialog_res['res'] = res; dialog_event.set()
                        self.update_queue.put(('show_edit_dialog', (image_path, short_desc, long_desc, cb)))
                        dialog_event.wait()
                        if dialog_res.get('res'):
                            short_desc, long_desc = dialog_res['res']['short'], dialog_res['res']['long']
                            self.log("  Описания отредактированы.")

                    with sqlite3.connect(self.db_path.get()) as conn:
                        conn.execute('UPDATE images SET ai_short_description=?, ai_long_description=?, ai_processed_date=?, ai_llm_used=?, ai_language=? WHERE id=?',
                                     (short_desc, long_desc, datetime.now().isoformat(), self.selected_llm.get(), self.description_language.get(), image_id))
                    self.log("  Описания сохранены в БД.")
                except Exception as e:
                    self.log(f"  !!! ОШИБКА: {e}")
                    if self.process_mode.get() == 'single': self.update_queue.put(('show_error', str(e)))
            
            self.log("\nОбработка описаний завершена!")
        except Exception as e:
            self.log(f"Критическая ошибка: {e}")
            self.update_queue.put(('show_error', f"Критическая ошибка: {e}"))
        finally:
            self.end_action_thread("Обработка описаний завершена.", "complete")

    def start_processing(self):
        if not all([self.db_path.get(), os.path.exists(self.db_path.get())]):
            messagebox.showwarning("Предупреждение", "Выберите существующий файл базы данных.")
            return
        if not self.available_llms:
            messagebox.showwarning("Предупреждение", "Нет доступных LLM. Проверьте файл keys-ai.ini.")
            return
        self.start_btn.config(state=tk.DISABLED); self.stop_btn.config(state=tk.NORMAL)
        self.start_action_thread(self.process_images_thread)

    def stop_processing(self):
        if not self.processing: return
        self.processing = False
        self.log("Остановка обработки...")
        self.end_action_thread("Обработка остановлена.", "idle")

    def renaming_thread(self, dest_dir):
        try:
            os.makedirs(dest_dir, exist_ok=True)
            with sqlite3.connect(self.db_path.get()) as conn:
                images = conn.execute('SELECT filepath, ai_short_description, filename FROM images').fetchall()

            total = len(images)
            self.log(f"Найдено {total} файлов для копирования/переименования.")
            copied, skipped = 0, 0

            for i, (original_path, short_desc, original_filename) in enumerate(images):
                if not self.processing: break
                self.update_status(f"Копирование {i+1}/{total}", "processing")
                
                if not original_path or not os.path.exists(original_path):
                    self.log(f"Файл не найден, пропуск: {original_path or original_filename}")
                    skipped += 1
                    continue

                base_name, extension = os.path.splitext(original_filename)

                if short_desc:
                    new_base_name = self.sanitize_filename(self.transliterate(short_desc))
                    new_filename = f"{new_base_name}{extension}"
                    new_path = os.path.join(dest_dir, new_filename)
                    
                    counter = 1
                    while os.path.exists(new_path):
                        counter += 1
                        new_filename = f"{new_base_name}_({counter}){extension}"
                        new_path = os.path.join(dest_dir, new_filename)
                else:
                    new_filename = f"{base_name}_no_AI_name{extension}"
                    new_path = os.path.join(dest_dir, new_filename)
                
                shutil.copy2(original_path, new_path)
                self.log(f"Скопирован: {original_filename} -> {new_filename}")
                copied += 1

            self.log(f"\nПереименование завершено. Скопировано: {copied}, Пропущено: {skipped}.")
        except Exception as e:
            self.log(f"Критическая ошибка при переименовании: {e}")
            self.update_queue.put(('show_error', f"Ошибка переименования: {e}"))
        finally:
            self.end_action_thread("Переименование завершено.", "complete")

    def start_renaming_process(self):
        dest_dir = self.rename_dest_dir.get()
        if not dest_dir:
            messagebox.showwarning("Предупреждение", "Укажите директорию для сохранения файлов.")
            return
        if not messagebox.askyesno("Подтверждение", f"Начать копирование файлов в директорию:\n{dest_dir}?"):
            return
        self.start_action_thread(self.renaming_thread, dest_dir)


def main():
    root = tk.Tk()
    app = AIPhotoDescriptor(root)
    root.mainloop()

if __name__ == "__main__":
    main()