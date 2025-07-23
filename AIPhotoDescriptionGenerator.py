# -*- coding: utf-8 -*-
"""
AI Photo Description Generator v3.27 (UI/UX Refinements)
This program generates photo descriptions using an LLM and then renames the files.

Version: 3.27
- Fixed a bug where the progress bar would not complete to 100% if some
  interactive operations were skipped by the user. A final update is now sent.
- The file renaming UI has been moved from a separate dialog back into the
  main window for a more integrated experience, appearing below the progress bar.
- The layout of the renaming controls has been improved for better visibility.
- Minor visual adjustments to panel labels.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sqlite3
import base64
from io import BytesIO
from PIL import Image, ImageTk
import threading
import queue
import json
import re
import configparser
from datetime import datetime
import shutil
from pathlib import Path
import traceback

# Optional library imports
try:
    import openai
except ImportError: openai = None
try:
    import anthropic
except ImportError: anthropic = None
try:
    import google.generativeai as genai
except ImportError: genai = None
try:
    import cv2
    import numpy as np
except ImportError: cv2, np = None, None

# --- Internationalization (i18n) ---
LANGUAGES = {
    'EN': {
        'version': "v3.27",
        'window_title': "AI Photo Description Generator",
        'db_frame_title': "Database", 'db_path_label': "DB Path:", 'browse_button': "Browse...",
        'settings_frame_title': "Settings", 'llm_label': "LLM:", 'filename_language_label': "Description Language:",
        'process_frame_title': "Process", 'process_mode_if_empty': "Only photos without description", 'process_mode_all': "All photos",
        'interaction_frame_title': "Interaction Mode", 'interaction_batch': "Batch processing (auto-save)", 'interaction_interactive': "One by one (interactive)",
        'control_frame_title': "Controls", 'start_button': "Start Processing", 'stop_button': "Stop", 'rename_button': "Rename Files", 'exit_button': "Exit",
        'rename_frame_title': "File Renaming", 'rename_dest_dir_label': "Directory for new files:", 'start_rename_button': "Start Renaming",
        'log_frame_title': "  Processing Log", 
        'copy_log_button': "📋", 'log_copied': "Log copied to clipboard.",
        'select_db_warning_title': "Warning", 'select_db_warning_msg': "Please select a working database first.",
        'select_rename_dir_warning_msg': "Please select a directory for the new files.",
        'dir_creation_error_title': "Error", 'dir_creation_error_msg': "Failed to create directory: {e}",
        'processing_started': "Starting processing...", 'processing_stopped': "Stopping processing...", 'processing_interrupted': "Processing interrupted by user.",
        'found_for_processing': "Found for processing: {total} images.", 'file_not_found_skip': "File not found, skipping: {path}",
        'saving_description_for': "Saved description for {filename}", 'processing_cancelled_for': "Processing cancelled for {filename}",
        'processing_finished': "Processing finished.", 'critical_error_thread': "Critical error in processing thread: {e}\n{traceback}",
        'db_schema_updated': "DB schema updated: Column '{col}' added.", 'db_error': "DB Error", 'db_schema_update_failed': "Failed to update DB schema: {e}",
        'keys_file_not_found': "'keys-ai.ini' file not found. LLM services will be unavailable.",
        'client_not_initialized': "ERROR: {llm} client is not initialized. Check 'keys-ai.ini' or library installation.",
        'sending_request_to': "Sending request to {llm} for {filename}...", 'api_error': "API Error {llm}: {e}",
        'image_encode_failed': "Failed to encode image: {filename}", 'propose_rename_dir': "Proposed directory for renaming: {dest_dir}",
        'propose_rename_dir_error': "Error determining default path: {e}", 'renaming_started': "Starting renaming...",
        'found_for_renaming': "Found for renaming: {total} images.", 'copied_file': "Copied: {original} -> {new}",
        'copy_error': "Error copying file {original}: {e}", 'renaming_finished': "Renaming finished.",
        'critical_error_renaming_thread': "Critical error in renaming thread: {e}\n{traceback}",
        'edit_dialog_title': "Edit AI Description", 'interactive_dialog_title': "Review Existing Description",
        'edit_dialog_image_frame': "Image", 'edit_dialog_short_desc_label': "Short Description (for filename):",
        'edit_dialog_long_desc_label': "Long Description:", 'edit_dialog_save_btn': "Save", 'edit_dialog_cancel_btn': "Skip",
        'image_load_fail': "Failed to load image:\n{e}",
        'interactive_dialog_reprocess_btn': "Get New Description (LLM)", 'interactive_dialog_cancel_all_btn': "Cancel All"
    },
    'RU': {
        'version': "v3.27",
        'window_title': "Генератор описаний фото",
        'db_frame_title': "База данных", 'db_path_label': "Путь к БД:", 'browse_button': "Обзор...",
        'settings_frame_title': "Настройки", 'llm_label': "LLM:", 'filename_language_label': "Язык описаний:",
        'process_frame_title': "Обрабатывать", 'process_mode_if_empty': "Только фото без описания", 'process_mode_all': "Все фото",
        'interaction_frame_title': "Режим взаимодействия", 'interaction_batch': "Пакетная обработка (автосохранение)", 'interaction_interactive': "По одному (интерактивно)",
        'control_frame_title': "Управление", 'start_button': "Начать обработку", 'stop_button': "Остановить", 'rename_button': "Переименовать файлы", 'exit_button': "Выход",
        'rename_frame_title': "Переименование файлов", 'rename_dest_dir_label': "Директория для новых файлов:", 'start_rename_button': "Начать переименование",
        'log_frame_title': "  Лог обработки", 
        'copy_log_button': "📋", 'log_copied': "Лог скопирован в буфер обмена.",
        'select_db_warning_title': "Предупреждение", 'select_db_warning_msg': "Сначала выберите рабочую базу данных.",
        'select_rename_dir_warning_msg': "Выберите директорию для новых файлов.",
        'dir_creation_error_title': "Ошибка", 'dir_creation_error_msg': "Не удалось создать директорию: {e}",
        'processing_started': "Начало обработки...", 'processing_stopped': "Остановка обработки...", 'processing_interrupted': "Обработка прервана пользователем.",
        'found_for_processing': "Найдено для обработки: {total} изображений.", 'file_not_found_skip': "Файл не найден, пропуск: {path}",
        'saving_description_for': "Сохранено описание для {filename}", 'processing_cancelled_for': "Обработка отменена для {filename}",
        'processing_finished': "Обработка завершена.", 'critical_error_thread': "Критическая ошибка в потоке обработки: {e}\n{traceback}",
        'db_schema_updated': "В БД добавлена колонка '{col}'.", 'db_error': "Ошибка БД", 'db_schema_update_failed': "Не удалось обновить схему БД: {e}",
        'keys_file_not_found': "Файл 'keys-ai.ini' не найден. LLM сервисы будут недоступны.",
        'client_not_initialized': "ОШИБКА: Клиент {llm} не инициализирован. Проверьте 'keys-ai.ini' или установку библиотеки.",
        'sending_request_to': "Отправка запроса к {llm} для {filename}...", 'api_error': "Ошибка API {llm}: {e}",
        'image_encode_failed': "Не удалось закодировать изображение: {filename}", 'propose_rename_dir': "Предложена директория для переименования: {dest_dir}",
        'propose_rename_dir_error': "Ошибка при определении пути по умолчанию: {e}", 'renaming_started': "Начало переименования...",
        'found_for_renaming': "Найдено для переименования: {total} изображений.", 'copied_file': "Скопировано: {original} -> {new}",
        'copy_error': "Ошибка копирования файла {original}: {e}", 'renaming_finished': "Переименование завершено.",
        'critical_error_renaming_thread': "Критическая ошибка в потоке переименования: {e}\n{traceback}",
        'edit_dialog_title': "Редактирование описания от LLM", 'interactive_dialog_title': "Просмотр существующего описания",
        'edit_dialog_image_frame': "Изображение", 'edit_dialog_short_desc_label': "Краткое описание (для имени файла):",
        'edit_dialog_long_desc_label': "Подробное описание:", 'edit_dialog_save_btn': "Сохранить", 'edit_dialog_cancel_btn': "Пропустить",
        'image_load_fail': "Не удалось загрузить изображение:\n{e}",
        'interactive_dialog_reprocess_btn': "Запросить новое описание (LLM)", 'interactive_dialog_cancel_all_btn': "Отменить всё"
    },
}

# --- Helper Functions ---
def correct_image_orientation(img: Image.Image) -> Image.Image:
    try:
        exif = img.getexif(); orientation_tag = 274
        if orientation_tag in exif:
            orientation = exif[orientation_tag]
            if orientation == 3: img = img.rotate(180, expand=True)
            elif orientation == 6: img = img.rotate(270, expand=True)
            elif orientation == 8: img = img.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError): pass
    return img

def get_image_base64(image_path, max_size=(2048, 2048)):
    try:
        with Image.open(image_path) as img:
            img = correct_image_orientation(img); img.thumbnail(max_size, Image.Resampling.LANCZOS)
            buffered = BytesIO(); img.save(buffered, format="JPEG")
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e: print(f"Error encoding image {image_path}: {e}"); return None

def transliterate(name):
    dic = {'ь':'', 'ъ':'', 'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e', 'ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n', 'о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h', 'ц':'c','ч':'ch','ш':'sh','щ':'shch','ы':'y','э':'e','ю':'yu','я':'ya'}
    return "".join(map(lambda x: dic.get(x, x), name.lower()))

def sanitize_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', "", name); name = re.sub(r'\s+', '_', name)
    return name

# --- Base Dialog Class ---
class BaseDialog(tk.Toplevel):
    def __init__(self, parent, app_context, title):
        super().__init__(parent)
        self.result = None; self.parent_app = app_context; self.lang = self.parent_app.lang
        self.title(title); self.geometry("1000x700"); self.transient(parent); self.grab_set(); self.protocol("WM_DELETE_WINDOW", self.on_cancel)
    
    def create_widgets(self, image_path, short_desc, long_desc):
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL); main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        img_container = ttk.Frame(main_pane); main_pane.add(img_container, weight=1)
        img_frame = ttk.LabelFrame(img_container, text=self.lang['edit_dialog_image_frame']); img_frame.pack(fill=tk.BOTH, expand=True)
        img_label = ttk.Label(img_frame); img_label.pack(expand=True, fill=tk.BOTH, padx=5, pady=5); self.load_image(image_path, img_label)
        desc_container = ttk.Frame(main_pane); main_pane.add(desc_container, weight=1)
        ttk.Label(desc_container, text=self.lang['edit_dialog_short_desc_label']).pack(anchor=tk.W, pady=(0, 2))
        self.short_desc_var = tk.StringVar(value=short_desc)
        ttk.Entry(desc_container, textvariable=self.short_desc_var, width=80).pack(fill=tk.X, pady=(0, 10))
        ttk.Label(desc_container, text=self.lang['edit_dialog_long_desc_label']).pack(anchor=tk.W, pady=(5, 2))
        self.long_text = scrolledtext.ScrolledText(desc_container, wrap=tk.WORD, height=10); self.long_text.pack(fill=tk.BOTH, expand=True)
        self.long_text.insert('1.0', long_desc)
        self.button_frame = ttk.Frame(self); self.button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
    def load_image(self, image_path, img_label):
        try:
            if cv2 and np:
                 img_cv = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                 img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB); img_pil = Image.fromarray(img_rgb)
            else: img_pil = Image.open(image_path)
            img_pil = correct_image_orientation(img_pil); img_pil.thumbnail((400, 400), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img_pil); img_label.config(image=photo); img_label.image = photo
        except Exception as e: img_label.config(text=self.lang['image_load_fail'].format(e=e))

    def center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2); y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f'+{x}+{y}')
    
    def on_save(self): self.result = {'status': 'save', 'data': {'short': self.short_desc_var.get().strip(), 'long': self.long_text.get('1.0', tk.END).strip()}}; self.destroy()
    def on_reprocess(self): self.result = {'status': 'reprocess'}; self.destroy()
    def on_cancel(self): self.result = None; self.destroy()
    def on_cancel_all(self): self.result = {'status': 'cancel_all'}; self.destroy()

# --- Dialog Implementations ---
class EditDescriptionDialog(BaseDialog):
    def __init__(self, parent, app_context, image_path, short_desc, long_desc):
        super().__init__(parent, app_context, app_context.lang['edit_dialog_title'])
        self.create_widgets(image_path, short_desc, long_desc)
        ttk.Button(self.button_frame, text=self.lang['edit_dialog_cancel_btn'], command=self.on_cancel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(self.button_frame, text=self.lang['edit_dialog_save_btn'], command=self.on_save, style="Accent.TButton").pack(side=tk.RIGHT)
        self.center_window()

class InteractiveDialog(BaseDialog):
    def __init__(self, parent, app_context, image_path, short_desc, long_desc):
        super().__init__(parent, app_context, app_context.lang['interactive_dialog_title'])
        self.create_widgets(image_path, short_desc, long_desc)
        ttk.Button(self.button_frame, text=self.lang['interactive_dialog_cancel_all_btn'], command=self.on_cancel_all).pack(side=tk.RIGHT, padx=5)
        ttk.Button(self.button_frame, text=self.lang['interactive_dialog_reprocess_btn'], command=self.on_reprocess).pack(side=tk.RIGHT, padx=5)
        ttk.Button(self.button_frame, text=self.lang['edit_dialog_save_btn'], command=self.on_save, style="Accent.TButton").pack(side=tk.RIGHT)
        self.center_window()

# --- Main Application Class ---
class AIPhotoDescriptor:
    def __init__(self, root):
        self.root = root; self.root.title("AI Photo Description Generator"); self.root.geometry("1200x900")
        self.ui_language = tk.StringVar(value="RU"); self.lang = LANGUAGES[self.ui_language.get()]
        self.db_path = tk.StringVar(); self.selected_llm = tk.StringVar(value="OpenAI"); self.selected_filename_language = tk.StringVar(value="Русский")
        self.process_target_mode = tk.StringVar(value="if_empty"); self.interaction_mode = tk.StringVar(value="interactive")
        self.rename_dest_dir = tk.StringVar()
        self.openai_client, self.anthropic_client, self.gemini_model = None, None, None; self.processing = False
        self.update_queue = queue.Queue()
        self.init_llm_clients(); self.create_widgets(); self.process_queue(); self.update_ui_language()

    def create_widgets(self):
        header_frame = ttk.Frame(self.root, padding=(10, 5, 10, 0)); header_frame.pack(fill=tk.X)
        self.version_label = ttk.Label(header_frame); self.version_label.pack(side=tk.RIGHT)
        lang_switcher = ttk.Combobox(header_frame, textvariable=self.ui_language, values=['EN', 'RU'], state="readonly", width=5)
        lang_switcher.pack(side=tk.RIGHT, padx=10); lang_switcher.bind("<<ComboboxSelected>>", self.update_ui_language)
        ttk.Label(header_frame, text="Language:").pack(side=tk.RIGHT)
        
        main_notebook = ttk.Notebook(self.root); main_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.process_tab = ttk.Frame(main_notebook); main_notebook.add(self.process_tab, text="  Обработка  ")
        self.create_process_tab(self.process_tab)

    def create_process_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(4, weight=1) # Make row with log/image panes expandable
        
        # --- Settings, Controls, Progress ---
        self.db_frame = ttk.LabelFrame(parent, padding="10"); self.db_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        self.db_frame.columnconfigure(1, weight=1)
        self.db_path_label = ttk.Label(self.db_frame); self.db_path_label.grid(row=0, column=0, sticky="w")
        ttk.Entry(self.db_frame, textvariable=self.db_path).grid(row=0, column=1, sticky="ew", padx=5)
        self.browse_db_button = ttk.Button(self.db_frame, command=self.browse_db); self.browse_db_button.grid(row=0, column=2)

        self.settings_frame = ttk.LabelFrame(parent, padding="10"); self.settings_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        settings_left = ttk.Frame(self.settings_frame); settings_left.pack(side=tk.LEFT, fill=tk.Y, anchor='n', padx=(0, 20))
        settings_right = ttk.Frame(self.settings_frame); settings_right.pack(side=tk.LEFT, fill=tk.Y, anchor='n')
        llm_frame = ttk.Frame(settings_left); llm_frame.pack(anchor="w", pady=(0, 10))
        self.llm_label = ttk.Label(llm_frame); self.llm_label.pack(anchor="w")
        self.llm_combo = ttk.Combobox(llm_frame, textvariable=self.selected_llm, state="readonly", width=15); self.llm_combo.pack(anchor="w")
        lang_frame = ttk.Frame(settings_left); lang_frame.pack(anchor="w")
        self.filename_language_label = ttk.Label(lang_frame); self.filename_language_label.pack(anchor="w")
        ttk.Combobox(lang_frame, textvariable=self.selected_filename_language, values=["Русский", "English"], state="readonly").pack(anchor="w")
        self.process_frame = ttk.LabelFrame(settings_right, padding=10); self.process_frame.pack(anchor="w", fill=tk.X)
        self.process_rb1 = ttk.Radiobutton(self.process_frame, variable=self.process_target_mode, value="if_empty"); self.process_rb1.pack(anchor="w")
        self.process_rb2 = ttk.Radiobutton(self.process_frame, variable=self.process_target_mode, value="all"); self.process_rb2.pack(anchor="w")
        self.interaction_frame = ttk.LabelFrame(settings_right, padding=10); self.interaction_frame.pack(anchor="w", fill=tk.X, pady=(10,0))
        self.interact_rb1 = ttk.Radiobutton(self.interaction_frame, variable=self.interaction_mode, value="batch"); self.interact_rb1.pack(anchor="w")
        self.interact_rb2 = ttk.Radiobutton(self.interaction_frame, variable=self.interaction_mode, value="interactive"); self.interact_rb2.pack(anchor="w")

        self.control_frame = ttk.LabelFrame(parent, padding="10"); self.control_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        self.process_button = ttk.Button(self.control_frame, command=self.start_processing, style="Accent.TButton"); self.process_button.pack(side=tk.LEFT, padx=5)
        self.stop_button = ttk.Button(self.control_frame, command=self.stop_processing, state=tk.DISABLED); self.stop_button.pack(side=tk.LEFT, padx=5)
        self.toggle_rename_button = ttk.Button(self.control_frame, command=self.toggle_rename_frame); self.toggle_rename_button.pack(side=tk.LEFT, padx=5)
        self.exit_button = ttk.Button(self.control_frame, command=self.root.destroy); self.exit_button.pack(side=tk.RIGHT, padx=5)
        
        progress_frame = ttk.Frame(parent); progress_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
        progress_frame.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(progress_frame, orient='horizontal', mode='determinate'); self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.progress_label = ttk.Label(progress_frame, text="0 / 0"); self.progress_label.grid(row=0, column=1, padx=10)

        # --- Renaming Frame (integrated into main window) ---
        self.rename_frame = ttk.LabelFrame(parent, padding="10"); self.rename_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=5)
        self.rename_frame.columnconfigure(0, weight=1)
        self.rename_dest_dir_label = ttk.Label(self.rename_frame); self.rename_dest_dir_label.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=2)
        ttk.Entry(self.rename_frame, textvariable=self.rename_dest_dir, width=80).grid(row=1, column=0, sticky=tk.EW, pady=2)
        self.browse_rename_button = ttk.Button(self.rename_frame, command=self.browse_rename_dest); self.browse_rename_button.grid(row=1, column=1, padx=5)
        self.start_rename_button = ttk.Button(self.rename_frame, command=self.start_renaming_process, style="Accent.TButton"); self.start_rename_button.grid(row=1, column=2)
        self.rename_frame.grid_remove() # Hidden by default
        
        # --- Log and Image Panes ---
        bottom_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL); bottom_pane.grid(row=5, column=0, sticky="nsew", padx=10, pady=10)
        parent.grid_rowconfigure(5, weight=1)

        log_container_wrapper = ttk.Frame(bottom_pane); bottom_pane.add(log_container_wrapper, weight=1)
        self.log_container = ttk.LabelFrame(log_container_wrapper, padding="10")
        self.log_container.pack(fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(self.log_container, width=100, height=10, wrap=tk.WORD); self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_button_frame = ttk.Frame(self.log_container); log_button_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        self.copy_log_button = ttk.Button(log_button_frame, command=self.copy_log_to_clipboard); self.copy_log_button.pack()

    def update_ui_language(self, event=None):
        self.lang = LANGUAGES[self.ui_language.get()]
        self.version_label.config(text=self.lang['version'])
        self.db_frame.config(text=self.lang['db_frame_title']); self.settings_frame.config(text=self.lang['settings_frame_title'])
        self.process_frame.config(text=self.lang['process_frame_title']); self.interaction_frame.config(text=self.lang['interaction_frame_title'])
        self.control_frame.config(text=self.lang['control_frame_title']); self.rename_frame.config(text=self.lang['rename_frame_title'])
        self.log_container.config(text=self.lang['log_frame_title'])
        self.db_path_label.config(text=self.lang['db_path_label']); self.llm_label.config(text=self.lang['llm_label'])
        self.filename_language_label.config(text=self.lang['filename_language_label']); self.rename_dest_dir_label.config(text=self.lang['rename_dest_dir_label'])
        self.browse_db_button.config(text=self.lang['browse_button']); self.process_button.config(text=self.lang['start_button'])
        self.stop_button.config(text=self.lang['stop_button']); self.toggle_rename_button.config(text=self.lang['rename_button'])
        self.exit_button.config(text=self.lang['exit_button']); self.copy_log_button.config(text=self.lang['copy_log_button'])
        self.browse_rename_button.config(text=self.lang['browse_button']); self.start_rename_button.config(text=self.lang['start_rename_button'])
        self.process_rb1.config(text=self.lang['process_mode_if_empty']); self.process_rb2.config(text=self.lang['process_mode_all'])
        self.interact_rb1.config(text=self.lang['interaction_batch']); self.interact_rb2.config(text=self.lang['interaction_interactive'])

    def process_queue(self):
        try:
            while True:
                action, data = self.update_queue.get_nowait()
                if action == 'log': self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {data}\n"); self.log_text.see(tk.END)
                elif action == 'progress':
                    current, total = data; self.progress_bar['value'] = (current / total) * 100 if total > 0 else 0; self.progress_label.config(text=f"{current} / {total}")
                elif action == 'show_edit_dialog': self.show_edit_dialog_main(data)
                elif action == 'show_interactive_dialog': self.show_interactive_dialog_main(data)
                elif action == 'task_finished':
                    self.process_button.config(state=tk.NORMAL); self.toggle_rename_button.config(state=tk.NORMAL); self.stop_button.config(state=tk.DISABLED)
        except queue.Empty: pass
        finally: self.root.after(100, self.process_queue)

    def browse_db(self):
        path = filedialog.askopenfilename(filetypes=[("SQLite Database", "*.db")])
        if path: self.db_path.set(path); self.update_database_schema()

    def update_database_schema(self):
        if not self.db_path.get(): return
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor(); cursor.execute("PRAGMA table_info(images)"); columns = [info[1] for info in cursor.fetchall()]
                for col in ['ai_short_description', 'ai_long_description', 'ai_processed_date', 'ai_llm_used', 'ai_language']:
                    if col not in columns: cursor.execute(f'ALTER TABLE images ADD COLUMN {col} TEXT'); self.update_queue.put(('log', self.lang['db_schema_updated'].format(col=col)))
                conn.commit()
        except sqlite3.Error as e: messagebox.showerror(self.lang['db_error'], self.lang['db_schema_update_failed'].format(e=e))

    def init_llm_clients(self):
        config = configparser.ConfigParser(); keys_file = "keys-ai.ini"; available_llms = []
        if not os.path.exists(keys_file): self.update_queue.put(('log', self.lang['keys_file_not_found'])); return
        config.read(keys_file)
        if 'Keys' in config:
            api_keys = config['Keys']
            if openai and 'OpenAI' in api_keys and api_keys.get('OpenAI'):
                try: self.openai_client = openai.OpenAI(api_key=api_keys['OpenAI']); available_llms.append('OpenAI')
                except Exception as e: self.update_queue.put(('log', f"OpenAI client init error: {e}"))
            if anthropic and 'ANTHROPIC' in api_keys and api_keys.get('ANTHROPIC'):
                try: self.anthropic_client = anthropic.Anthropic(api_key=api_keys['ANTHROPIC']); available_llms.append('Anthropic')
                except Exception as e: self.update_queue.put(('log', f"Anthropic client init error: {e}"))
            if genai and 'GEMINI' in api_keys and api_keys.get('GEMINI'):
                try: genai.configure(api_key=api_keys['GEMINI']); self.gemini_model = genai.GenerativeModel('gemini-1.5-flash'); available_llms.append('Gemini')
                except Exception as e: self.update_queue.put(('log', f"Gemini client init error: {e}"))
        else: self.update_queue.put(('log', "ERROR: Section [Keys] not found in 'keys-ai.ini'."))
        if hasattr(self, 'llm_combo'): self.llm_combo['values'] = available_llms; self.selected_llm.set(available_llms[0]) if available_llms else None

    def start_processing(self):
        if not self.db_path.get() or not os.path.exists(self.db_path.get()): messagebox.showwarning(self.lang['select_db_warning_title'], self.lang['select_db_warning_msg']); return
        self.process_button.config(state=tk.DISABLED); self.toggle_rename_button.config(state=tk.DISABLED); self.stop_button.config(state=tk.NORMAL)
        self.processing = True; self.update_queue.put(('log', self.lang['processing_started']))
        threading.Thread(target=self.process_images_thread, daemon=True).start()

    def stop_processing(self): self.update_queue.put(('log', self.lang['processing_stopped'])); self.processing = False

    def process_images_thread(self):
        total = 0
        try:
            mode = self.process_target_mode.get(); query = 'SELECT id, filepath FROM images ORDER BY filepath'
            if mode == 'if_empty': query = 'SELECT id, filepath FROM images WHERE (ai_short_description IS NULL OR ai_short_description = "") ORDER BY filepath'
            with sqlite3.connect(self.db_path.get()) as conn: images_to_process = conn.cursor().execute(query).fetchall()
            total = len(images_to_process)
            self.update_queue.put(('progress', (0, total))); self.update_queue.put(('log', self.lang['found_for_processing'].format(total=total)))
            for i, (image_id, image_path) in enumerate(images_to_process):
                if not self.processing: self.update_queue.put(('log', self.lang['processing_interrupted'])); break
                self.update_queue.put(('progress', (i, total))) # Progress before processing
                if not os.path.exists(image_path): self.update_queue.put(('log', self.lang['file_not_found_skip'].format(path=image_path))); continue
                
                short_d, long_d = self.get_existing_description(image_id)
                final_desc_dict = None
                
                if self.interaction_mode.get() == 'interactive':
                    if short_d and mode == 'all': # Interactive, has description, and processing all
                        dialog_event = threading.Event(); dialog_res = {}
                        self.update_queue.put(('show_interactive_dialog', (image_path, short_d, long_d, dialog_event, dialog_res)))
                        dialog_event.wait(); result = dialog_res.get('result')
                        if not result: continue # User skipped this image
                        if result['status'] == 'cancel_all': break
                        if result['status'] == 'save': final_desc_dict = result.get('data')
                        if result['status'] == 'reprocess': pass # Fall through
                    
                    if not short_d or (locals().get('result') and result['status'] == 'reprocess'): # No description OR user requested reprocess
                        persons = self.get_persons_for_image(image_id); dogs = self.get_dogs_for_image(image_id)
                        new_data = self.generate_description(image_path, persons, dogs)
                        if new_data:
                            dialog_event = threading.Event(); dialog_res = {}
                            self.update_queue.put(('show_edit_dialog', (image_path, new_data['short'], new_data['long'], dialog_event, dialog_res)))
                            dialog_event.wait(); edit_result = dialog_res.get('result')
                            if edit_result: final_desc_dict = edit_result.get('data')
                else: # Batch mode
                    persons = self.get_persons_for_image(image_id); dogs = self.get_dogs_for_image(image_id)
                    final_desc_dict = self.generate_description(image_path, persons, dogs)

                if final_desc_dict:
                    with sqlite3.connect(self.db_path.get()) as conn:
                        conn.cursor().execute("UPDATE images SET ai_short_description=?, ai_long_description=?, ai_processed_date=?, ai_llm_used=?, ai_language=? WHERE id=?",
                            (final_desc_dict['short'], final_desc_dict['long'], datetime.now().isoformat(), self.selected_llm.get(), self.selected_filename_language.get(), image_id))
                    self.update_queue.put(('log', self.lang['saving_description_for'].format(filename=os.path.basename(image_path))))
                elif locals().get('result') is None and self.interaction_mode.get() == 'interactive':
                    self.update_queue.put(('log', self.lang['processing_cancelled_for'].format(filename=os.path.basename(image_path))))
            
            if self.processing: self.update_queue.put(('log', self.lang['processing_finished']))
        except Exception as e: self.update_queue.put(('log', self.lang['critical_error_thread'].format(e=e, traceback=traceback.format_exc())))
        finally:
            self.update_queue.put(('progress', (total, total))) # Final progress update
            self.processing = False; self.update_queue.put(('task_finished', None))

    def show_edit_dialog_main(self, data):
        image_path, short, long, event, res_dict = data
        dialog = EditDescriptionDialog(self.root, self, image_path, short, long); self.root.wait_window(dialog); res_dict['result'] = dialog.result; event.set()
    def show_interactive_dialog_main(self, data):
        image_path, short, long, event, res_dict = data
        dialog = InteractiveDialog(self.root, self, image_path, short, long); self.root.wait_window(dialog); res_dict['result'] = dialog.result; event.set()

    def get_persons_for_image(self, image_id):
        with sqlite3.connect(self.db_path.get()) as conn: return [row[0] for row in conn.cursor().execute("SELECT DISTINCT p.short_name FROM persons p JOIN person_detections pd ON p.id = pd.person_id WHERE pd.image_id = ? AND p.is_known = 1", (image_id,)).fetchall()]
    def get_dogs_for_image(self, image_id):
        with sqlite3.connect(self.db_path.get()) as conn: return [row[0] for row in conn.cursor().execute("SELECT DISTINCT d.name FROM dogs d JOIN dog_detections dd ON d.id = dd.dog_id WHERE dd.image_id = ? AND d.is_known = 1", (image_id,)).fetchall()]
    def get_existing_description(self, image_id):
        with sqlite3.connect(self.db_path.get()) as conn: return conn.cursor().execute("SELECT ai_short_description, ai_long_description FROM images WHERE id = ?", (image_id,)).fetchone() or (None, None)

    def get_language_specific_prompt(self, person_names, dog_names):
        lang_code = 'ru' if self.selected_filename_language.get() == 'Русский' else 'en'
        if lang_code == "ru":
            base_prompt = ("Проанализируй это изображение и предоставь описания на русском языке.\n\n"
                           "Ты ДОЛЖЕН ответить ТОЛЬКО JSON объектом со структурой:\n"
                           "{\"short\": \"краткое описание на русском\", \"long\": \"подробное описание изображения на русском\"}\n\n"
                           "Правила для краткого описания:\n- Краткое описание сцены на русском языке.\n- Используй пробелы между словами (НЕ подчеркивания).\n"
                           "- Максимум 100 символов.\n- На правильном русском языке.\n- Это описание будет использовано как имя файла, поэтому оно должно быть лаконичным и информативным.\n\n"
                           "Дополнительно, если на фото изображено известное место или произведение искусства, постарайся указать его название. "
                           "Для произведений искусства, если возможно, укажи автора и место хранения (музей). "
                           "Эту информацию кратко отрази в коротком описании и более подробно в длинном.")
        else: # English
            base_prompt = ("Analyze this image and provide descriptions in English.\n\n"
                           "You MUST respond with ONLY a JSON object with the structure:\n"
                           "{\"short\": \"short description in English\", \"long\": \"detailed description of the image in English\"}\n\n"
                           "Rules for the short description:\n- Brief description of the scene in English.\n- Use spaces between words (NOT underscores).\n"
                           "- Maximum 100 characters.\n- In proper English.\n- This description will be used as a filename, so it should be concise and informative.\n\n"
                           "Additionally, if the photo depicts a famous place or a work of art, try to identify it. "
                           "For artwork, if possible, specify the artist and its location (museum). "
                           "Briefly include this information in the short description and provide more detail in the long one.")
        if person_names:
            names_str = ", ".join(person_names); base_prompt += f"\n\nЛюди на этом изображении: {names_str}\nВАЖНО: Включи эти имена в свои описания." if lang_code == "ru" else f"\n\nPeople in this image: {names_str}\nIMPORTANT: Include these names in your descriptions."
        if dog_names:
            dogs_str = ", ".join(dog_names); base_prompt += f"\n\nСобаки на этом изображении: {dogs_str}\nВАЖНО: Включи эти клички собак в свои описания." if lang_code == "ru" else f"\n\nDogs in this image: {dogs_str}\nIMPORTANT: Include these dog names in your descriptions."
        return base_prompt

    def parse_llm_response(self, response_text):
        try: return json.loads(response_text)
        except json.JSONDecodeError:
            match = re.search(r'```json\s*([\s\S]+?)\s*```', response_text)
            if match:
                try: return json.loads(match.group(1))
                except json.JSONDecodeError: pass
            try:
                short = re.search(r'["\']short["\']\s*:\s*["\'](.*?)["\']', response_text, re.DOTALL).group(1)
                long = re.search(r'["\']long["\']\s*:\s*["\'](.*?)["\']', response_text, re.DOTALL).group(1)
                return {'short': short, 'long': long}
            except AttributeError: return None

    def generate_description_openai(self, base64_image, prompt):
        response = self.openai_client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}], max_tokens=1000, response_format={"type": "json_object"})
        return self.parse_llm_response(response.choices[0].message.content)
    def generate_description_anthropic(self, base64_image, prompt):
        response = self.anthropic_client.messages.create(model="claude-3-haiku-20240307", max_tokens=1000, messages=[{"role": "user", "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64_image}}, {"type": "text", "text": prompt}]}])
        return self.parse_llm_response(response.content[0].text)
    def generate_description_gemini(self, pil_image, prompt):
        response = self.gemini_model.generate_content([prompt, pil_image]); return self.parse_llm_response(response.text)

    def generate_description(self, image_path, persons, dogs):
        base64_image = get_image_base64(image_path)
        if not base64_image: self.update_queue.put(('log', self.lang['image_encode_failed'].format(filename=os.path.basename(image_path)))); return None
        prompt = self.get_language_specific_prompt(persons, dogs); llm = self.selected_llm.get()
        if (llm == "OpenAI" and not self.openai_client) or (llm == "Anthropic" and not self.anthropic_client) or (llm == "Gemini" and not self.gemini_model):
            self.update_queue.put(('log', self.lang['client_not_initialized'].format(llm=llm))); return None
        try:
            self.update_queue.put(('log', self.lang['sending_request_to'].format(llm=llm, filename=os.path.basename(image_path))))
            if llm == "OpenAI": return self.generate_description_openai(base64_image, prompt)
            elif llm == "Anthropic": return self.generate_description_anthropic(base64_image, prompt)
            elif llm == "Gemini":
                with Image.open(image_path) as img: return self.generate_description_gemini(img, prompt)
        except Exception as e: self.update_queue.put(('log', self.lang['api_error'].format(llm=llm, e=e))); return None

    def toggle_rename_frame(self):
        if not self.db_path.get() or not os.path.exists(self.db_path.get()): messagebox.showwarning(self.lang['select_db_warning_title'], self.lang['select_db_warning_msg']); return
        if self.rename_frame.winfo_viewable(): self.rename_frame.grid_remove()
        else: self.rename_frame.grid(); self.propose_rename_directory(self.rename_dest_dir)
            
    def propose_rename_directory(self, dest_dir_var):
        """Proposes a 'NewNames' subdirectory in the current working directory."""
        try:
            # Получаем текущую рабочую директорию
            current_dir = os.getcwd()
            # Создаем путь к подпапке 'NewNames'
            dest_dir = os.path.join(current_dir, "NewNames")
            # Устанавливаем этот путь в поле для ввода
            dest_dir_var.set(dest_dir)
            # Логируем предложенную директорию
            self.update_queue.put(('log', self.lang['propose_rename_dir'].format(dest_dir=dest_dir)))
        except Exception as e:
            self.update_queue.put(('log', self.lang['propose_rename_dir_error'].format(e=e)))

    def browse_rename_dest(self):
        path = filedialog.askdirectory(title=self.lang['rename_dest_dir_label'])
        if path: self.rename_dest_dir.set(path)

    def start_renaming_process(self):
        dest_dir = self.rename_dest_dir.get()
        if not dest_dir: messagebox.showwarning(self.lang['select_db_warning_title'], self.lang['select_rename_dir_warning_msg']); return
        if not os.path.exists(dest_dir):
            try: os.makedirs(dest_dir)
            except OSError as e: messagebox.showerror(self.lang['dir_creation_error_title'], self.lang['dir_creation_error_msg'].format(e=e)); return
        self.process_button.config(state=tk.DISABLED); self.toggle_rename_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED) # No stop for renaming for now
        self.update_queue.put(('log', self.lang['renaming_started'])); threading.Thread(target=self.renaming_thread, args=(dest_dir,), daemon=True).start()

    def renaming_thread(self, dest_dir):
        total = 0
        try:
            with sqlite3.connect(self.db_path.get()) as conn: images_to_rename = conn.cursor().execute('SELECT filepath, ai_short_description FROM images WHERE ai_short_description IS NOT NULL AND ai_short_description != ""').fetchall()
            total = len(images_to_rename)
            self.update_queue.put(('progress', (0, total))); self.update_queue.put(('log', self.lang['found_for_renaming'].format(total=total)))
            for i, (original_path, description) in enumerate(images_to_rename):
                self.update_queue.put(('progress', (i, total)))
                if not os.path.exists(original_path): self.update_queue.put(('log', self.lang['file_not_found_skip'].format(path=original_path))); continue
                file_extension = Path(original_path).suffix; new_filename_base = sanitize_filename(transliterate(description))
                new_filename = f"{new_filename_base}{file_extension}"; new_filepath = os.path.join(dest_dir, new_filename)
                counter = 2
                while os.path.exists(new_filepath): new_filename = f"{new_filename_base}_({counter}){file_extension}"; new_filepath = os.path.join(dest_dir, new_filename); counter += 1
                try: shutil.copy2(original_path, new_filepath); self.update_queue.put(('log', self.lang['copied_file'].format(original=os.path.basename(original_path), new=new_filename)))
                except Exception as e: self.update_queue.put(('log', self.lang['copy_error'].format(original=os.path.basename(original_path), e=e)))
            self.update_queue.put(('log', self.lang['renaming_finished']))
        except Exception as e: self.update_queue.put(('log', self.lang['critical_error_renaming_thread'].format(e=e, traceback=traceback.format_exc())))
        finally: self.update_queue.put(('progress', (total, total))); self.update_queue.put(('task_finished', None))

    def copy_log_to_clipboard(self): self.root.clipboard_clear(); self.root.clipboard_append(self.log_text.get(1.0, tk.END)); self.update_queue.put(('log', self.lang['log_copied']))

def main():
    root = tk.Tk()
    try:
        style = ttk.Style(root); style.theme_use('clam'); style.configure("Accent.TButton", foreground="white", background="#0078D7")
    except tk.TclError: print("Theme 'clam' not found, using default theme.")
    app = AIPhotoDescriptor(root); root.mainloop()

if __name__ == "__main__": main()