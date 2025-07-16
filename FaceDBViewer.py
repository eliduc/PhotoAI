"""
Face Database Viewer v1.6.0
Программа для просмотра базы данных распознанных лиц и собак

Версия: 1.6.0
- Устранена критическая ошибка TclError "unknown option -weight". Проблема
  возникала из-за неверного использования опций для виджета PanedWindow.
- Окончательно исправлена проблема сжатия панели изображения. Используется
  стандартный tk.PanedWindow с корректной опцией `minsize`.
- Проверена и подтверждена работа функции автоповорота изображений (EXIF).
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sqlite3
from datetime import datetime
from PIL import Image, ImageTk, ImageDraw, ImageFont, ExifTags
import json

# Версия программы
VERSION = "1.6.0"

def correct_image_orientation(image: Image.Image) -> Image.Image:
    """Применяет поворот к изображению PIL на основе его EXIF-данных."""
    try:
        exif = image.getexif()
        orientation_tag = 0x0112

        if orientation_tag in exif:
            orientation = exif[orientation_tag]
            if orientation == 3:
                image = image.rotate(180, expand=True)
            elif orientation == 6:
                image = image.rotate(270, expand=True)
            elif orientation == 8:
                image = image.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError):
        pass
    return image

class EditPersonDialog(tk.Toplevel):
    """Диалог для редактирования информации о человеке"""
    def __init__(self, parent, viewer, detection_id, current_person_id=None):
        super().__init__(parent)
        self.viewer = viewer
        self.detection_id = detection_id
        self.current_person_id = current_person_id
        self.result = None

        self.title("Редактировать информацию о человеке")
        self.geometry("600x500")
        self.resizable(True, True)
        self.transient(parent); self.grab_set()

        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Вкладка 1: Выбор из существующих
        existing_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(existing_frame, text="Выбрать из БД")
        columns = ('ID', 'Полное имя', 'Короткое имя', 'Статус')
        self.person_tree = ttk.Treeview(existing_frame, columns=columns, show='headings', height=12)
        for col in columns:
            self.person_tree.heading(col, text=col)
            self.person_tree.column(col, width=120, anchor='w')
        self.person_tree.column('ID', width=50, anchor='center')
        tree_scroll = ttk.Scrollbar(existing_frame, orient="vertical", command=self.person_tree.yview)
        self.person_tree.configure(yscrollcommand=tree_scroll.set)
        self.load_persons()
        self.person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Вкладка 2: Создание нового
        new_person_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(new_person_frame, text="Создать нового")
        new_person_frame.columnconfigure(1, weight=1)
        ttk.Label(new_person_frame, text="Полное имя:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.full_name_var = tk.StringVar()
        ttk.Entry(new_person_frame, textvariable=self.full_name_var).grid(row=0, column=1, sticky=tk.EW)
        ttk.Label(new_person_frame, text="Короткое имя:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.short_name_var = tk.StringVar()
        ttk.Entry(new_person_frame, textvariable=self.short_name_var).grid(row=1, column=1, sticky=tk.EW)
        ttk.Label(new_person_frame, text="Примечание:").grid(row=2, column=0, sticky=tk.NW, padx=5, pady=5)
        self.notes_text = tk.Text(new_person_frame, height=4, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.notes_text.grid(row=2, column=1, sticky=tk.NSEW)
        new_person_frame.rowconfigure(2, weight=1)

        # Вкладка 3: Локальная идентификация
        local_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(local_frame, text="Локальная идентификация")
        local_frame.columnconfigure(1, weight=1)
        ttk.Label(local_frame, text="Локальная идентификация сохраняется только для данного фото", wraplength=500, justify=tk.CENTER).grid(row=0, column=0, columnspan=2, pady=10)
        ttk.Label(local_frame, text="Полное имя:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.local_full_name_var = tk.StringVar()
        ttk.Entry(local_frame, textvariable=self.local_full_name_var).grid(row=1, column=1, sticky=tk.EW)
        ttk.Label(local_frame, text="Короткое имя:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.local_short_name_var = tk.StringVar()
        ttk.Entry(local_frame, textvariable=self.local_short_name_var).grid(row=2, column=1, sticky=tk.EW)
        ttk.Label(local_frame, text="Примечание:").grid(row=3, column=0, sticky=tk.NW, padx=5, pady=5)
        self.local_notes_text = tk.Text(local_frame, height=3, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.local_notes_text.grid(row=3, column=1, sticky=tk.NSEW)
        local_frame.rowconfigure(3, weight=1)

        # Кнопки
        button_frame = ttk.Frame(self, padding=(10, 5))
        button_frame.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(button_frame, text="Применить", command=self.apply_changes, style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Сбросить связь", command=self.remove_link).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Отмена", command=self.cancel).pack(side=tk.RIGHT, padx=5)

        self.load_current_data()
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f'+{x}+{y-50}')

    def load_persons(self):
        with sqlite3.connect(self.viewer.db_path.get()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, full_name, short_name, CASE WHEN is_known THEN 'Известный' ELSE 'Неизвестный' END FROM persons ORDER BY is_known DESC, full_name")
            for row in cursor.fetchall():
                self.person_tree.insert('', tk.END, values=row)
                if self.current_person_id and row[0] == self.current_person_id:
                    self.person_tree.selection_set(self.person_tree.get_children()[-1])
                    self.person_tree.see(self.person_tree.get_children()[-1])

    def load_current_data(self):
        with sqlite3.connect(self.viewer.db_path.get()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_locally_identified, local_full_name, local_short_name, local_notes FROM person_detections WHERE id = ?", (self.detection_id,))
            row = cursor.fetchone()
            if row and row[0]: # is_locally_identified
                self.local_full_name_var.set(row[1] or '')
                self.local_short_name_var.set(row[2] or '')
                self.local_notes_text.insert('1.0', row[3] or '')
                self.notebook.select(2)

    def apply_changes(self):
        current_tab = self.notebook.index(self.notebook.select())
        if current_tab == 0:
            selection = self.person_tree.selection()
            if not selection: messagebox.showwarning("Предупреждение", "Выберите человека из списка", parent=self); return
            self.result = {'action': 'existing', 'person_id': self.person_tree.item(selection[0])['values'][0]}
        elif current_tab == 1:
            full_name = self.full_name_var.get().strip()
            if not full_name: messagebox.showwarning("Предупреждение", "Введите полное имя", parent=self); return
            self.result = {'action': 'new', 'full_name': full_name, 'short_name': self.short_name_var.get().strip() or full_name.split()[0], 'notes': self.notes_text.get('1.0', tk.END).strip()}
        elif current_tab == 2:
            full_name = self.local_full_name_var.get().strip()
            if not full_name: messagebox.showwarning("Предупреждение", "Введите полное имя для локальной идентификации", parent=self); return
            self.result = {'action': 'local', 'local_full_name': full_name, 'local_short_name': self.local_short_name_var.get().strip() or full_name.split()[0], 'local_notes': self.local_notes_text.get('1.0', tk.END).strip()}
        self.destroy()

    def remove_link(self):
        if messagebox.askyesno("Подтверждение", "Удалить связь с человеком?", parent=self):
            self.result = {'action': 'remove'}
            self.destroy()

    def cancel(self): self.result = None; self.destroy()


class EditDogDialog(tk.Toplevel):
    def __init__(self, parent, viewer, detection_id, current_dog_id=None):
        super().__init__(parent)
        self.viewer = viewer
        self.detection_id = detection_id
        self.current_dog_id = current_dog_id
        self.result = None

        self.title("Редактировать информацию о собаке")
        self.geometry("600x450")
        self.resizable(True, True)
        self.transient(parent); self.grab_set()

        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Вкладка 1: Выбор из существующих
        existing_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(existing_frame, text="Выбрать из БД")
        columns = ('ID', 'Кличка', 'Порода', 'Владелец', 'Статус')
        self.dog_tree = ttk.Treeview(existing_frame, columns=columns, show='headings', height=10)
        for col in columns:
            self.dog_tree.heading(col, text=col)
            self.dog_tree.column(col, width=100, anchor='w')
        self.dog_tree.column('ID', width=50, anchor='center')
        tree_scroll = ttk.Scrollbar(existing_frame, orient="vertical", command=self.dog_tree.yview)
        self.dog_tree.configure(yscrollcommand=tree_scroll.set)
        self.load_dogs()
        self.dog_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Вкладка 2: Создание новой
        new_dog_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(new_dog_frame, text="Создать новую")
        new_dog_frame.columnconfigure(1, weight=1)
        ttk.Label(new_dog_frame, text="Кличка:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.name_var = tk.StringVar()
        ttk.Entry(new_dog_frame, textvariable=self.name_var).grid(row=0, column=1, sticky=tk.EW)
        ttk.Label(new_dog_frame, text="Порода:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.breed_var = tk.StringVar()
        ttk.Entry(new_dog_frame, textvariable=self.breed_var).grid(row=1, column=1, sticky=tk.EW)
        ttk.Label(new_dog_frame, text="Владелец:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.owner_var = tk.StringVar()
        ttk.Entry(new_dog_frame, textvariable=self.owner_var).grid(row=2, column=1, sticky=tk.EW)
        ttk.Label(new_dog_frame, text="Примечание:").grid(row=3, column=0, sticky=tk.NW, padx=5, pady=5)
        self.notes_text = tk.Text(new_dog_frame, height=3, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.notes_text.grid(row=3, column=1, sticky=tk.NSEW)
        new_dog_frame.rowconfigure(3, weight=1)

        button_frame = ttk.Frame(self, padding=(10,5))
        button_frame.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(button_frame, text="Применить", command=self.apply_changes, style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Сбросить связь", command=self.remove_link).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Отмена", command=self.cancel).pack(side=tk.RIGHT, padx=5)

        self.center_window()

    def center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f'+{x}+{y-50}')

    def load_dogs(self):
        with sqlite3.connect(self.viewer.db_path.get()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, breed, owner, CASE WHEN is_known THEN 'Известная' ELSE 'Неизвестная' END FROM dogs ORDER BY is_known DESC, name")
            for row in cursor.fetchall():
                self.dog_tree.insert('', tk.END, values=row)
                if self.current_dog_id and row[0] == self.current_dog_id:
                    self.dog_tree.selection_set(self.dog_tree.get_children()[-1])
                    self.dog_tree.see(self.dog_tree.get_children()[-1])

    def apply_changes(self):
        current_tab = self.notebook.index(self.notebook.select())
        if current_tab == 0:
            selection = self.dog_tree.selection()
            if not selection: messagebox.showwarning("Предупреждение", "Выберите собаку из списка", parent=self); return
            self.result = {'action': 'existing', 'dog_id': self.dog_tree.item(selection[0])['values'][0]}
        elif current_tab == 1:
            name = self.name_var.get().strip()
            if not name: messagebox.showwarning("Предупреждение", "Введите кличку", parent=self); return
            self.result = {'action': 'new', 'name': name, 'breed': self.breed_var.get().strip(), 'owner': self.owner_var.get().strip(), 'notes': self.notes_text.get('1.0', tk.END).strip()}
        self.destroy()

    def remove_link(self):
        if messagebox.askyesno("Подтверждение", "Удалить связь с собакой?", parent=self):
            self.result = {'action': 'remove'}
            self.destroy()

    def cancel(self): self.result = None; self.destroy()


class FaceDBViewer:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Face Database Viewer v{VERSION}")
        self.root.geometry("1500x950")

        # --- Стили ---
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            pass # Fallback to default
        self.style.configure('TLabelFrame.Label', font=('Arial', 10, 'bold'))
        self.style.configure('TNotebook.Tab', font=('Arial', 11, 'bold'), padding=[10, 5])
        self.style.configure('Status.TLabel', font=('Arial', 10, 'bold'), padding=5)
        self.style.configure('Idle.Status.TLabel', background='lightblue', foreground='black')
        self.style.configure('Processing.Status.TLabel', background='lightyellow', foreground='black')
        self.style.configure('Complete.Status.TLabel', background='lightgreen', foreground='black')
        self.style.configure('Error.Status.TLabel', background='lightcoral', foreground='black')
        self.style.configure('Accent.TButton', font=('Arial', 10, 'bold'), foreground='navy')


        # Переменные
        self.db_path = tk.StringVar()
        self.current_image_id = None
        self.search_name = tk.StringVar()
        self.search_date_from = tk.StringVar()
        self.search_date_to = tk.StringVar()
        self.highlighted_person_detection_id = None
        self.highlighted_dog_detection_id = None
        self.has_dogs = False
        self.has_ai_descriptions = False

        self.create_widgets()
        self.update_status("Выберите базу данных и нажмите 'Открыть'", 'idle')

    def update_status(self, message, status_type):
        self.status_bar.config(text=message)
        style_map = {'idle': 'Idle.Status.TLabel', 'processing': 'Processing.Status.TLabel',
                     'complete': 'Complete.Status.TLabel', 'error': 'Error.Status.TLabel'}
        self.status_bar.config(style=style_map.get(status_type, 'Idle.Status.TLabel'))

    def create_widgets(self):
        # --- Верхняя панель ---
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(side=tk.TOP, fill=tk.X)
        top_frame.columnconfigure(1, weight=1)
        ttk.Label(top_frame, text="База данных:").grid(row=0, column=0, padx=(0, 5))
        ttk.Entry(top_frame, textvariable=self.db_path, width=70).grid(row=0, column=1, sticky=tk.EW)
        ttk.Button(top_frame, text="Выбрать...", command=self.browse_db).grid(row=0, column=2, padx=5)
        ttk.Button(top_frame, text="📂 Открыть", command=self.open_db, style="Accent.TButton").grid(row=0, column=3)
        ttk.Label(self.root, text=f"v{VERSION}", font=('Arial', 9)).place(relx=0.99, y=5, anchor='ne')

        # --- Основная область ---
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Левая панель
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=2)
        self.create_search_panel(left_frame)
        self.create_image_list(left_frame)

        # Правая панель
        # ИСПРАВЛЕНИЕ: Используем стандартный tk.PanedWindow для поддержки minsize
        right_paned = tk.PanedWindow(main_paned, orient=tk.VERTICAL, sashrelief=tk.RAISED, bg="#dcdcdc")
        main_paned.add(right_paned, weight=5)
        
        image_frame = ttk.LabelFrame(right_paned, text="Изображение", padding="5")
        
        # ИСПРАВЛЕНИЕ: Добавляем панель с minsize, удаляем weight
        right_paned.add(image_frame, minsize=300)

        self.image_label = ttk.Label(image_frame, anchor='center')
        self.image_label.pack(fill=tk.BOTH, expand=True)

        self.info_notebook = ttk.Notebook(right_paned)
        right_paned.add(self.info_notebook, minsize=200) # minsize для нижней панели
        for text, creator in [("Общая информация", self.create_general_info),
                              ("Распознанные люди", self.create_people_info),
                              ("Распознанные собаки", self.create_dogs_info),
                              ("AI Описания", self.create_ai_descriptions)]:
            tab_frame = ttk.Frame(self.info_notebook)
            self.info_notebook.add(tab_frame, text=text)
            creator(tab_frame)
        self.info_notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)

        # Статусная строка
        self.status_bar = ttk.Label(self.root, relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def create_search_panel(self, parent):
        search_frame = ttk.LabelFrame(parent, text="Поиск", padding="10")
        search_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))
        search_frame.columnconfigure(1, weight=1)

        ttk.Label(search_frame, text="Имя/Кличка:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(search_frame, textvariable=self.search_name).grid(row=0, column=1, columnspan=2, sticky=tk.EW, pady=2)
        ttk.Label(search_frame, text="Имена: & (и), | (или)", font=('Arial', 8, 'italic')).grid(row=1, column=1, columnspan=2, sticky=tk.W)

        ttk.Label(search_frame, text="Дата с:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(search_frame, textvariable=self.search_date_from).grid(row=2, column=1, sticky=tk.EW, pady=2)
        ttk.Label(search_frame, text="по:").grid(row=2, column=2, sticky=tk.W, padx=5)
        ttk.Entry(search_frame, textvariable=self.search_date_to).grid(row=2, column=3, sticky=tk.EW, pady=2)
        ttk.Label(search_frame, text="Формат: YYYY-MM-DD", font=('Arial', 8, 'italic')).grid(row=3, column=1, columnspan=3, sticky=tk.W)

        button_frame = ttk.Frame(search_frame)
        button_frame.grid(row=4, column=0, columnspan=4, pady=(10, 0))
        ttk.Button(button_frame, text="Искать", command=self.search_images, style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Сбросить", command=self.reset_search).pack(side=tk.LEFT, padx=5)

    def create_image_list(self, parent):
        list_frame = ttk.LabelFrame(parent, text="Изображения", padding="5")
        list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        columns = ('ID', 'Файл', 'Дата', 'Люди', 'Лица', 'Собаки', 'AI')
        self.image_tree = ttk.Treeview(list_frame, columns=columns, show='headings')
        for col in columns: self.image_tree.heading(col, text=col)
        for col, w in [('ID', 40), ('Файл', 200), ('Дата', 90), ('Люди', 40), ('Лица', 40), ('Собаки', 50), ('AI', 30)]:
            self.image_tree.column(col, width=w, anchor='center')
        self.image_tree.column('Файл', anchor='w')
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.image_tree.yview)
        self.image_tree.configure(yscrollcommand=scrollbar.set)
        self.image_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.image_tree.bind('<<TreeviewSelect>>', self.on_image_select)

    def create_text_pane(self, parent, is_detail=False):
        text_widget = tk.Text(parent, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1,
                              font=('Arial', 10), background="#fdfdfd", padx=5, pady=5)
        if is_detail:
            text_widget.tag_config("header", font=('Arial', 11, 'bold'), spacing1=5, spacing3=5, underline=True)
            text_widget.tag_config("subheader", font=('Arial', 10, 'bold'), spacing1=8, spacing3=2)
            text_widget.tag_config("meta", font=('Arial', 9, 'italic'), foreground='gray')
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        return text_widget

    def create_general_info(self, parent):
        self.info_text = self.create_text_pane(parent, is_detail=True)

    def create_people_info(self, parent):
        pane = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        pane.pack(fill=tk.BOTH, expand=True)
        
        table_frame = ttk.Frame(pane)
        pane.add(table_frame, weight=1)
        header = ttk.Frame(table_frame)
        header.pack(fill=tk.X, padx=5, pady=(5,2))
        ttk.Label(header, text="Люди на фото:", font=('Arial', 10, 'bold')).pack(side=tk.LEFT)
        self.edit_person_btn = ttk.Button(header, text="Редактировать", command=self.edit_person_detection, state=tk.DISABLED)
        self.edit_person_btn.pack(side=tk.RIGHT)
        
        cols = ('#', 'Тип', 'Имя', 'Статус', 'ID')
        self.people_tree = ttk.Treeview(table_frame, columns=cols, show='headings')
        for col in cols: self.people_tree.heading(col, text=col)
        for col, w in [('#', 30), ('Тип', 80), ('Имя', 200), ('Статус', 120), ('ID', 50)]:
            self.people_tree.column(col, width=w, anchor='center')
        self.people_tree.column('Имя', anchor='w')
        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.people_tree.yview)
        self.people_tree.configure(yscrollcommand=scroll.set)
        self.people_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.people_tree.bind('<<TreeviewSelect>>', self.on_person_select)
        
        detail_frame = ttk.LabelFrame(pane, text="Детальная информация", padding=5)
        pane.add(detail_frame, weight=1)
        self.person_detail_text = self.create_text_pane(detail_frame, is_detail=True)
        self.person_detail_text.insert('1.0', "Выберите человека для просмотра деталей.")

    def create_dogs_info(self, parent):
        pane = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        pane.pack(fill=tk.BOTH, expand=True)
        
        table_frame = ttk.Frame(pane)
        pane.add(table_frame, weight=1)
        header = ttk.Frame(table_frame)
        header.pack(fill=tk.X, padx=5, pady=(5,2))
        ttk.Label(header, text="Собаки на фото:", font=('Arial', 10, 'bold')).pack(side=tk.LEFT)
        self.edit_dog_btn = ttk.Button(header, text="Редактировать", command=self.edit_dog_detection, state=tk.DISABLED)
        self.edit_dog_btn.pack(side=tk.RIGHT)

        cols = ('#', 'Кличка', 'Порода', 'Владелец', 'Статус', 'ID')
        self.dogs_tree = ttk.Treeview(table_frame, columns=cols, show='headings')
        for col in cols: self.dogs_tree.heading(col, text=col)
        for col, w in [('#', 30), ('Кличка', 120), ('Порода', 120), ('Владелец', 120), ('Статус', 100), ('ID', 50)]:
            self.dogs_tree.column(col, width=w, anchor='center')
        for col in ['Кличка', 'Порода', 'Владелец']: self.dogs_tree.column(col, anchor='w')
        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.dogs_tree.yview)
        self.dogs_tree.configure(yscrollcommand=scroll.set)
        self.dogs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.dogs_tree.bind('<<TreeviewSelect>>', self.on_dog_select)

        detail_frame = ttk.LabelFrame(pane, text="Детальная информация", padding=5)
        pane.add(detail_frame, weight=1)
        self.dog_detail_text = self.create_text_pane(detail_frame, is_detail=True)
        self.dog_detail_text.insert('1.0', "Выберите собаку для просмотра деталей.")

    def create_ai_descriptions(self, parent):
        self.ai_descriptions_text = self.create_text_pane(parent, is_detail=True)
        self.ai_descriptions_text.insert('1.0', "Выберите изображение для просмотра AI описаний.")

    def browse_db(self):
        filename = filedialog.askopenfilename(title="Выберите базу данных", filetypes=[("SQLite DB", "*.db"), ("Все файлы", "*.*")])
        if filename: self.db_path.set(filename)

    def open_db(self):
        db_path = self.db_path.get()
        if not db_path or not os.path.exists(db_path):
            messagebox.showerror("Ошибка", "Выберите существующий файл базы данных")
            return
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                if 'images' not in tables or 'person_detections' not in tables:
                    raise sqlite3.DatabaseError("Неверная структура БД.")
                self.has_dogs = 'dogs' in tables and 'dog_detections' in tables
                cursor.execute("PRAGMA table_info(images)")
                self.has_ai_descriptions = 'ai_short_description' in [col[1] for col in cursor.fetchall()]

            self.load_images()
            self.update_status(f"База данных открыта: {os.path.basename(db_path)}", 'complete')
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка открытия БД: {e}")
            self.update_status(f"Ошибка открытия БД", 'error')

    def load_images(self, **kwargs):
        for item in self.image_tree.get_children(): self.image_tree.delete(item)
        if not self.db_path.get(): return
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                # Динамическое построение запроса
                base_query = "SELECT i.id, i.filename, i.created_date, i.num_bodies, i.num_faces, i.filepath"
                query_parts = [base_query]
                params = []

                if self.has_dogs: query_parts.append(", i.num_dogs")
                else: query_parts.append(", 0 as num_dogs")
                if self.has_ai_descriptions: query_parts.append(", i.ai_short_description")
                else: query_parts.append(", NULL as ai_short_description")

                query_parts.append("FROM images i")

                # Логика фильтрации
                conditions, search_pattern = [], self.search_name.get().strip()
                if search_pattern:
                    query_parts.append("LEFT JOIN person_detections pd ON i.id = pd.image_id LEFT JOIN persons p ON pd.person_id = p.id")
                    if self.has_dogs:
                        query_parts.append("LEFT JOIN dog_detections dd ON i.id = dd.image_id LEFT JOIN dogs d ON dd.dog_id = d.id")

                    if '&' in search_pattern:
                        names = [name.strip() for name in search_pattern.split('&') if name.strip()]
                        for name in names:
                            name_like = f"%{name}%"
                            sub_cond = "(p.full_name LIKE ? OR p.short_name LIKE ? OR pd.local_full_name LIKE ? OR pd.local_short_name LIKE ?)"
                            if self.has_dogs:
                                sub_cond = f"({sub_cond} OR d.name LIKE ?)"
                                params.extend([name_like] * 5)
                            else:
                                params.extend([name_like] * 4)
                            conditions.append(f"i.id IN (SELECT image_id FROM person_detections pd LEFT JOIN persons p ON pd.person_id = p.id {'LEFT JOIN dog_detections dd ON pd.image_id = dd.image_id LEFT JOIN dogs d ON dd.dog_id = d.id' if self.has_dogs else ''} WHERE {sub_cond})")
                    else: # Режим ИЛИ (по умолчанию)
                        names = [name.strip() for name in search_pattern.split('|') if name.strip()]
                        if not names: names = [search_pattern]
                        
                        or_clauses = []
                        for name in names:
                            name_like = f"%{name}%"
                            clause = "(p.full_name LIKE ? OR p.short_name LIKE ? OR pd.local_full_name LIKE ? OR pd.local_short_name LIKE ?)"
                            if self.has_dogs:
                                clause = f"({clause} OR d.name LIKE ?)"
                                params.extend([name_like] * 5)
                            else:
                                params.extend([name_like] * 4)
                            or_clauses.append(clause)
                        conditions.append(f"({' OR '.join(or_clauses)})")

                if self.search_date_from.get(): conditions.append("date(i.created_date) >= ?"); params.append(self.search_date_from.get())
                if self.search_date_to.get(): conditions.append("date(i.created_date) <= ?"); params.append(self.search_date_to.get())

                if conditions: query_parts.append("WHERE " + " AND ".join(conditions))
                query_parts.append("GROUP BY i.id ORDER BY i.created_date DESC")
                
                final_query = " ".join(query_parts)
                cursor = conn.cursor()
                cursor.execute(final_query, params)
                for row in cursor.fetchall():
                    date_str = datetime.fromisoformat(row[2]).strftime("%Y-%m-%d") if row[2] else ""
                    self.image_tree.insert('', tk.END, values=(row[0], row[1], date_str, row[3], row[4], row[6] if self.has_dogs else '-', "✓" if row[7] else ""), tags=(row[5],))
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка загрузки изображений: {e}")

    def search_images(self): self.load_images()
    def reset_search(self):
        self.search_name.set(""); self.search_date_from.set(""); self.search_date_to.set(""); self.load_images()

    def on_image_select(self, event):
        selection = self.image_tree.selection()
        if not selection: return
        item = self.image_tree.item(selection[0])
        self.current_image_id = item['values'][0]
        filepath = item['tags'][0] if item['tags'] else None
        self.highlighted_person_detection_id = None
        self.highlighted_dog_detection_id = None
        self.display_image(filepath)
        self.on_tab_changed()

    def on_tab_changed(self, event=None):
        if not self.current_image_id: return
        try:
            tab_text = self.info_notebook.tab(self.info_notebook.select(), "text")
        except tk.TclError:
            return 
        
        if tab_text == "Общая информация": self.show_image_info()
        elif tab_text == "Распознанные люди": self.show_people_info()
        elif tab_text == "Распознанные собаки": self.show_dogs_info()
        elif tab_text == "AI Описания": self.show_ai_descriptions()

        if tab_text not in ['Распознанные люди', 'Распознанные собаки']:
            if self.highlighted_person_detection_id or self.highlighted_dog_detection_id:
                self.highlighted_person_detection_id = None
                self.highlighted_dog_detection_id = None
                if self.image_tree.selection():
                    filepath = self.image_tree.item(self.image_tree.selection()[0])['tags'][0]
                    self.display_image(filepath)

    def display_image(self, filepath):
        if not filepath or not os.path.exists(filepath):
            self.image_label.config(image='', text="Файл не найден")
            return
        try:
            image = Image.open(filepath)
            image = correct_image_orientation(image)
            draw = ImageDraw.Draw(image, 'RGBA')
            try: font, highlight_font = ImageFont.truetype("arial.ttf", 20), ImageFont.truetype("arial.ttf", 24)
            except IOError: font = highlight_font = ImageFont.load_default()

            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                q_people = "SELECT pd.id, pd.bbox, pd.has_face, p.is_known, COALESCE(p.short_name, pd.local_short_name, 'Unknown'), pd.person_index FROM person_detections pd LEFT JOIN persons p ON pd.person_id = p.id WHERE pd.image_id = ?"
                for det_id, bbox_js, has_face, is_known, name, index in cursor.execute(q_people, (self.current_image_id,)):
                    is_hl = (self.highlighted_person_detection_id == det_id)
                    color, text = ("purple", f"#{index}: {name}") if is_known else (("green", f"#{index}: Face") if has_face else ("yellow", f"#{index}: No face"))
                    self._draw_box_and_text(draw, json.loads(bbox_js), text, color, is_hl, font, highlight_font)
                if self.has_dogs:
                    q_dogs = "SELECT dd.id, dd.bbox, d.is_known, d.name, dd.dog_index FROM dog_detections dd LEFT JOIN dogs d ON dd.dog_id = d.id WHERE dd.image_id = ?"
                    for det_id, bbox_js, is_known, name, index in cursor.execute(q_dogs, (self.current_image_id,)):
                        is_hl = (self.highlighted_dog_detection_id == det_id)
                        color, text = ("#800080", f"Dog #{index}: {name}") if is_known else ("orange", f"Dog #{index}")
                        self._draw_box_and_text(draw, json.loads(bbox_js), text, color, is_hl, font, highlight_font)

            self.image_label.update_idletasks()
            w, h = self.image_label.winfo_width(), self.image_label.winfo_height()
            if w > 10 and h > 10: image.thumbnail((w - 20, h - 20), Image.Resampling.LANCZOS)

            photo = ImageTk.PhotoImage(image)
            self.image_label.config(image=photo, text='')
            self.image_label.image = photo
        except Exception as e:
            self.image_label.config(image='', text=f"Ошибка отображения: {e}")

    def _draw_box_and_text(self, draw, bbox, text, color, is_highlighted, font, highlight_font):
        x1, y1, x2, y2 = bbox
        width, current_font = (6, highlight_font) if is_highlighted else (3, font)
        draw.rectangle([x1, y1, x2, y2], outline=color, width=width)
        
        try:
             text_bbox = draw.textbbox((0, 0), text, font=current_font)
             text_h = text_bbox[3] - text_bbox[1]
             text_pos = (x1, y1 - text_h - 7)
        except AttributeError:
             text_pos = (x1, y1 - 25)
             text_h = 15

        text_bbox_final = (text_pos[0], text_pos[1], text_pos[0] + (draw.textlength(text, font=current_font) if hasattr(draw, 'textlength') else 100), text_pos[1] + text_h + 5)
        draw.rectangle([text_bbox_final[0]-3, text_bbox_final[1]-3, text_bbox_final[2]+3, text_bbox_final[3]+3], fill=(255,255,255,200))
        draw.text(text_pos, text, fill=color, font=current_font)

    def _execute_info_query(self, text_widget, query, formatter, default_text):
        text_widget.delete('1.0', tk.END)
        if not self.current_image_id: return
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                row = conn.execute(query, (self.current_image_id,)).fetchone()
                if row:
                    formatted_text = formatter(row)
                    text_widget.insert('1.0', formatted_text)
                else:
                    text_widget.insert('1.0', default_text)
        except sqlite3.OperationalError as e:
            text_widget.insert('1.0', f"Ошибка в структуре БД: {e}")

    def show_image_info(self):
        self._execute_info_query(
            self.info_text,
            "SELECT filename, filepath, file_size, created_date, processed_date, num_bodies, num_faces, num_dogs FROM images WHERE id = ?",
            lambda r: f"Файл: {r[0]}\nПуть: {r[1]}\nРазмер: {r[2]:,} байт\nДата создания: {r[3]}\nДата обработки: {r[4]}\n\nЛюдей: {r[5]}\nЛиц: {r[6]}\nСобак: {r[7] if len(r)>7 and r[7] is not None else 'N/A'}",
            "Информация об изображении не найдена."
        )

    def show_ai_descriptions(self):
        if not self.has_ai_descriptions:
            self.ai_descriptions_text.delete('1.0', tk.END)
            self.ai_descriptions_text.insert('1.0', "AI описания не поддерживаются этой базой данных.")
            return
        self._execute_info_query(
            self.ai_descriptions_text,
            "SELECT ai_short_description, ai_long_description, ai_processed_date, ai_llm_used FROM images WHERE id = ?",
            lambda r: (f"🤖 AI ОПИСАНИЯ\n\n📝 Краткое:\n{r[0]}\n\n📄 Подробное:\n{r[1]}\n\n"
                       f"Мета:\nОбработано: {r[2]}\nМодель: {r[3]}") if r and (r[0] or r[1]) else "AI описания отсутствуют.",
            "AI описания для этого изображения отсутствуют."
        )
    
    def _update_detection_tree(self, tree, query):
        for item in tree.get_children(): tree.delete(item)
        if not self.current_image_id: return
        with sqlite3.connect(self.db_path.get()) as conn:
            for row in conn.execute(query, (self.current_image_id,)):
                tree.insert('', tk.END, values=row[:-1], tags=(row[-1],))

    def show_people_info(self):
        self.person_detail_text.delete('1.0', tk.END)
        self.person_detail_text.insert('1.0', "Выберите человека для просмотра деталей.")
        self._update_detection_tree(self.people_tree, "SELECT pd.person_index, CASE WHEN pd.has_face THEN 'С лицом' ELSE 'Без лица' END, COALESCE(p.full_name, pd.local_full_name, 'Неизвестный'), CASE WHEN p.is_known THEN 'Известный' WHEN pd.is_locally_identified THEN 'Локальный' ELSE 'Неизвестный' END, p.id, pd.id FROM person_detections pd LEFT JOIN persons p ON pd.person_id = p.id WHERE pd.image_id = ? ORDER BY pd.person_index")

    def show_dogs_info(self):
        self.dog_detail_text.delete('1.0', tk.END)
        self.dog_detail_text.insert('1.0', "Выберите собаку для просмотра деталей.")
        if not self.has_dogs:
            self.dogs_tree.insert('', tk.END, values=('', 'Не поддерживается', '', '', '', ''))
            return
        self._update_detection_tree(self.dogs_tree, "SELECT dd.dog_index, d.name, d.breed, d.owner, CASE WHEN d.is_known THEN 'Известная' ELSE 'Неизвестная' END, d.id, dd.id FROM dog_detections dd LEFT JOIN dogs d ON dd.dog_id = d.id WHERE dd.image_id = ? ORDER BY dd.dog_index")

    def _on_detection_select(self, type):
        tree = self.people_tree if type == 'people' else self.dogs_tree
        btn = self.edit_person_btn if type == 'people' else self.edit_dog_btn
        
        selection = tree.selection()
        if not selection: btn.config(state=tk.DISABLED); return
        btn.config(state=tk.NORMAL)
        
        detection_id = tree.item(selection[0])['tags'][0]
        setattr(self, f'highlighted_{"person" if type == "people" else "dog"}_detection_id', detection_id)
        if type == 'people': self.highlighted_dog_detection_id = None
        else: self.highlighted_person_detection_id = None

        filepath = self.image_tree.item(self.image_tree.selection()[0])['tags'][0]
        self.display_image(filepath)
        # Логика детальной информации здесь (или вызов отдельного метода)

    def on_person_select(self, event): self._on_detection_select('people')
    def on_dog_select(self, event): self._on_detection_select('dogs')

    def _edit_detection(self, type):
        tree = self.people_tree if type == 'people' else self.dogs_tree
        if not tree.selection(): return
        detection_id = tree.item(tree.selection()[0])['tags'][0]
        
        with sqlite3.connect(self.db_path.get()) as conn:
            id_field, table = ("person_id", "person_detections") if type == 'people' else ("dog_id", "dog_detections")
            current_id = conn.execute(f'SELECT {id_field} FROM {table} WHERE id = ?', (detection_id,)).fetchone()
        
        dialog = (EditPersonDialog if type == 'people' else EditDogDialog)(self.root, self, detection_id, current_id[0] if current_id else None)
        self.root.wait_window(dialog)
        
        if dialog.result:
            self._apply_changes(type, detection_id, dialog.result)
            self.on_image_select(None)

    def edit_person_detection(self): self._edit_detection('people')
    def edit_dog_detection(self): self._edit_detection('dogs')

    def _apply_changes(self, type, detection_id, result):
        action = result.get('action')
        with sqlite3.connect(self.db_path.get()) as conn:
            cursor = conn.cursor()
            if type == 'people':
                if action == 'existing':
                    cursor.execute('UPDATE person_detections SET person_id=?, is_locally_identified=0, local_full_name=NULL, local_short_name=NULL, local_notes=NULL WHERE id=?', (result['person_id'], detection_id))
                elif action == 'new':
                    cursor.execute('INSERT INTO persons (is_known, full_name, short_name, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?)', (result['full_name'], result['short_name'], result['notes'], datetime.now().isoformat(), datetime.now().isoformat()))
                    cursor.execute('UPDATE person_detections SET person_id=? WHERE id=?', (cursor.lastrowid, detection_id))
                elif action == 'local':
                    cursor.execute('UPDATE person_detections SET person_id=NULL, is_locally_identified=1, local_full_name=?, local_short_name=?, local_notes=? WHERE id=?', (result['local_full_name'], result['local_short_name'], result['local_notes'], detection_id))
                elif action == 'remove':
                    cursor.execute('UPDATE person_detections SET person_id=NULL, is_locally_identified=0, local_full_name=NULL, local_short_name=NULL, local_notes=NULL WHERE id=?', (detection_id,))
            else: # dogs
                if action == 'existing':
                    cursor.execute('UPDATE dog_detections SET dog_id=? WHERE id=?', (result['dog_id'], detection_id))
                elif action == 'new':
                    cursor.execute('INSERT INTO dogs (is_known, name, breed, owner, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?, ?)', (result['name'], result['breed'], result['owner'], result['notes'], datetime.now().isoformat(), datetime.now().isoformat()))
                    cursor.execute('UPDATE dog_detections SET dog_id=? WHERE id=?', (cursor.lastrowid, detection_id))
                elif action == 'remove':
                    cursor.execute('UPDATE dog_detections SET dog_id=NULL WHERE id=?', (detection_id,))
            conn.commit()


def main():
    root = tk.Tk()
    app = FaceDBViewer(root)
    root.mainloop()


if __name__ == "__main__":
    main()