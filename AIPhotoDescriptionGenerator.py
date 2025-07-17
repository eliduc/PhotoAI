# -*- coding: utf-8 -*-
"""
AI Photo Description Generator v2.4 (Concurrency Fix)
Программа для генерации описаний фотографий с помощью LLM
и последующего переименования файлов.

Версия: 2.4
- Исправлена критическая проблема с состоянием гонки (race condition),
  которая приводила к ошибке "database is locked".
- Реализована блокировка кнопок "Начать обработку" и "Обновить имена файлов"
  на время выполнения одной из задач, что предотвращает их одновременный запуск.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sqlite3
import base64
from io import BytesIO
from PIL import Image, ImageTk, ExifTags
import threading
import queue
import json
import re
import configparser
from datetime import datetime
import shutil
from pathlib import Path

# Попытка импорта опциональных библиотек
try:
    import openai
except ImportError:
    openai = None

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None
    
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

# --- Вспомогательные функции ---

def correct_image_orientation(img: Image.Image) -> Image.Image:
    """Применяет поворот к изображению на основе его EXIF-данных."""
    try:
        exif = img.getexif()
        orientation_tag = 274  # Тег ориентации
        if orientation_tag in exif:
            orientation = exif[orientation_tag]
            if orientation == 3:
                img = img.rotate(180, expand=True)
            elif orientation == 6:
                img = img.rotate(270, expand=True)
            elif orientation == 8:
                img = img.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError):
        # Игнорировать ошибки, если у изображения нет EXIF
        pass
    return img

def get_image_base64(image_path, max_size=(2048, 2048)):
    """Открывает изображение, сжимает его и возвращает в формате Base64."""
    try:
        with Image.open(image_path) as img:
            img = correct_image_orientation(img)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            buffered = BytesIO()
            img.save(buffered, format="JPEG")
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"Ошибка при кодировании изображения {image_path}: {e}")
        return None

def transliterate(name):
    """Простая транслитерация для имен файлов."""
    dic = {'ь':'', 'ъ':'', 'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e',
           'ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n',
           'о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h',
           'ц':'c','ч':'ch','ш':'sh','щ':'shch','ы':'y','э':'e','ю':'yu','я':'ya'}
    return "".join(map(lambda x: dic.get(x, x), name.lower()))

def sanitize_filename(name):
    """Очищает строку для использования в качестве имени файла."""
    # Удаляем запрещенные символы
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    # Заменяем пробелы на подчеркивания
    name = re.sub(r'\s+', '_', name)
    return name

# --- Классы диалоговых окон ---

class ProcessedImagesDialog(tk.Toplevel):
    def __init__(self, parent, image_path, existing_data):
        super().__init__(parent)
        self.result = None
        self.apply_to_all = tk.BooleanVar()

        self.title("Изображение уже обработано")
        self.transient(parent)
        self.grab_set()

        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        message = f"Изображение '{os.path.basename(image_path)}' уже было обработано ранее."
        ttk.Label(main_frame, text=message, wraplength=450).pack(pady=(0, 10))

        if existing_data:
            ttk.Label(main_frame, text="Существующее описание:", font=('TkDefaultFont', 10, 'bold')).pack(anchor=tk.W)
            desc_text = scrolledtext.ScrolledText(main_frame, height=5, wrap=tk.WORD, state=tk.DISABLED)
            desc_text.pack(fill=tk.X, expand=True, pady=5)
            desc_text.config(state=tk.NORMAL)
            desc_text.insert(tk.END, existing_data)
            desc_text.config(state=tk.DISABLED)

        ttk.Checkbutton(main_frame, text="Применить это решение для всех последующих изображений", variable=self.apply_to_all).pack(pady=10)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="Обработать заново", command=self.on_reprocess).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Пропустить", command=self.on_skip).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Отмена", command=self.on_cancel).pack(side=tk.LEFT, padx=5)

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f'+{x}+{y}')

    def on_reprocess(self):
        self.result = "reprocess"
        self.destroy()

    def on_skip(self):
        self.result = "skip"
        self.destroy()
    
    def on_cancel(self):
        self.result = "cancel"
        self.destroy()

class EditDescriptionDialog(tk.Toplevel):
    def __init__(self, parent, image_path, description):
        super().__init__(parent)
        self.result = None
        
        self.title("Редактирование описания")
        self.geometry("1000x700")
        self.transient(parent)
        self.grab_set()
        
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # Панель с изображением
        img_frame = ttk.LabelFrame(main_frame, text="Изображение")
        img_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        img_label = ttk.Label(img_frame)
        img_label.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)

        # Панель с описанием
        desc_frame = ttk.LabelFrame(main_frame, text="Описание")
        desc_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self.desc_text = scrolledtext.ScrolledText(desc_frame, wrap=tk.WORD, width=60)
        self.desc_text.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
        self.desc_text.insert(tk.END, description)

        # Кнопки
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=1, column=0, columnspan=2, pady=10)
        ttk.Button(button_frame, text="Сохранить", command=self.on_save).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="Отмена", command=self.on_cancel).pack(side=tk.LEFT)

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.load_image(image_path, img_label)
        self.center_window()

    def load_image(self, image_path, img_label):
        try:
            # !!! ОШИБКА OpenCV
            # cv2.imread() не работает с кириллицей в путях на Windows.
            # Используем обходной путь через numpy
            if cv2 and np:
                 img_cv = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                 img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
                 img_pil = Image.fromarray(img_rgb)
            else: # Резервный вариант, если OpenCV не установлен
                 img_pil = Image.open(image_path)
            
            img_pil = correct_image_orientation(img_pil)
            
            img_label.update_idletasks()
            max_w, max_h = img_label.winfo_width(), img_label.winfo_height()
            img_pil.thumbnail((max_w - 10, max_h - 10), Image.Resampling.LANCZOS)
            
            photo = ImageTk.PhotoImage(img_pil)
            img_label.config(image=photo)
            img_label.image = photo
        except Exception as e:
            img_label.config(text=f"Не удалось загрузить изображение:\n{e}")

    def center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f'+{x}+{y}')
        
    def on_save(self):
        self.result = self.desc_text.get("1.0", tk.END).strip()
        self.destroy()
        
    def on_cancel(self):
        self.result = None
        self.destroy()

# --- Основной класс приложения ---

class AIPhotoDescriptor:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Photo Description Generator v2.4")
        self.root.geometry("1200x800")

        self.db_path = tk.StringVar()
        self.selected_llm = tk.StringVar(value="OpenAI")
        self.selected_language = tk.StringVar(value="Русский")
        
        self.process_mode = tk.StringVar(value="if_empty") # 'if_empty' или 'all'
        self.processed_mode = tk.StringVar(value="skip") # 'skip', 'reprocess', 'ask'
        self.apply_to_all_processed = None

        self.openai_client = None
        self.anthropic_client = None
        self.gemini_model = None
        self.processing = False

        self.update_queue = queue.Queue()
        self.init_llm_clients()
        
        # --- GUI ---
        self.create_widgets()
        self.process_queue()

    def create_widgets(self):
        main_pane = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        main_pane.pack(fill=tk.BOTH, expand=True)

        # Верхняя панель (настройки)
        top_frame = ttk.Frame(main_pane, padding="10")
        main_pane.add(top_frame, weight=1)
        self.create_process_tab(top_frame)
        
        # Нижняя панель (лог)
        log_container = ttk.LabelFrame(main_pane, text="Лог обработки", padding="10")
        main_pane.add(log_container, weight=2)
        
        self.log_text = scrolledtext.ScrolledText(log_container, width=100, height=10, wrap=tk.WORD)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        log_button_frame = ttk.Frame(log_container)
        log_button_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Button(log_button_frame, text="Копировать лог", command=self.copy_log_to_clipboard).pack()
        ttk.Button(log_button_frame, text="Очистить лог", command=lambda: self.log_text.delete(1.0, tk.END)).pack()

    def create_process_tab(self, parent):
        parent.columnconfigure(0, weight=1)

        # Настройки БД
        db_frame = ttk.LabelFrame(parent, text="База данных", padding="10")
        db_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        db_frame.columnconfigure(1, weight=1)
        ttk.Label(db_frame, text="Путь к БД:").grid(row=0, column=0, sticky="w")
        ttk.Entry(db_frame, textvariable=self.db_path).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(db_frame, text="Обзор...", command=self.browse_db).grid(row=0, column=2)

        # Настройки LLM
        settings_frame = ttk.LabelFrame(parent, text="Настройки", padding="10")
        settings_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        llm_frame = ttk.Frame(settings_frame)
        llm_frame.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(llm_frame, text="LLM:").pack(anchor="w")
        ttk.Combobox(llm_frame, textvariable=self.selected_llm, values=["OpenAI", "Anthropic", "Gemini"], state="readonly").pack()

        lang_frame = ttk.Frame(settings_frame)
        lang_frame.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(lang_frame, text="Язык:").pack(anchor="w")
        ttk.Combobox(lang_frame, textvariable=self.selected_language, values=["Русский", "English"], state="readonly").pack()

        # Режим обработки
        mode_frame = ttk.LabelFrame(settings_frame, text="Режим обработки", padding=10)
        mode_frame.pack(side=tk.LEFT, padx=(20, 0))
        ttk.Radiobutton(mode_frame, text="Только фото без описания", variable=self.process_mode, value="if_empty").pack(anchor="w")
        ttk.Radiobutton(mode_frame, text="Все фото в базе", variable=self.process_mode, value="all").pack(anchor="w")

        processed_frame = ttk.LabelFrame(settings_frame, text="Уже обработанные", padding=10)
        processed_frame.pack(side=tk.LEFT, padx=20)
        ttk.Radiobutton(processed_frame, text="Пропускать", variable=self.processed_mode, value="skip").pack(anchor="w")
        ttk.Radiobutton(processed_frame, text="Обрабатывать заново", variable=self.processed_mode, value="reprocess").pack(anchor="w")
        ttk.Radiobutton(processed_frame, text="Спрашивать", variable=self.processed_mode, value="ask").pack(anchor="w")

        # Управление
        control_frame = ttk.LabelFrame(parent, text="Управление", padding="10")
        control_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        
        self.process_button = ttk.Button(control_frame, text="Начать обработку", command=self.start_processing, style="Accent.TButton")
        self.process_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = ttk.Button(control_frame, text="Остановить", command=self.stop_processing, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)

        self.toggle_rename_button = ttk.Button(control_frame, text="Обновить имена файлов", command=self.toggle_rename_frame)
        self.toggle_rename_button.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="Выход", command=self.root.destroy).pack(side=tk.RIGHT, padx=5)
        
        # Прогресс
        progress_frame = ttk.Frame(parent)
        progress_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
        progress_frame.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(progress_frame, orient='horizontal', mode='determinate')
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.progress_label = ttk.Label(progress_frame, text="0 / 0")
        self.progress_label.grid(row=0, column=1, padx=10)

        # Панель переименования
        self.rename_frame = ttk.LabelFrame(parent, text="Переименование файлов", padding="10")
        self.rename_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        self.rename_dest_dir = tk.StringVar()
        ttk.Label(self.rename_frame, text="Директория для файлов с новыми именами:").grid(row=0, column=0, sticky=tk.W, pady=2)
        rename_entry_frame = ttk.Frame(self.rename_frame)
        rename_entry_frame.grid(row=1, column=0, sticky=tk.EW, pady=2)
        ttk.Entry(rename_entry_frame, textvariable=self.rename_dest_dir, width=80).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))
        ttk.Button(rename_entry_frame, text="Обзор...", command=self.browse_rename_dest).pack(side=tk.LEFT)
        self.rename_frame.columnconfigure(0, weight=1)
        
        self.start_rename_button = ttk.Button(self.rename_frame, text="Начать переименование", command=self.start_renaming_process, style="Accent.TButton")
        self.start_rename_button.grid(row=2, column=0, pady=(10,0), sticky=tk.W)
        
        self.rename_frame.grid_remove() # Скрываем по умолчанию

    def process_queue(self):
        try:
            while True:
                action, data = self.update_queue.get_nowait()
                if action == 'log':
                    self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {data}\n")
                    self.log_text.see(tk.END)
                elif action == 'progress':
                    current, total = data
                    self.progress_bar['value'] = (current / total) * 100
                    self.progress_label.config(text=f"{current} / {total}")
                elif action == 'show_processed_dialog':
                    dialog_res, apply_all = self.show_processed_dialog_main(data)
                    self.apply_to_all_processed = dialog_res if apply_all else None
                elif action == 'show_edit_dialog':
                    self.show_edit_dialog_main(data)
                elif action == 'task_finished':
                    self.process_button.config(state=tk.NORMAL)
                    self.toggle_rename_button.config(state=tk.NORMAL)
                    self.start_rename_button.config(state=tk.NORMAL)
                    self.stop_button.config(state=tk.DISABLED)

        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)

    def browse_db(self):
        path = filedialog.askopenfilename(filetypes=[("SQLite Database", "*.db")])
        if path:
            self.db_path.set(path)
            self.update_database_schema()

    def update_database_schema(self):
        db = self.db_path.get()
        if not db: return
        try:
            with sqlite3.connect(db) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(images)")
                columns = [info[1] for info in cursor.fetchall()]
                if 'ai_short_description' not in columns:
                    cursor.execute('ALTER TABLE images ADD COLUMN ai_short_description TEXT')
                    self.update_queue.put(('log', "В БД добавлена колонка 'ai_short_description'."))
                if 'ai_long_description' not in columns:
                    cursor.execute('ALTER TABLE images ADD COLUMN ai_long_description TEXT')
                    self.update_queue.put(('log', "В БД добавлена колонка 'ai_long_description'."))
                if 'ai_processed_date' not in columns:
                    cursor.execute('ALTER TABLE images ADD COLUMN ai_processed_date TEXT')
                if 'ai_llm_used' not in columns:
                    cursor.execute('ALTER TABLE images ADD COLUMN ai_llm_used TEXT')
                if 'ai_language' not in columns:
                    cursor.execute('ALTER TABLE images ADD COLUMN ai_language TEXT')
                conn.commit()
        except sqlite3.Error as e:
            messagebox.showerror("Ошибка БД", f"Не удалось обновить схему БД: {e}")

    def init_llm_clients(self):
        config = configparser.ConfigParser()
        if os.path.exists("keys-ai.ini"):
            config.read("keys-ai.ini")
            if openai and 'OpenAI' in config and 'api_key' in config['OpenAI']:
                openai.api_key = config['OpenAI']['api_key']
                self.openai_client = openai
            if anthropic and 'Anthropic' in config and 'api_key' in config['Anthropic']:
                self.anthropic_client = anthropic.Anthropic(api_key=config['Anthropic']['api_key'])
            if genai and 'Gemini' in config and 'api_key' in config['Gemini']:
                genai.configure(api_key=config['Gemini']['api_key'])
                self.gemini_model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.update_queue.put(('log', "Файл 'keys-ai.ini' не найден. LLM сервисы будут недоступны."))

    def start_processing(self):
        if not self.db_path.get() or not os.path.exists(self.db_path.get()):
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочую базу данных.")
            return

        self.process_button.config(state=tk.DISABLED)
        self.toggle_rename_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        self.processing = True
        self.apply_to_all_processed = None
        self.update_queue.put(('log', "Начало обработки..."))
        threading.Thread(target=self.process_images_thread, daemon=True).start()

    def stop_processing(self):
        self.update_queue.put(('log', "Остановка обработки..."))
        self.processing = False

    def process_images_thread(self):
        mode = self.process_mode.get()
        query = 'SELECT id, filepath FROM images'
        if mode == 'if_empty':
            query += ' WHERE ai_short_description IS NULL OR ai_short_description = ""'
            
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                images_to_process = cursor.execute(query).fetchall()

            total = len(images_to_process)
            self.update_queue.put(('progress', (0, total)))
            self.update_queue.put(('log', f"Найдено для обработки: {total} изображений."))

            for i, image_rec in enumerate(images_to_process):
                if not self.processing:
                    self.update_queue.put(('log', "Обработка прервана пользователем."))
                    break
                
                image_id, image_path = image_rec
                self.update_queue.put(('progress', (i, total)))
                
                if not os.path.exists(image_path):
                    self.update_queue.put(('log', f"Файл не найден, пропуск: {image_path}"))
                    continue

                existing_desc, _ = self.is_image_processed(image_id)
                if existing_desc:
                    decision = self.apply_to_all_processed or self.processed_mode.get()
                    if decision == 'skip':
                        self.update_queue.put(('log', f"Пропуск (уже обработано): {os.path.basename(image_path)}"))
                        continue
                    if decision == 'ask':
                        dialog_event = threading.Event()
                        self.update_queue.put(('show_processed_dialog', (image_path, existing_desc, dialog_event)))
                        dialog_event.wait()
                        decision = self.apply_to_all_processed or 'skip'
                    
                    if decision == 'cancel': break
                    if decision == 'skip': continue
                
                persons = self.get_persons_for_image(image_id)
                dogs = self.get_dogs_for_image(image_id)
                
                description_data = self.generate_description(image_path, persons, dogs)

                if description_data:
                    short_desc = description_data.get('short', '')
                    long_desc = description_data.get('long', '')

                    dialog_event = threading.Event()
                    dialog_res = {}
                    self.update_queue.put(('show_edit_dialog', (image_path, short_desc, dialog_event, dialog_res)))
                    dialog_event.wait()

                    final_desc = dialog_res.get('result')
                    if final_desc is not None:
                        with sqlite3.connect(self.db_path.get()) as conn_write:
                             conn_write.cursor().execute("""
                                UPDATE images SET ai_short_description=?, ai_long_description=?, ai_processed_date=?, ai_llm_used=?, ai_language=? WHERE id=?
                             """, (final_desc, long_desc, datetime.now().isoformat(), self.selected_llm.get(), self.selected_language.get(), image_id))
                             conn_write.commit()
                        self.update_queue.put(('log', f"Сохранено описание для {os.path.basename(image_path)}"))
                    else:
                        self.update_queue.put(('log', f"Обработка отменена для {os.path.basename(image_path)}"))
                
                self.update_queue.put(('progress', (i + 1, total)))
            
            self.update_queue.put(('log', "Обработка завершена."))
        except Exception as e:
            self.update_queue.put(('log', f"Критическая ошибка в потоке обработки: {e}\n{traceback.format_exc()}"))
        finally:
            self.processing = False
            self.update_queue.put(('task_finished', None))

    def show_processed_dialog_main(self, data):
        image_path, existing_desc, event = data
        dialog = ProcessedImagesDialog(self.root, image_path, existing_desc)
        self.root.wait_window(dialog)
        event.set()
        return dialog.result, dialog.apply_to_all.get()

    def show_edit_dialog_main(self, data):
        image_path, desc, event, res_dict = data
        dialog = EditDescriptionDialog(self.root, image_path, desc)
        self.root.wait_window(dialog)
        res_dict['result'] = dialog.result
        event.set()

    def get_persons_for_image(self, image_id):
        query = """
            SELECT DISTINCT p.short_name FROM persons p
            JOIN person_detections pd ON p.id = pd.person_id
            WHERE pd.image_id = ? AND p.is_known = 1
        """
        with sqlite3.connect(self.db_path.get()) as conn:
            return [row[0] for row in conn.cursor().execute(query, (image_id,)).fetchall()]

    def get_dogs_for_image(self, image_id):
        query = """
            SELECT DISTINCT d.name FROM dogs d
            JOIN dog_detections dd ON d.id = dd.dog_id
            WHERE dd.image_id = ? AND d.is_known = 1
        """
        with sqlite3.connect(self.db_path.get()) as conn:
            return [row[0] for row in conn.cursor().execute(query, (image_id,)).fetchall()]

    def is_image_processed(self, image_id):
        with sqlite3.connect(self.db_path.get()) as conn:
            res = conn.cursor().execute(
                'SELECT ai_short_description, ai_long_description FROM images WHERE id = ?', (image_id,)
            ).fetchone()
            if res and (res[0] or res[1]):
                return res[0], res[1]
            return None, None

    def get_language_specific_prompt(self, persons, dogs):
        lang = self.selected_language.get()
        if lang == "English":
            prompt = "Provide a short, one-sentence description for this photo for use as a filename. Then provide a long, detailed description. "
            if persons: prompt += f"Known people in the photo: {', '.join(persons)}. "
            if dogs: prompt += f"Known dogs in the photo: {', '.join(dogs)}. "
            prompt += "Format the output as a JSON object with two keys: 'short' and 'long'."
        else: # Русский
            prompt = "Предоставь краткое описание для этой фотографии из одного предложения, которое подойдет для имени файла. Затем предоставь длинное, детальное описание. "
            if persons: prompt += f"На фото есть известные люди: {', '.join(persons)}. "
            if dogs: prompt += f"На фото есть известные собаки: {', '.join(dogs)}. "
            prompt += "Отформатируй ответ в виде JSON-объекта с двумя ключами: 'short' и 'long'."
        return prompt

    def parse_llm_response(self, response_text):
        try:
            # Сначала пытаемся как чистый JSON
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Если не вышло, ищем JSON внутри ```...```
            match = re.search(r'```json\s*([\s\S]+?)\s*```', response_text)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            # Если и так не вышло, используем regex как последнюю попытку
            try:
                short = re.search(r'["\']short["\']\s*:\s*["\'](.*?)["\']', response_text, re.DOTALL).group(1)
                long = re.search(r'["\']long["\']\s*:\s*["\'](.*?)["\']', response_text, re.DOTALL).group(1)
                return {'short': short, 'long': long}
            except AttributeError:
                return None

    def generate_description_openai(self, base64_image, prompt):
        if not self.openai_client: return None
        response = self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]}],
            max_tokens=500
        )
        return self.parse_llm_response(response.choices[0].message.content)

    def generate_description_anthropic(self, base64_image, prompt):
        if not self.anthropic_client: return None
        response = self.anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64_image}},
                {"type": "text", "text": prompt}
            ]}]
        )
        return self.parse_llm_response(response.content[0].text)

    def generate_description_gemini(self, pil_image, prompt):
        if not self.gemini_model: return None
        response = self.gemini_model.generate_content([prompt, pil_image])
        return self.parse_llm_response(response.text)

    def generate_description(self, image_path, persons, dogs):
        base64_image = get_image_base64(image_path)
        if not base64_image:
            self.update_queue.put(('log', f"Не удалось закодировать изображение: {os.path.basename(image_path)}"))
            return None
            
        prompt = self.get_language_specific_prompt(persons, dogs)
        llm = self.selected_llm.get()
        
        try:
            self.update_queue.put(('log', f"Отправка запроса к {llm} для {os.path.basename(image_path)}..."))
            if llm == "OpenAI":
                return self.generate_description_openai(base64_image, prompt)
            elif llm == "Anthropic":
                return self.generate_description_anthropic(base64_image, prompt)
            elif llm == "Gemini":
                with Image.open(image_path) as img:
                    return self.generate_description_gemini(img, prompt)
        except Exception as e:
            self.update_queue.put(('log', f"Ошибка API {llm}: {e}"))
            return None

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
        db_dir = os.path.dirname(self.db_path.get())
        parent_dir = os.path.dirname(db_dir)
        # Ищем первую попавшуюся директорию с фото
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                res = conn.cursor().execute("SELECT filepath FROM images LIMIT 1").fetchone()
                if res:
                    image_dir = os.path.dirname(res[0])
                    # Предлагаем создать папку 'New Names' рядом с папкой с фото
                    dest_dir = os.path.join(os.path.dirname(image_dir), "New Names")
                    self.rename_dest_dir.set(dest_dir)
                    self.update_queue.put(('log', f"Предложена директория для переименования: {dest_dir}"))
                    return
        except Exception as e:
            self.update_queue.put(('log', f"Ошибка при определении пути по умолчанию: {e}"))
            
        # Если не получилось, предлагаем папку рядом с БД
        dest_dir = os.path.join(parent_dir, "Renamed Photos")
        self.rename_dest_dir.set(dest_dir)
        self.update_queue.put(('log', f"Предложена директория для переименования: {dest_dir}"))

    def browse_rename_dest(self):
        path = filedialog.askdirectory()
        if path:
            self.rename_dest_dir.set(path)

    def start_renaming_process(self):
        if not self.db_path.get() or not os.path.exists(self.db_path.get()):
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочую базу данных.")
            return
        if not self.rename_dest_dir.get():
            messagebox.showwarning("Предупреждение", "Выберите директорию для переименованных файлов.")
            return
        
        dest_path = self.rename_dest_dir.get()
        if not os.path.exists(dest_path):
            try:
                os.makedirs(dest_path)
            except OSError as e:
                messagebox.showerror("Ошибка", f"Не удалось создать директорию: {e}")
                return
        
        self.process_button.config(state=tk.DISABLED)
        self.toggle_rename_button.config(state=tk.DISABLED)
        self.start_rename_button.config(state=tk.DISABLED)
        
        self.update_queue.put(('log', "Начало переименования..."))
        threading.Thread(target=self.renaming_thread, daemon=True).start()

    def renaming_thread(self):
        query = 'SELECT filepath, ai_short_description FROM images WHERE ai_short_description IS NOT NULL AND ai_short_description != ""'
        dest_dir = self.rename_dest_dir.get()
        
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                images_to_rename = conn.cursor().execute(query).fetchall()

            total = len(images_to_rename)
            self.update_queue.put(('progress', (0, total)))
            self.update_queue.put(('log', f"Найдено для переименования: {total} изображений."))

            for i, (original_path, description) in enumerate(images_to_rename):
                self.update_queue.put(('progress', (i, total)))
                if not os.path.exists(original_path):
                    self.update_queue.put(('log', f"Файл не найден, пропуск: {original_path}"))
                    continue

                file_extension = Path(original_path).suffix
                
                # Создаем имя файла
                new_filename_base = sanitize_filename(transliterate(description))
                new_filename = f"{new_filename_base}{file_extension}"
                new_filepath = os.path.join(dest_dir, new_filename)
                
                # Обработка конфликтов имен
                counter = 2
                while os.path.exists(new_filepath):
                    new_filename = f"{new_filename_base}_({counter}){file_extension}"
                    new_filepath = os.path.join(dest_dir, new_filename)
                    counter += 1
                
                try:
                    shutil.copy2(original_path, new_filepath)
                    self.update_queue.put(('log', f"Скопировано: {os.path.basename(original_path)} -> {new_filename}"))
                except Exception as e:
                    self.update_queue.put(('log', f"Ошибка копирования файла {os.path.basename(original_path)}: {e}"))
                
                self.update_queue.put(('progress', (i + 1, total)))
            
            self.update_queue.put(('log', "Переименование завершено."))
            
        except Exception as e:
            self.update_queue.put(('log', f"Критическая ошибка в потоке переименования: {e}\n{traceback.format_exc()}"))
        finally:
            self.update_queue.put(('task_finished', None))

    def copy_log_to_clipboard(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_text.get(1.0, tk.END))
        self.update_queue.put(('log', "Лог скопирован в буфер обмена."))

def main():
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        style.theme_use('clam') 
        style.configure("Accent.TButton", foreground="white", background="#0078D7")
    except tk.TclError:
        print("Тема 'clam' не найдена, используется тема по умолчанию.")
        
    app = AIPhotoDescriptor(root)
    root.mainloop()

if __name__ == "__main__":
    main()