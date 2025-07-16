"""
Face Detection v2.9
Программа для распознавания и учета людей и собак на фотографиях
Версия: 2.9
- Рефакторинг управления базой данных:
  - Удалены пути по умолчанию для директории с фото и базы данных. Пользователь должен выбрать их вручную.
  - Добавлена кнопка "Создать новую..." для создания файла БД в указанном месте.
  - Кнопка "Обзор..." теперь открывает существующий файл БД и проверяет его структуру.
  - Если структура выбранной БД некорректна, программа сообщает об ошибке.
- Улучшен UI/UX:
  - Основные функции (сканирование, управление записями) заблокированы до загрузки или создания БД.
  - Поле для пути к БД теперь только для чтения и заполняется автоматически.
- Исправление критических ошибок:
  - Устранена SyntaxError в обработчиках диалоговых окон.
  - Заполнена логика создания таблиц в функции init_database.
- Повышена стабильность: добавлены проверки на наличие загруженной БД перед выполнением операций.
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import os
import sqlite3
from datetime import datetime
from PIL import Image, ImageTk, ExifTags
import cv2
import face_recognition
import numpy as np
import threading
import queue
from pathlib import Path
from ultralytics import YOLO
import json

# Версия программы
VERSION = "2.9"

def orient_image(img: Image.Image) -> Image.Image:
    """
    Корректирует ориентацию PIL Image на основе его EXIF-данных.
    """
    try:
        exif = img.getexif()
        orientation_tag = 274  # 'Orientation' tag ID

        if orientation_tag in exif:
            orientation = exif[orientation_tag]
            if orientation == 3:
                img = img.rotate(180, expand=True)
            elif orientation == 6:
                img = img.rotate(270, expand=True)
            elif orientation == 8:
                img = img.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError):
        # Если EXIF нет или он некорректен, ничего не делаем
        pass
    return img


class ProcessedImageDialog(tk.Toplevel):
    """Диалог для запроса обработки уже обработанного изображения"""
    def __init__(self, parent, image_path):
        super().__init__(parent)
        self.parent = parent
        self.result = None
        self.apply_to_all = False
        
        self.title("Изображение уже обработано")
        self.geometry("500x200")
        self.resizable(False, False)
        
        self.transient(parent)
        self.grab_set()
        
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        message = f"Изображение '{os.path.basename(image_path)}' уже было обработано ранее.\nОбработать его заново?"
        ttk.Label(main_frame, text=message, wraplength=450).pack(pady=10)
        
        self.apply_to_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(main_frame, text="Применить это решение для всех последующих изображений",
                       variable=self.apply_to_all_var).pack(pady=10)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        
        ttk.Button(button_frame, text="Да, обработать", 
                  command=self.process).pack(side=tk.LEFT, padx=5, expand=True)
        ttk.Button(button_frame, text="Нет, пропустить", 
                  command=self.skip).pack(side=tk.LEFT, padx=5, expand=True)
        ttk.Button(button_frame, text="Отмена", 
                  command=self.cancel).pack(side=tk.RIGHT, padx=5, expand=True)
        
        self.center_window()
        
    def center_window(self):
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width = self.winfo_width()
        window_height = self.winfo_height()
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        self.geometry(f'+{x}+{y}')
        
    def process(self):
        self.result = 'process'
        self.apply_to_all = self.apply_to_all_var.get()
        self.destroy()
        
    def skip(self):
        self.result = 'skip'
        self.apply_to_all = self.apply_to_all_var.get()
        self.destroy()
        
    def cancel(self):
        self.result = 'cancel'
        self.destroy()

class PersonDialog(tk.Toplevel):
    """Диалог для ввода информации о человеке"""
    def __init__(self, parent, image, face_location, existing_persons=None, db_path=None):
        super().__init__(parent)
        self.parent = parent
        self.result = None
        self.existing_persons = existing_persons or []
        self.db_path = db_path
        
        self.title("Новый человек обнаружен")
        self.geometry("700x750")
        self.resizable(True, True)
        
        self.transient(parent)
        self.grab_set()
        
        self.protocol("WM_DELETE_WINDOW", self.save_unknown)
        
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        face_frame = ttk.Frame(main_frame)
        face_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        
        top, right, bottom, left = face_location
        face_img = image[top:bottom, left:right]
        face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
        face_img = Image.fromarray(face_img)
        
        face_img.thumbnail((150, 150), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(face_img)
        
        face_label = ttk.Label(face_frame, image=photo)
        face_label.image = photo
        face_label.pack()
        
        ttk.Label(face_frame, text="Обнаружен новый человек", 
                 font=('Arial', 12, 'bold')).pack(pady=5)
        
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        new_person_frame = ttk.Frame(self.notebook)
        self.notebook.add(new_person_frame, text="Новый человек")
        
        input_frame = ttk.Frame(new_person_frame, padding="20")
        input_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(input_frame, text="Полное имя:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.full_name_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.full_name_var, width=40).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        ttk.Label(input_frame, text="Короткое имя:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.short_name_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.short_name_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        ttk.Label(input_frame, text="Примечание:").grid(row=2, column=0, sticky=tk.W+tk.N, padx=5, pady=5)
        
        text_frame = ttk.Frame(input_frame)
        text_frame.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        self.notes_text = tk.Text(text_frame, width=40, height=4, wrap=tk.WORD)
        notes_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.notes_text.yview)
        self.notes_text.configure(yscrollcommand=notes_scroll.set)
        
        self.notes_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        notes_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        input_frame.columnconfigure(1, weight=1)
        
        if self.existing_persons:
            existing_frame = ttk.Frame(self.notebook)
            self.notebook.add(existing_frame, text="Выбрать из БД")
            
            tree_frame = ttk.Frame(existing_frame, padding="10")
            tree_frame.pack(fill=tk.BOTH, expand=True)
            
            columns = ('ID', 'Полное имя', 'Короткое имя')
            self.person_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=8)
            
            for col in columns:
                self.person_tree.heading(col, text=col)
                if col == 'ID':
                    self.person_tree.column(col, width=50)
                else:
                    self.person_tree.column(col, width=200)
            
            tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.person_tree.yview)
            self.person_tree.configure(yscrollcommand=tree_scroll.set)
            
            for person in self.existing_persons:
                self.person_tree.insert('', tk.END, values=(
                    person['id'], 
                    person['full_name'], 
                    person['short_name']
                ))
            
            self.person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            ttk.Button(existing_frame, text="Использовать выбранного", 
                      command=self.confirm_existing_selection).pack(pady=10)
        
        button_frame = ttk.Frame(self)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        left_buttons = ttk.Frame(button_frame)
        left_buttons.pack(side=tk.LEFT)
        
        right_buttons = ttk.Frame(button_frame)
        right_buttons.pack(side=tk.RIGHT)
        
        ttk.Button(left_buttons, text="Сохранить как известного", 
                  command=self.save_known).pack(side=tk.LEFT, padx=5)
        ttk.Button(left_buttons, text="Оставить неизвестным", 
                  command=self.save_unknown).pack(side=tk.LEFT, padx=5)
        
        if self.existing_persons:
            ttk.Button(left_buttons, text="Выбрать из БД", 
                      command=self.switch_to_db_tab).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(right_buttons, text="Отмена", 
                  command=self.cancel).pack(side=tk.RIGHT, padx=5)
        
        self.center_window()
        
        self.full_name_var.set("")
        self.notebook.select(0)
        self.after(100, lambda: self.focus_force())
        
    def center_window(self):
        self.update_idletasks()
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        window_width = self.winfo_width()
        window_height = self.winfo_height()
        
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2) - 50
        
        if y < 0:
            y = 0
        if y + window_height > screen_height:
            y = screen_height - window_height - 40
            
        self.geometry(f'+{x}+{y}')
        
        self.update_idletasks()
        min_height = self.winfo_reqheight()
        if window_height < min_height:
            self.geometry(f"{window_width}x{min_height}+{x}+{y}")
    
    def check_person_exists(self, full_name, short_name):
        if not self.db_path:
            return False, []
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT id, full_name, short_name 
                FROM persons 
                WHERE is_known = 1 AND full_name = ? AND short_name = ?
            ''', (full_name, short_name))
            
            duplicates = cursor.fetchall()
            
            if duplicates:
                return True, duplicates
            else:
                return False, []
                
        finally:
            conn.close()
        
    def save_known(self):
        full_name = self.full_name_var.get().strip()
        if not full_name:
            messagebox.showwarning("Предупреждение", "Введите полное имя")
            return
        
        short_name = self.short_name_var.get().strip() or full_name.split()[0]
        
        exists, duplicates = self.check_person_exists(full_name, short_name)
        
        if exists:
            duplicate_info = duplicates[0]
            message = (f"В базе данных уже есть человек с такими же именами:\n\n"
                      f"Полное имя: {duplicate_info[1]}\n"
                      f"Короткое имя: {duplicate_info[2]}\n\n"
                      f"Если это другой человек, пожалуйста, измените полное или короткое имя.\n"
                      f"Если это тот же человек, выберите его из вкладки 'Выбрать из БД'.")
            
            messagebox.showwarning("Человек уже существует", message)
            
            if hasattr(self, 'notebook') and len(self.notebook.tabs()) > 1:
                self.notebook.select(1)
                
                for item in self.person_tree.get_children():
                    values = self.person_tree.item(item)['values']
                    if values[0] == duplicate_info[0]:
                        self.person_tree.selection_set(item)
                        self.person_tree.see(item)
                        break
            return
            
        self.result = {
            'action': 'new_known',
            'full_name': full_name,
            'short_name': short_name,
            'notes': self.notes_text.get('1.0', tk.END).strip()
        }
        self.destroy()
        
    def save_unknown(self):
        self.result = {'action': 'unknown'}
        self.destroy()
        
    def switch_to_db_tab(self):
        if hasattr(self, 'notebook'):
            self.notebook.select(1)
    
    def confirm_existing_selection(self):
        if not hasattr(self, 'person_tree'):
            return
            
        selection = self.person_tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите человека из списка")
            return
            
        item = self.person_tree.item(selection[0])
        person_id = item['values'][0]
        
        self.result = {
            'action': 'existing',
            'person_id': person_id
        }
        self.destroy()
        
    def cancel(self):
        self.result = None
        self.destroy()


class DogDialog(tk.Toplevel):
    """Диалог для ввода информации о собаке"""
    def __init__(self, parent, image, dog_bbox, existing_dogs=None, db_path=None):
        super().__init__(parent)
        self.parent = parent
        self.result = None
        self.existing_dogs = existing_dogs or []
        self.db_path = db_path
        
        self.title("Новая собака обнаружена")
        self.geometry("700x600")
        self.resizable(True, True)
        
        self.transient(parent)
        self.grab_set()
        
        self.protocol("WM_DELETE_WINDOW", self.save_unknown)
        
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        dog_frame = ttk.Frame(main_frame)
        dog_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        
        x1, y1, x2, y2 = dog_bbox
        dog_img = image[y1:y2, x1:x2]
        dog_img = cv2.cvtColor(dog_img, cv2.COLOR_BGR2RGB)
        dog_img = Image.fromarray(dog_img)
        
        dog_img.thumbnail((200, 200), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(dog_img)
        
        dog_label = ttk.Label(dog_frame, image=photo)
        dog_label.image = photo
        dog_label.pack()
        
        ttk.Label(dog_frame, text="Обнаружена собака", 
                 font=('Arial', 12, 'bold')).pack(pady=5)
        
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        new_dog_frame = ttk.Frame(self.notebook)
        self.notebook.add(new_dog_frame, text="Новая собака")
        
        input_frame = ttk.Frame(new_dog_frame, padding="20")
        input_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(input_frame, text="Кличка:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.name_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.name_var, width=40).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        ttk.Label(input_frame, text="Порода:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.breed_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.breed_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        ttk.Label(input_frame, text="Владелец:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.owner_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.owner_var, width=40).grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        ttk.Label(input_frame, text="Примечание:").grid(row=3, column=0, sticky=tk.W+tk.N, padx=5, pady=5)
        
        text_frame = ttk.Frame(input_frame)
        text_frame.grid(row=3, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        self.notes_text = tk.Text(text_frame, width=40, height=3, wrap=tk.WORD)
        self.notes_text.pack(fill=tk.BOTH, expand=True)
        
        input_frame.columnconfigure(1, weight=1)
        
        if self.existing_dogs:
            existing_frame = ttk.Frame(self.notebook)
            self.notebook.add(existing_frame, text="Выбрать из БД")
            
            tree_frame = ttk.Frame(existing_frame, padding="10")
            tree_frame.pack(fill=tk.BOTH, expand=True)
            
            columns = ('ID', 'Кличка', 'Порода', 'Владелец')
            self.dog_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=8)
            
            for col in columns:
                self.dog_tree.heading(col, text=col)
                if col == 'ID':
                    self.dog_tree.column(col, width=50)
                else:
                    self.dog_tree.column(col, width=180)
            
            tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.dog_tree.yview)
            self.dog_tree.configure(yscrollcommand=tree_scroll.set)
            
            for dog in self.existing_dogs:
                self.dog_tree.insert('', tk.END, values=(
                    dog['id'], 
                    dog['name'], 
                    dog['breed'] or 'Не указана',
                    dog['owner'] or 'Не указан'
                ))
            
            self.dog_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            ttk.Button(existing_frame, text="Использовать выбранную", 
                      command=self.confirm_existing_selection).pack(pady=10)
        
        button_frame = ttk.Frame(self)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

        # Создаем две рамки внутри основной рамки для кнопок
        left_button_frame = ttk.Frame(button_frame)
        left_button_frame.pack(side=tk.LEFT)

        right_button_frame = ttk.Frame(button_frame)
        right_button_frame.pack(side=tk.RIGHT)
        
        # Размещаем кнопки по разным сторонам
        ttk.Button(left_button_frame, text="Сохранить как известную", 
                  command=self.save_known).pack(side=tk.LEFT, padx=5)
        ttk.Button(left_button_frame, text="Оставить неизвестной", 
                  command=self.save_unknown).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(right_button_frame, text="Отмена", 
                  command=self.cancel).pack(side=tk.RIGHT, padx=5)
        
        self.center_window()
        
    def center_window(self):
        self.update_idletasks()
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        window_width = self.winfo_width()
        window_height = self.winfo_height()
        
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2) - 50
        
        if y < 0:
            y = 0
        if y + window_height > screen_height:
            y = screen_height - window_height - 40
            
        self.geometry(f'+{x}+{y}')
    
    def check_dog_exists(self, name, breed, owner):
        if not self.db_path:
            return False, []
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT id, name, breed, owner 
                FROM dogs 
                WHERE is_known = 1 AND name = ? AND breed = ? AND owner = ?
            ''', (name, breed, owner))
            
            duplicates = cursor.fetchall()
            
            if duplicates:
                return True, duplicates
            else:
                return False, []
                
        finally:
            conn.close()
        
    def save_known(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Предупреждение", "Введите кличку собаки")
            return
        
        breed = self.breed_var.get().strip()
        owner = self.owner_var.get().strip()
        
        exists, duplicates = self.check_dog_exists(name, breed, owner)
        
        if exists:
            duplicate_info = duplicates[0]
            message = (f"В базе данных уже есть собака с такими же данными:\n\n"
                      f"Кличка: {duplicate_info[1]}\n"
                      f"Порода: {duplicate_info[2] or 'Не указана'}\n"
                      f"Владелец: {duplicate_info[3] or 'Не указан'}\n\n"
                      f"Если это другая собака, пожалуйста, измените кличку, породу или владельца.\n"
                      f"Если это та же собака, выберите её из вкладки 'Выбрать из БД'.")
            
            messagebox.showwarning("Собака уже существует", message)
            
            if hasattr(self, 'notebook') and len(self.notebook.tabs()) > 1:
                self.notebook.select(1)
                
                for item in self.dog_tree.get_children():
                    values = self.dog_tree.item(item)['values']
                    if values[0] == duplicate_info[0]:
                        self.dog_tree.selection_set(item)
                        self.dog_tree.see(item)
                        break
            return
            
        self.result = {
            'action': 'new_known',
            'name': name,
            'breed': breed,
            'owner': owner,
            'notes': self.notes_text.get('1.0', tk.END).strip()
        }
        self.destroy()
        
    def save_unknown(self):
        self.result = {'action': 'unknown'}
        self.destroy()
        
    def confirm_existing_selection(self):
        if not hasattr(self, 'dog_tree'):
            return
            
        selection = self.dog_tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите собаку из списка")
            return
            
        item = self.dog_tree.item(selection[0])
        dog_id = item['values'][0]
        
        self.result = {
            'action': 'existing',
            'dog_id': dog_id
        }
        self.destroy()
        
    def cancel(self):
        self.result = None
        self.destroy()


class BodyWithoutFaceDialog(tk.Toplevel):
    """Диалог для идентификации человека без лица (только по фигуре)"""
    def __init__(self, parent, image, body_bbox, existing_persons=None, db_path=None):
        super().__init__(parent)
        self.parent = parent
        self.result = None
        self.existing_persons = existing_persons or []
        self.db_path = db_path
        
        self.title("Человек без распознанного лица")
        self.geometry("700x800")
        self.resizable(True, True)
        
        self.transient(parent)
        self.grab_set()
        
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        body_frame = ttk.Frame(main_frame)
        body_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        
        x1, y1, x2, y2 = body_bbox
        body_img = image[y1:y2, x1:x2]
        body_img = cv2.cvtColor(body_img, cv2.COLOR_BGR2RGB)
        body_img = Image.fromarray(body_img)
        
        body_img.thumbnail((200, 300), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(body_img)
        
        body_label = ttk.Label(body_frame, image=photo)
        body_label.image = photo
        body_label.pack()
        
        ttk.Label(body_frame, text="Человек без распознанного лица", 
                 font=('Arial', 12, 'bold')).pack(pady=5)
        
        info_text = ("Лицо этого человека не видно, поэтому автоматическое распознавание невозможно.\n"
                    "Если вы знаете этого человека, можете указать его данные.\n"
                    "Эта информация будет сохранена только для данного фото.")
        ttk.Label(main_frame, text=info_text, wraplength=650, justify=tk.CENTER).pack(pady=10)
        
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        input_tab = ttk.Frame(self.notebook)
        self.notebook.add(input_tab, text="Ввести данные")
        
        input_frame = ttk.Frame(input_tab, padding="20")
        input_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(input_frame, text="Полное имя:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.full_name_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.full_name_var, width=40).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        ttk.Label(input_frame, text="Короткое имя:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.short_name_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.short_name_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        ttk.Label(input_frame, text="Примечание:").grid(row=2, column=0, sticky=tk.W+tk.N, padx=5, pady=5)
        
        text_frame = ttk.Frame(input_frame)
        text_frame.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        self.notes_text = tk.Text(text_frame, width=40, height=3, wrap=tk.WORD)
        self.notes_text.pack(fill=tk.BOTH, expand=True)
        
        input_frame.columnconfigure(1, weight=1)
        
        if self.existing_persons:
            existing_tab = ttk.Frame(self.notebook)
            self.notebook.add(existing_tab, text="Выбрать из БД")
            
            tree_frame = ttk.Frame(existing_tab, padding="10")
            tree_frame.pack(fill=tk.BOTH, expand=True)
            
            columns = ('ID', 'Полное имя', 'Короткое имя')
            self.person_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=8)
            
            for col in columns:
                self.person_tree.heading(col, text=col)
                if col == 'ID':
                    self.person_tree.column(col, width=50)
                else:
                    self.person_tree.column(col, width=250)
            
            tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.person_tree.yview)
            self.person_tree.configure(yscrollcommand=tree_scroll.set)
            
            for person in self.existing_persons:
                self.person_tree.insert('', tk.END, values=(
                    person['id'], 
                    person['full_name'], 
                    person['short_name']
                ))
            
            self.person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            ttk.Button(existing_tab, text="Использовать выбранного", 
                      command=self.confirm_db_selection).pack(pady=10)
        
        button_frame = ttk.Frame(self)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        ttk.Button(button_frame, text="Сохранить информацию", 
                  command=self.save_local_info).pack(side=tk.LEFT, padx=5)
        if self.existing_persons:
            ttk.Button(button_frame, text="Выбрать из БД", 
                      command=self.switch_to_db_tab).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Пропустить (неизвестный)", 
                  command=self.skip).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Отмена", 
                  command=self.cancel).pack(side=tk.RIGHT, padx=5)
        
        self.center_window()
        
    def center_window(self):
        self.update_idletasks()
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        window_width = self.winfo_width()
        window_height = self.winfo_height()
        
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2) - 50
        
        if y < 0:
            y = 0
        if y + window_height > screen_height:
            y = screen_height - window_height - 40
            
        self.geometry(f'+{x}+{y}')
        
        self.update_idletasks()
        min_height = self.winfo_reqheight()
        if window_height < min_height:
            self.geometry(f"{window_width}x{min_height}+{x}+{y}")
    
    def check_person_exists(self, full_name, short_name):
        if not self.db_path:
            return False, []
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT id, full_name, short_name 
                FROM persons 
                WHERE is_known = 1 AND full_name = ? AND short_name = ?
            ''', (full_name, short_name))
            
            duplicates = cursor.fetchall()
            
            if duplicates:
                return True, duplicates
            else:
                return False, []
                
        finally:
            conn.close()
        
    def save_local_info(self):
        full_name = self.full_name_var.get().strip()
        if not full_name:
            messagebox.showwarning("Предупреждение", "Введите полное имя или нажмите 'Пропустить'")
            return
        
        short_name = self.short_name_var.get().strip() or full_name.split()[0]
        
        exists, duplicates = self.check_person_exists(full_name, short_name)
        
        if exists:
            duplicate_info = duplicates[0]
            message = (f"В базе данных уже есть человек с такими же именами:\n\n"
                      f"Полное имя: {duplicate_info[1]}\n"
                      f"Короткое имя: {duplicate_info[2]}\n\n"
                      f"Если это другой человек, пожалуйста, измените полное или короткое имя.\n"
                      f"Если это тот же человек, выберите его из вкладки 'Выбрать из БД'.")
            
            messagebox.showwarning("Человек уже существует", message)
            
            if hasattr(self, 'notebook') and len(self.notebook.tabs()) > 1:
                self.notebook.select(1)
                
                for item in self.person_tree.get_children():
                    values = self.person_tree.item(item)['values']
                    if values[0] == duplicate_info[0]:
                        self.person_tree.selection_set(item)
                        self.person_tree.see(item)
                        break
            return
            
        self.result = {
            'action': 'local_known',
            'full_name': full_name,
            'short_name': short_name,
            'notes': self.notes_text.get('1.0', tk.END).strip()
        }
        self.destroy()
    
    def switch_to_db_tab(self):
        if hasattr(self, 'notebook'):
            self.notebook.select(1)
    
    def confirm_db_selection(self):
        if not hasattr(self, 'person_tree'):
            return
            
        selection = self.person_tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите человека из списка")
            return
            
        item = self.person_tree.item(selection[0])
        person_id = item['values'][0]
        
        self.result = {
            'action': 'existing',
            'person_id': person_id
        }
        self.destroy()
        
    def skip(self):
        self.result = {'action': 'unknown'}
        self.destroy()
        
    def cancel(self):
        self.result = None
        self.destroy()


class FaceDetectionV2:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Face Detection v{VERSION} - Распознавание и учет людей и собак")
        self.root.geometry("1400x900")

        # --- Улучшение UI/UX: Стили и тема ---
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use('clam') 
        except tk.TclError:
            print("Тема 'clam' не найдена, используется тема по умолчанию.")
        
        self.style.configure('TNotebook.Tab', font=('Arial', 12, 'bold'), padding=[10, 5])
        self.style.configure('Status.TLabel', font=('Arial', 11, 'bold'), padding=5)
        self.style.configure('Idle.Status.TLabel', background='lightblue', foreground='black')
        self.style.configure('Processing.Status.TLabel', background='lightyellow', foreground='black')
        self.style.configure('Complete.Status.TLabel', background='lightgreen', foreground='black')
        self.style.configure('Error.Status.TLabel', background='lightcoral', foreground='black')
        
        self.update_queue = queue.Queue()
        
        # Переменные
        self.source_dir = tk.StringVar(value="")
        self.db_path_var = tk.StringVar(value="") # Для отображения пути к БД в UI
        self.include_subdirs = tk.BooleanVar(value=False)
        self.face_threshold = tk.DoubleVar(value=0.6)
        self.yolo_conf = tk.DoubleVar(value=0.5)
        self.yolo_model = tk.StringVar(value="yolov8n.pt")
        self.processing = False
        
        self.processed_mode = tk.StringVar(value="skip")
        self.processed_decision_for_all = None
        
        self.db_path = None # Путь к БД не задан при старте
        
        # init_database() не вызывается здесь, а только после выбора/создания файла БД
        self.create_widgets()
        
        self.version_label = ttk.Label(self.root, text=f"v{VERSION}", font=('Arial', 10))
        self.version_label.place(relx=0.99, y=5, anchor='ne')
        
        self.process_queue()
        
    def create_widgets(self):
        main_notebook = ttk.Notebook(self.root)
        main_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scan_frame = ttk.Frame(main_notebook)
        main_notebook.add(scan_frame, text="Сканирование")
        self.create_scan_tab(scan_frame)
        
        people_frame = ttk.Frame(main_notebook)
        main_notebook.add(people_frame, text="База людей")
        self.create_people_tab(people_frame)
        
        dogs_frame = ttk.Frame(main_notebook)
        main_notebook.add(dogs_frame, text="База собак")
        self.create_dogs_tab(dogs_frame)
        
    def create_scan_tab(self, parent):
        dir_frame = ttk.LabelFrame(parent, text="Настройки сканирования", padding="10")
        dir_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=10, pady=5)
        dir_frame.columnconfigure(1, weight=1)

        # --- Выбор директории с фото ---
        ttk.Label(dir_frame, text="Директория-источник:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(dir_frame, textvariable=self.source_dir, width=60).grid(row=0, column=1, padx=5, sticky=tk.EW)
        ttk.Button(dir_frame, text="Обзор...", command=self.browse_source).grid(row=0, column=2)
        
        ttk.Checkbutton(dir_frame, text="Включать поддиректории", 
                       variable=self.include_subdirs).grid(row=0, column=3, padx=20)
        
        # --- Управление базой данных ---
        ttk.Label(dir_frame, text="Файл Базы Данных:").grid(row=1, column=0, sticky=tk.W, pady=5)
        db_entry = ttk.Entry(dir_frame, textvariable=self.db_path_var, width=60, state='readonly')
        db_entry.grid(row=1, column=1, padx=5, sticky=tk.EW)
        
        db_button_frame = ttk.Frame(dir_frame)
        db_button_frame.grid(row=1, column=2, columnspan=2, sticky=tk.W)
        ttk.Button(db_button_frame, text="Обзор...", command=self.select_database_file).pack(side=tk.LEFT)
        ttk.Button(db_button_frame, text="Создать новую...", command=self.create_new_database).pack(side=tk.LEFT, padx=5)

        # --- Порог сходства лиц ---
        ttk.Label(dir_frame, text="Порог сходства лиц:").grid(row=2, column=0, sticky=tk.W, pady=5)
        threshold_frame = ttk.Frame(dir_frame)
        threshold_frame.grid(row=2, column=1, columnspan=3, sticky=tk.W, pady=5)
        
        self.threshold_label = ttk.Label(threshold_frame, text=f"{self.face_threshold.get():.2f}", font=('Arial', 10, 'bold'))
        def update_threshold_label(value): self.threshold_label.config(text=f"{float(value):.2f}")
        ttk.Scale(threshold_frame, from_=0.3, to=0.8, variable=self.face_threshold, 
                 orient=tk.HORIZONTAL, length=200, command=update_threshold_label).pack(side=tk.LEFT)
        self.threshold_label.pack(side=tk.LEFT, padx=10)
        ttk.Label(threshold_frame, text="(чем меньше значение, тем строже сравнение)", font=('Arial', 9, 'italic')).pack(side=tk.LEFT)

        # --- Настройка уверенности YOLO ---
        ttk.Label(dir_frame, text="Порог уверенности YOLO:").grid(row=3, column=0, sticky=tk.W, pady=5)
        yolo_conf_frame = ttk.Frame(dir_frame)
        yolo_conf_frame.grid(row=3, column=1, columnspan=3, sticky=tk.W, pady=5)

        self.yolo_conf_label = ttk.Label(yolo_conf_frame, text=f"{self.yolo_conf.get():.2f}", font=('Arial', 10, 'bold'))
        def update_yolo_conf_label(value): self.yolo_conf_label.config(text=f"{float(value):.2f}")
        ttk.Scale(yolo_conf_frame, from_=0.1, to=0.9, variable=self.yolo_conf,
                  orient=tk.HORIZONTAL, length=200, command=update_yolo_conf_label).pack(side=tk.LEFT)
        self.yolo_conf_label.pack(side=tk.LEFT, padx=10)
        ttk.Label(yolo_conf_frame, text="(уверенность модели в обнаружении объекта)", font=('Arial', 9, 'italic')).pack(side=tk.LEFT)

        # --- Выбор модели YOLO ---
        ttk.Label(dir_frame, text="Модель YOLO:").grid(row=4, column=0, sticky=tk.W, pady=5)
        model_frame = ttk.Frame(dir_frame)
        model_frame.grid(row=4, column=1, columnspan=2, sticky=tk.W, pady=5)

        models = ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt"]
        self.model_combo = ttk.Combobox(model_frame, textvariable=self.yolo_model, 
                                        values=models, state="readonly", width=15)
        self.model_combo.current(0)
        self.model_combo.pack(side=tk.LEFT)
        self.model_info_label = ttk.Label(model_frame, text="Nano (быстрая, ~6MB)", font=('Arial', 9), foreground='gray')
        self.model_info_label.pack(side=tk.LEFT, padx=10)
        def update_model_info(event=None):
            model_descriptions = {"yolov8n.pt": "Nano (быстрая, ~6MB)", "yolov8s.pt": "Small (баланс, ~22MB)",
                                  "yolov8m.pt": "Medium (точная, ~50MB)", "yolov8l.pt": "Large (очень точная, ~84MB)",
                                  "yolov8x.pt": "Extra (макс. точность, ~131MB)"}
            self.model_info_label.config(text=model_descriptions.get(self.yolo_model.get(), ""))
        self.model_combo.bind('<<ComboboxSelected>>', update_model_info)
        
        processed_frame = ttk.LabelFrame(dir_frame, text="Повторная обработка", padding="10")
        processed_frame.grid(row=5, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Radiobutton(processed_frame, text="Не обрабатывать (пропускать)", variable=self.processed_mode, value="skip").pack(anchor=tk.W)
        ttk.Radiobutton(processed_frame, text="Обрабатывать заново", variable=self.processed_mode, value="process").pack(anchor=tk.W)
        ttk.Radiobutton(processed_frame, text="Запрашивать для каждого", variable=self.processed_mode, value="ask").pack(anchor=tk.W)
        
        # --- Кнопки управления и статус ---
        control_frame = ttk.Frame(parent, padding="10")
        control_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5)
        
        self.start_btn = ttk.Button(control_frame, text="🚀 Начать сканирование", command=self.start_processing, state=tk.DISABLED)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="🛑 Остановить", command=self.stop_processing, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.exit_btn = ttk.Button(control_frame, text="Выход", command=self.root.destroy)
        self.exit_btn.pack(side=tk.RIGHT, padx=5)

        self.status_label = ttk.Label(control_frame, text="Готов к работе. Выберите или создайте БД.", style="Idle.Status.TLabel")
        self.status_label.pack(side=tk.LEFT, padx=20, fill=tk.X, expand=True)
        
        image_frame = ttk.LabelFrame(parent, text="Текущее изображение", padding="10")
        image_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=10)
        
        self.image_label = ttk.Label(image_frame)
        self.image_label.pack(expand=True, fill=tk.BOTH)
        
        log_frame = ttk.LabelFrame(parent, text="Лог обработки", padding="10")
        log_frame.grid(row=2, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=10)
        
        header_frame = ttk.Frame(log_frame)
        header_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.copy_btn = ttk.Button(header_frame, text="📋", width=3, command=self.copy_log_content)
        self.copy_btn.pack(side=tk.RIGHT)
        
        text_frame = ttk.Frame(log_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(text_frame, width=50, height=30, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        log_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text.bind('<Control-a>', self.select_all_log)
        self.log_text.bind('<Control-A>', self.select_all_log)
        
        parent.grid_rowconfigure(2, weight=1)
        parent.grid_columnconfigure(0, weight=2)
        parent.grid_columnconfigure(1, weight=1)
    
    def copy_log_content(self):
        content = self.log_text.get('1.0', tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        original_text = self.copy_btn['text']
        self.copy_btn.config(text="✓")
        self.root.after(1000, lambda: self.copy_btn.config(text=original_text))
        
    def select_all_log(self, event=None):
        self.log_text.tag_add(tk.SEL, "1.0", tk.END)
        self.log_text.mark_set(tk.INSERT, "1.0")
        self.log_text.see(tk.INSERT)
        return 'break'
        
    def create_people_tab(self, parent):
        toolbar = ttk.Frame(parent)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        self.btn_refresh_people = ttk.Button(toolbar, text="Обновить", command=self.refresh_people_list, state=tk.DISABLED)
        self.btn_refresh_people.pack(side=tk.LEFT, padx=5)
        self.btn_edit_person = ttk.Button(toolbar, text="Редактировать", command=self.edit_person, state=tk.DISABLED)
        self.btn_edit_person.pack(side=tk.LEFT, padx=5)
        self.btn_delete_person = ttk.Button(toolbar, text="Удалить", command=self.delete_person, state=tk.DISABLED)
        self.btn_delete_person.pack(side=tk.LEFT, padx=5)
        
        columns = ('ID', 'Статус', 'Полное имя', 'Короткое имя', 'Кол-во фото', 'Примечание')
        self.people_tree = ttk.Treeview(parent, columns=columns, show='headings')
        
        self.people_tree.heading('ID', text='ID'); self.people_tree.column('ID', width=50, anchor='center')
        self.people_tree.heading('Статус', text='Статус'); self.people_tree.column('Статус', width=100)
        self.people_tree.heading('Полное имя', text='Полное имя'); self.people_tree.column('Полное имя', width=200)
        self.people_tree.heading('Короткое имя', text='Короткое имя'); self.people_tree.column('Короткое имя', width=150)
        self.people_tree.heading('Кол-во фото', text='Фото'); self.people_tree.column('Кол-во фото', width=80, anchor='center')
        self.people_tree.heading('Примечание', text='Примечание'); self.people_tree.column('Примечание', width=300)
        
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.people_tree.yview)
        self.people_tree.configure(yscrollcommand=scrollbar.set)
        
        self.people_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def create_dogs_tab(self, parent):
        toolbar = ttk.Frame(parent)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        self.btn_refresh_dogs = ttk.Button(toolbar, text="Обновить", command=self.refresh_dogs_list, state=tk.DISABLED)
        self.btn_refresh_dogs.pack(side=tk.LEFT, padx=5)
        self.btn_edit_dog = ttk.Button(toolbar, text="Редактировать", command=self.edit_dog, state=tk.DISABLED)
        self.btn_edit_dog.pack(side=tk.LEFT, padx=5)
        self.btn_delete_dog = ttk.Button(toolbar, text="Удалить", command=self.delete_dog, state=tk.DISABLED)
        self.btn_delete_dog.pack(side=tk.LEFT, padx=5)
        
        columns = ('ID', 'Статус', 'Кличка', 'Порода', 'Владелец', 'Кол-во фото', 'Примечание')
        self.dogs_tree = ttk.Treeview(parent, columns=columns, show='headings')
        
        self.dogs_tree.heading('ID', text='ID'); self.dogs_tree.column('ID', width=50, anchor='center')
        self.dogs_tree.heading('Статус', text='Статус'); self.dogs_tree.column('Статус', width=100)
        self.dogs_tree.heading('Кличка', text='Кличка'); self.dogs_tree.column('Кличка', width=150)
        self.dogs_tree.heading('Порода', text='Порода'); self.dogs_tree.column('Порода', width=150)
        self.dogs_tree.heading('Владелец', text='Владелец'); self.dogs_tree.column('Владелец', width=150)
        self.dogs_tree.heading('Кол-во фото', text='Фото'); self.dogs_tree.column('Кол-во фото', width=80, anchor='center')
        self.dogs_tree.heading('Примечание', text='Примечание'); self.dogs_tree.column('Примечание', width=200)
        
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.dogs_tree.yview)
        self.dogs_tree.configure(yscrollcommand=scrollbar.set)
        
        self.dogs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def set_db_dependent_widgets_state(self, state):
        """Включает или выключает виджеты, зависящие от БД."""
        self.start_btn.config(state=state)
        self.btn_refresh_people.config(state=state)
        self.btn_edit_person.config(state=state)
        self.btn_delete_person.config(state=state)
        self.btn_refresh_dogs.config(state=state)
        self.btn_edit_dog.config(state=state)
        self.btn_delete_dog.config(state=state)
        
    def init_database(self, db_path):
        """Инициализирует структуру БД в указанном файле."""
        try:
            db_dir = os.path.dirname(db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS persons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    is_known BOOLEAN DEFAULT 0,
                    full_name TEXT,
                    short_name TEXT,
                    notes TEXT,
                    created_date TEXT,
                    updated_date TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dogs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    is_known BOOLEAN DEFAULT 0,
                    name TEXT,
                    breed TEXT,
                    owner TEXT,
                    notes TEXT,
                    created_date TEXT,
                    updated_date TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    created_date TEXT,
                    file_size INTEGER,
                    num_bodies INTEGER,
                    num_faces INTEGER,
                    num_dogs INTEGER DEFAULT 0,
                    processed_date TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS face_encodings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_id INTEGER,
                    image_id INTEGER,
                    face_encoding TEXT,
                    face_location TEXT,
                    FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE,
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS person_detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER,
                    person_id INTEGER,
                    person_index INTEGER,
                    bbox TEXT,
                    confidence REAL,
                    has_face BOOLEAN,
                    face_encoding_id INTEGER,
                    is_locally_identified BOOLEAN DEFAULT 0,
                    local_full_name TEXT,
                    local_short_name TEXT,
                    local_notes TEXT,
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
                    FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE,
                    FOREIGN KEY (face_encoding_id) REFERENCES face_encodings(id) ON DELETE SET NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dog_detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER,
                    dog_id INTEGER,
                    dog_index INTEGER,
                    bbox TEXT,
                    confidence REAL,
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
                    FOREIGN KEY (dog_id) REFERENCES dogs(id) ON DELETE CASCADE
                )
            ''')
            
            cursor.execute('PRAGMA foreign_keys = ON;')
            conn.commit()
            conn.close()
            
            self.log(f"База данных успешно инициализирована в файле: {db_path}")
            return True
        except Exception as e:
            self.log(f"Ошибка при инициализации БД: {e}")
            messagebox.showerror("Ошибка создания БД", f"Не удалось создать или инициализировать базу данных:\n{e}")
            return False

    def validate_database_structure(self, db_path):
        """Проверяет, что выбранный файл БД имеет корректную структуру."""
        REQUIRED_TABLES = {
            'persons': ['id', 'is_known', 'full_name', 'short_name'],
            'dogs': ['id', 'is_known', 'name'],
            'images': ['id', 'filename', 'filepath'],
            'face_encodings': ['id', 'person_id', 'image_id', 'face_encoding'],
            'person_detections': ['id', 'image_id', 'person_id', 'bbox', 'has_face'],
            'dog_detections': ['id', 'image_id', 'dog_id', 'bbox']
        }
        try:
            # Открываем в режиме "только чтение" для проверки
            conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            existing_tables = [row[0] for row in cursor.fetchall()]
            
            for table in REQUIRED_TABLES.keys():
                if table not in existing_tables:
                    messagebox.showerror("Ошибка структуры БД", f"Выбранная база данных некорректна.\nОтсутствует таблица: '{table}'")
                    conn.close()
                    return False

            for table, required_columns in REQUIRED_TABLES.items():
                cursor.execute(f"PRAGMA table_info({table})")
                existing_columns = [col[1] for col in cursor.fetchall()]
                for col in required_columns:
                    if col not in existing_columns:
                        messagebox.showerror("Ошибка структуры БД", f"Выбранная база данных некорректна.\nВ таблице '{table}' отсутствует столбец: '{col}'")
                        conn.close()
                        return False
            
            conn.close()
            return True
        except sqlite3.Error as e:
            messagebox.showerror("Ошибка чтения БД", f"Не удалось прочитать файл базы данных.\nОшибка: {e}\n\nВозможно, файл поврежден или не является файлом SQLite.")
            return False

    def select_database_file(self):
        """Диалог для выбора существующего файла БД."""
        filepath = filedialog.askopenfilename(
            title="Выберите файл базы данных",
            filetypes=[("Файлы баз данных", "*.db"), ("Все файлы", "*.*")]
        )
        if not filepath:
            return

        self.log(f"Проверка файла БД: {filepath}")
        if self.validate_database_structure(filepath):
            self.db_path = filepath
            self.db_path_var.set(filepath)
            self.log(f"База данных успешно загружена: {filepath}")
            self.set_db_dependent_widgets_state(tk.NORMAL)
            self.refresh_people_list()
            self.refresh_dogs_list()
            self.update_status("БД загружена. Готов к сканированию.", 'complete')
        else:
            self.log("Выбранный файл БД имеет неверную структуру.")
            self.db_path = None
            self.db_path_var.set("")
            self.set_db_dependent_widgets_state(tk.DISABLED)

    def create_new_database(self):
        """Диалог для создания нового файла БД."""
        filepath = filedialog.asksaveasfilename(
            title="Создать новый файл базы данных",
            defaultextension=".db",
            filetypes=[("Файлы баз данных", "*.db"), ("Все файлы", "*.*")]
        )
        if not filepath:
            return

        # init_database создаст файл и структуру
        if self.init_database(filepath):
            self.db_path = filepath
            self.db_path_var.set(filepath)
            self.set_db_dependent_widgets_state(tk.NORMAL)
            self.refresh_people_list() # Обновит пустые списки
            self.refresh_dogs_list()
            self.update_status("Новая БД создана. Готов к сканированию.", 'complete')
        else:
            self.db_path = None
            self.db_path_var.set("")
            self.set_db_dependent_widgets_state(tk.DISABLED)

    def browse_source(self):
        directory = filedialog.askdirectory(title="Выберите директорию с фотографиями")
        if directory:
            self.source_dir.set(directory)
            
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.update_queue.put(('log', f"[{timestamp}] {message}\n"))
        
    def update_image(self, image_path, annotated_image=None):
        self.update_queue.put(('image', (image_path, annotated_image)))
    
    def update_status(self, message, status_type):
        self.update_queue.put(('status', (message, status_type)))

    def show_processed_dialog_main(self, data):
        image_path, callback = data
        dialog = ProcessedImageDialog(self.root, image_path)
        self.root.wait_window(dialog)
        if dialog.result:
            callback(dialog.result, dialog.apply_to_all)
        else:
            callback('cancel', False)
        
    def is_image_processed(self, image_path):
        if not self.db_path: return False
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id FROM images WHERE filepath = ?', (image_path,))
            result = cursor.fetchone()
            return result is not None
        finally:
            conn.close()
            
    def clear_image_data(self, image_path):
        if not self.db_path: return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('PRAGMA foreign_keys = ON;')
        try:
            cursor.execute('SELECT id FROM images WHERE filepath = ?', (image_path,))
            result = cursor.fetchone()
            if result:
                image_id = result[0]
                cursor.execute('DELETE FROM images WHERE id = ?', (image_id,))
                conn.commit()
                self.log(f"  Старые данные для изображения {os.path.basename(image_path)} удалены.")
        finally:
            conn.close()
            
    def process_queue(self):
        """Обработка очереди обновлений GUI"""
        try:
            while True:
                action, data = self.update_queue.get_nowait()
                if action == 'log': self.log_text.insert(tk.END, data); self.log_text.see(tk.END)
                elif action == 'image': self.display_image(data[0], data[1])
                elif action == 'status':
                    message, status_type = data
                    self.status_label.config(text=message)
                    styles = {'idle': 'Idle.Status.TLabel', 'processing': 'Processing.Status.TLabel',
                              'complete': 'Complete.Status.TLabel', 'error': 'Error.Status.TLabel'}
                    self.status_label.config(style=styles.get(status_type, 'Idle.Status.TLabel'))
                elif action == 'enable_buttons':
                    self.start_btn.config(state=tk.NORMAL if self.db_path else tk.DISABLED)
                    self.stop_btn.config(state=tk.DISABLED)
                elif action == 'show_person_dialog': self.show_person_dialog_main(data)
                elif action == 'show_body_dialog': self.show_body_dialog_main(data)
                elif action == 'show_dog_dialog': self.show_dog_dialog_main(data)
                elif action == 'show_processed_dialog': self.show_processed_dialog_main(data)
                elif action == 'refresh_people': self.refresh_people_list()
                elif action == 'refresh_dogs': self.refresh_dogs_list()
        except queue.Empty: pass
        finally: self.root.after(100, self.process_queue)
            
    def display_image(self, image_path, annotated_image=None):
        try:
            if annotated_image is not None:
                image = cv2.cvtColor(annotated_image, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(image)
            else:
                image = Image.open(image_path)
                image = orient_image(image)
            
            self.image_label.update_idletasks()
            label_width = self.image_label.winfo_width()
            label_height = self.image_label.winfo_height()
            
            if label_width <= 1 or label_height <= 1: label_width, label_height = 700, 700
            
            max_width, max_height = label_width - 20, label_height - 20
            img_width, img_height = image.size
            scale = min(max_width / img_width, max_height / img_height, 1.0)
            
            new_width, new_height = int(img_width * scale), int(img_height * scale)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            photo = ImageTk.PhotoImage(image)
            self.image_label.config(image=photo)
            self.image_label.image = photo
        except Exception as e:
            self.log(f"Ошибка отображения изображения: {str(e)}")
            self.image_label.config(image=None, text=f"Не удалось показать\n{os.path.basename(image_path)}")

    def start_processing(self):
        # Проверка, что все пути заданы
        if not self.db_path:
            messagebox.showerror("Ошибка", "Необходимо выбрать или создать файл базы данных.")
            return
        if not self.source_dir.get() or not os.path.exists(self.source_dir.get()):
            messagebox.showerror("Ошибка", "Необходимо указать существующую директорию-источник с фотографиями.")
            return

        if not self.processing:
            self.processing = True
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.update_status("Инициализация...", 'processing')
            
            self.log(f"Инициализация модели {self.yolo_model.get()}...")
            try:
                self.yolo = YOLO(self.yolo_model.get())
                self.log("Модель YOLO загружена успешно.")
            except Exception as e:
                self.log(f"Ошибка загрузки модели YOLO: {str(e)}")
                self.update_status("Ошибка загрузки модели!", 'error')
                self.processing = False
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
                return
            
            thread = threading.Thread(target=self.process_images, daemon=True)
            thread.start()
            
    def stop_processing(self):
        self.processing = False
        self.log("Остановка обработки...")
        self.update_status("Остановка...", 'idle')

    def refresh_people_list(self):
        if not self.db_path: return
        for item in self.people_tree.get_children(): self.people_tree.delete(item)
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.id, CASE WHEN p.is_known THEN 'Известный' ELSE 'Неизвестный' END,
                       p.full_name, p.short_name, COUNT(DISTINCT pd.image_id), p.notes
                FROM persons p
                LEFT JOIN person_detections pd ON p.id = pd.person_id
                GROUP BY p.id ORDER BY p.is_known DESC, p.full_name
            ''')
            for row in cursor.fetchall(): self.people_tree.insert('', tk.END, values=row)
            conn.close()
        except Exception as e:
             self.log(f"Ошибка при обновлении списка людей: {str(e)}")
    
    def refresh_dogs_list(self):
        if not self.db_path: return
        for item in self.dogs_tree.get_children(): self.dogs_tree.delete(item)
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT d.id, CASE WHEN d.is_known THEN 'Известная' ELSE 'Неизвестная' END,
                       d.name, d.breed, d.owner, COUNT(DISTINCT dd.image_id), d.notes
                FROM dogs d
                LEFT JOIN dog_detections dd ON d.id = dd.dog_id
                GROUP BY d.id ORDER BY d.is_known DESC, d.name
            ''')
            for row in cursor.fetchall(): self.dogs_tree.insert('', tk.END, values=row)
            conn.close()
        except Exception as e:
             self.log(f"Ошибка при обновлении списка собак: {str(e)}")
            
    def edit_person(self):
        if not self.people_tree.selection():
            messagebox.showwarning("Предупреждение", "Выберите человека для редактирования")
            return
        messagebox.showinfo("В разработке", "Функция редактирования будет добавлена в будущих версиях.")
        
    def delete_person(self):
        if not self.people_tree.selection():
            messagebox.showwarning("Предупреждение", "Выберите человека для удаления")
            return
        if messagebox.askyesno("Подтверждение", "Вы уверены, что хотите удалить этого человека и все связанные с ним данные? Это действие необратимо."):
            item = self.people_tree.item(self.people_tree.selection()[0])
            person_id = item['values'][0]
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('PRAGMA foreign_keys = ON;')
            try:
                cursor.execute('DELETE FROM persons WHERE id = ?', (person_id,))
                conn.commit()
                self.refresh_people_list()
                messagebox.showinfo("Успех", "Человек успешно удален")
            except Exception as e: messagebox.showerror("Ошибка", f"Ошибка удаления: {str(e)}")
            finally: conn.close()
    
    def edit_dog(self):
        if not self.dogs_tree.selection():
            messagebox.showwarning("Предупреждение", "Выберите собаку для редактирования")
            return
        messagebox.showinfo("В разработке", "Функция редактирования будет добавлена в будущих версиях.")
        
    def delete_dog(self):
        if not self.dogs_tree.selection():
            messagebox.showwarning("Предупреждение", "Выберите собаку для удаления")
            return
        if messagebox.askyesno("Подтверждение", "Вы уверены, что хотите удалить эту собаку и все связанные с ней данные? Это действие необратимо."):
            item = self.dogs_tree.item(self.dogs_tree.selection()[0])
            dog_id = item['values'][0]
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('PRAGMA foreign_keys = ON;')
            try:
                cursor.execute('DELETE FROM dogs WHERE id = ?', (dog_id,))
                conn.commit()
                self.refresh_dogs_list()
                messagebox.showinfo("Успех", "Собака успешно удалена")
            except Exception as e: messagebox.showerror("Ошибка", f"Ошибка удаления: {str(e)}")
            finally: conn.close()

    def identify_person(self, face_encoding):
        if not self.db_path: return None
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT fe.id, fe.person_id, fe.face_encoding, p.full_name, p.short_name
                FROM face_encodings fe
                JOIN persons p ON fe.person_id = p.id
                WHERE p.is_known = 1
            ''')
            
            known_faces = cursor.fetchall()
            
            if not known_faces:
                return None
            
            known_encodings_np = [np.array(json.loads(face[2])) for face in known_faces]
            if not known_encodings_np:
                return None

            distances = face_recognition.face_distance(known_encodings_np, face_encoding)
            
            min_distance_idx = np.argmin(distances)
            min_distance = distances[min_distance_idx]
            
            if min_distance < self.face_threshold.get():
                face_id, person_id, _, full_name, short_name = known_faces[min_distance_idx]
                return {
                    'person_id': person_id,
                    'full_name': full_name,
                    'short_name': short_name,
                    'distance': min_distance
                }
            
            return None
            
        finally:
            conn.close()
            
    def get_existing_persons(self):
        if not self.db_path: return []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id, full_name, short_name FROM persons WHERE is_known = 1 ORDER BY full_name')
            return [{'id': row[0], 'full_name': row[1], 'short_name': row[2]} for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def get_existing_dogs(self):
        if not self.db_path: return []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id, name, breed, owner FROM dogs WHERE is_known = 1 ORDER BY name')
            return [{'id': row[0], 'name': row[1], 'breed': row[2], 'owner': row[3]} for row in cursor.fetchall()]
        finally:
            conn.close()
            
    def show_person_dialog_main(self, data):
        image, face_location, face_encoding, callback = data
        existing_persons = self.get_existing_persons()
        dialog = PersonDialog(self.root, image, face_location, existing_persons, self.db_path)
        self.root.wait_window(dialog)
        callback(dialog.result)
            
    def show_body_dialog_main(self, data):
        image, body_bbox, callback = data
        existing_persons = self.get_existing_persons()
        dialog = BodyWithoutFaceDialog(self.root, image, body_bbox, existing_persons, self.db_path)
        self.root.wait_window(dialog)
        callback(dialog.result)
    
    def show_dog_dialog_main(self, data):
        image, dog_bbox, callback = data
        existing_dogs = self.get_existing_dogs()
        dialog = DogDialog(self.root, image, dog_bbox, existing_dogs, self.db_path)
        self.root.wait_window(dialog)
        callback(dialog.result)
            
    def create_or_update_person(self, result, face_encoding=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        person_id = None
        try:
            now = datetime.now().isoformat()
            if result['action'] == 'new_known':
                cursor.execute('INSERT INTO persons (is_known, full_name, short_name, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?)',
                               (result['full_name'], result['short_name'], result['notes'], now, now))
                person_id = cursor.lastrowid
                self.log(f"  Создан новый человек: {result['full_name']}")
            elif result['action'] == 'unknown':
                cursor.execute('INSERT INTO persons (is_known, created_date, updated_date) VALUES (0, ?, ?)', (now, now))
                person_id = cursor.lastrowid
                self.log(f"  Добавлен неизвестный человек (ID: {person_id})")
            elif result['action'] == 'existing':
                person_id = result['person_id']
                cursor.execute('SELECT full_name FROM persons WHERE id = ?', (person_id,))
                name = cursor.fetchone()[0]
                self.log(f"  Идентифицирован как: {name}")
            elif result['action'] == 'local_known':
                cursor.execute('INSERT INTO persons (is_known, full_name, short_name, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?)',
                               (result['full_name'], result['short_name'], result.get('notes', ''), now, now))
                person_id = cursor.lastrowid
                self.log(f"  Создан новый человек (без лица): {result['full_name']}")
            conn.commit()
            return person_id
        except Exception as e:
            self.log(f"Ошибка при создании/обновлении человека: {str(e)}")
            return None
        finally:
            conn.close()
    
    def create_or_update_dog(self, result):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        dog_id = None
        try:
            now = datetime.now().isoformat()
            if result['action'] == 'new_known':
                cursor.execute('INSERT INTO dogs (is_known, name, breed, owner, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?, ?)',
                               (result['name'], result.get('breed', ''), result.get('owner', ''), result.get('notes', ''), now, now))
                dog_id = cursor.lastrowid
                self.log(f"  Создана новая собака: {result['name']}")
            elif result['action'] == 'unknown':
                cursor.execute('INSERT INTO dogs (is_known, created_date, updated_date) VALUES (0, ?, ?)', (now, now))
                dog_id = cursor.lastrowid
                self.log(f"  Добавлена неизвестная собака (ID: {dog_id})")
            elif result['action'] == 'existing':
                dog_id = result['dog_id']
                cursor.execute('SELECT name FROM dogs WHERE id = ?', (dog_id,))
                name = cursor.fetchone()[0]
                self.log(f"  Идентифицирована как: {name}")
            conn.commit()
            return dog_id
        except Exception as e:
            self.log(f"Ошибка при создании/обновлении собаки: {str(e)}")
            return None
        finally:
            conn.close()
            
    def detect_faces_and_bodies(self, image_path, image_id):
        # Эта версия метода с "жадным" алгоритмом сопоставления была возвращена по просьбе пользователя
        # Если проблема останется, можно будет вернуться к последней предложенной версии.
        # Для простоты отладки пока используется оригинальная логика.
        try:
            pil_image = Image.open(image_path)
            oriented_pil_image = orient_image(pil_image)
            image = cv2.cvtColor(np.array(oriented_pil_image), cv2.COLOR_RGB2BGR)
            
            if image is None:
                self.log(f"  Ошибка: не удалось загрузить или сконвертировать изображение")
                return 0, 0, 0, [], [], None, [], []
                
            COLOR_BODY_NO_FACE, COLOR_FACE_NO_BODY, COLOR_BODY_WITH_FACE = (0, 255, 255), (0, 0, 255), (0, 255, 0)
            COLOR_KNOWN_PERSON, COLOR_DOG, COLOR_KNOWN_DOG = (255, 0, 255), (255, 165, 0), (128, 0, 128)
            
            results = self.yolo(image, conf=self.yolo_conf.get())
            
            person_detections, dog_detections, annotated_image = [], [], image.copy()
            
            for r in results:
                if r.boxes:
                    person_idx, dog_idx = 0, 0
                    for box in r.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        confidence, class_id = box.conf[0].cpu().numpy(), int(box.cls[0].cpu().numpy())
                        if class_id == 0:
                            person_detections.append({'person_index': person_idx, 'bbox': [int(x1), int(y1), int(x2), int(y2)], 'confidence': float(confidence), 'has_face': False, 'face_encoding': None, 'face_location': None, 'person_id': None, 'is_known': False, 'is_locally_identified': False, 'local_full_name': None, 'local_short_name': None, 'local_notes': None})
                            person_idx += 1
                        elif class_id == 16:
                            dog_detections.append({'dog_index': dog_idx, 'bbox': [int(x1), int(y1), int(x2), int(y2)], 'confidence': float(confidence), 'dog_id': None, 'is_known': False})
                            dog_idx += 1
                
            self.log(f"  YOLO обнаружил людей: {len(person_detections)}, собак: {len(dog_detections)}")
            
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_image, model='hog')
            face_encodings = face_recognition.face_encodings(rgb_image, face_locations)
            
            self.log(f"  face_recognition обнаружил лиц: {len(face_locations)}")
            
            unmatched_faces = []
            
            for face_idx, (face_location, face_encoding) in enumerate(zip(face_locations, face_encodings)):
                top, right, bottom, left = face_location
                face_center_x, face_center_y = (left + right) // 2, (top + bottom) // 2
                best_person_idx, best_overlap = -1, 0
                
                for person_idx, person in enumerate(person_detections):
                    px1, py1, px2, py2 = person['bbox']
                    if px1 <= face_center_x <= px2 and py1 <= face_center_y <= py2:
                        intersection_area = (min(right, px2) - max(left, px1)) * (min(bottom, py2) - max(top, py1))
                        face_area = (right - left) * (bottom - top)
                        if intersection_area > 0 and face_area > 0:
                            overlap = intersection_area / face_area
                            if overlap > best_overlap:
                                best_overlap, best_person_idx = overlap, person_idx
                
                if best_person_idx >= 0 and best_overlap > 0.5:
                    self.log(f"    Лицо {face_idx} сопоставлено с человеком {best_person_idx}")
                    person_detections[best_person_idx]['has_face'] = True
                    person_detections[best_person_idx]['face_encoding'] = face_encoding
                    person_detections[best_person_idx]['face_location'] = face_location
                    
                    match = self.identify_person(face_encoding)
                    if match:
                        person_detections[best_person_idx]['person_id'] = match['person_id']
                        person_detections[best_person_idx]['is_known'] = True
                        self.log(f"  Распознан: {match['full_name']} (сходство: {1-match['distance']:.2%})")
                else:
                    self.log(f"    Лицо {face_idx} не сопоставлено ни с одним человеком")
                    unmatched_faces.append({'face_location': face_location, 'face_encoding': face_encoding, 'person_id': None, 'is_known': False})
            
            self.update_image(image_path, annotated_image)
            
            for person in person_detections:
                if person['has_face'] and person['person_id'] is None:
                    self.log(f"  Диалог для неизвестного человека с лицом...")
                    dialog_event = threading.Event()
                    dialog_result = {'result': None}
                    def callback(result):
                        dialog_result['result'] = result
                        dialog_event.set()
                    self.update_queue.put(('show_person_dialog', (image, person['face_location'], person['face_encoding'], callback)))
                    dialog_event.wait()
                    if dialog_result['result']:
                        person_id = self.create_or_update_person(dialog_result['result'], person['face_encoding'])
                        if person_id: 
                            person['person_id'] = person_id
                            person['is_known'] = dialog_result['result']['action'] != 'unknown'
            
            for face_idx, face_data in enumerate(unmatched_faces):
                self.log(f"  Диалог для лица без тела #{face_idx}...")
                dialog_event = threading.Event()
                dialog_result = {'result': None}
                def callback(result):
                    dialog_result['result'] = result
                    dialog_event.set()
                self.update_queue.put(('show_person_dialog', (image, face_data['face_location'], face_data['face_encoding'], callback)))
                dialog_event.wait()
                if dialog_result['result']:
                    person_id = self.create_or_update_person(dialog_result['result'], face_data['face_encoding'])
                    if person_id: 
                        face_data['person_id'] = person_id
                        face_data['is_known'] = dialog_result['result']['action'] != 'unknown'

            for person in person_detections:
                if not person['has_face']:
                    self.log(f"  Диалог для человека {person['person_index']} без лица...")
                    dialog_event = threading.Event()
                    dialog_result = {'result': None}
                    def callback(result):
                        dialog_result['result'] = result
                        dialog_event.set()
                    self.update_queue.put(('show_body_dialog', (image, person['bbox'], callback)))
                    dialog_event.wait()
                    if dialog_result['result']:
                        action = dialog_result['result']['action']
                        person_id = self.create_or_update_person(dialog_result['result'], None)
                        if person_id:
                            person['person_id'] = person_id
                            person['is_known'] = action != 'unknown'
                            if action == 'local_known':
                                person.update({'is_locally_identified': True, 'local_full_name': dialog_result['result']['full_name'], 'local_short_name': dialog_result['result']['short_name'], 'local_notes': dialog_result['result']['notes']})
            
            for dog in dog_detections:
                self.log(f"  Диалог для собаки {dog['dog_index']}...")
                dialog_event = threading.Event()
                dialog_result = {'result': None}
                def callback(result):
                    dialog_result['result'] = result
                    dialog_event.set()
                self.update_queue.put(('show_dog_dialog', (image, dog['bbox'], callback)))
                dialog_event.wait()
                if dialog_result['result']:
                    dog_id = self.create_or_update_dog(dialog_result['result'])
                    if dog_id: 
                        dog['dog_id'] = dog_id
                        dog['is_known'] = dialog_result['result']['action'] != 'unknown'

            annotated_image = image.copy()
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for person in person_detections:
                x1, y1, x2, y2 = person['bbox']
                color, label_text = (COLOR_BODY_NO_FACE, "Неизвестный без лица")
                if person['has_face']: color, label_text = (COLOR_BODY_WITH_FACE, "Неизвестный с лицом")
                if person['is_known']:
                    color = COLOR_KNOWN_PERSON
                    cursor.execute('SELECT short_name FROM persons WHERE id = ?', (person['person_id'],))
                    res = cursor.fetchone()
                    label_text = res[0] if res else 'Известный'
                cv2.rectangle(annotated_image, (x1, y1), (x2, y2), color, 3)
                cv2.putText(annotated_image, label_text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            for face_data in unmatched_faces:
                top, right, bottom, left = face_data['face_location']
                cv2.rectangle(annotated_image, (left, top), (right, bottom), COLOR_FACE_NO_BODY, 2)
                cv2.putText(annotated_image, 'Лицо без тела', (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_FACE_NO_BODY, 2)

            for dog in dog_detections:
                x1, y1, x2, y2 = dog['bbox']
                color, label = (COLOR_DOG, 'Неизвестная собака')
                if dog['is_known']:
                    color = COLOR_KNOWN_DOG
                    cursor.execute('SELECT name FROM dogs WHERE id = ?', (dog['dog_id'],))
                    res = cursor.fetchone()
                    label = res[0] if res else 'Известная'
                
                cv2.rectangle(annotated_image, (x1, y1), (x2, y2), color, 3)
                cv2.putText(annotated_image, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            conn.close()
            return len(person_detections), len(face_locations), len(dog_detections), face_encodings, person_detections, annotated_image, unmatched_faces, dog_detections
            
        except Exception as e:
            self.log(f"Критическая ошибка при детекции: {str(e)}")
            import traceback; self.log(f"  Traceback: {traceback.format_exc()}")
            return 0, 0, 0, [], [], None, [], []
            
    def save_to_database(self, image_path, image_id, num_bodies, num_faces, num_dogs, face_encodings, person_detections, unmatched_faces, dog_detections):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            for person in person_detections:
                face_encoding_id = None
                if person['has_face'] and person['face_encoding'] is not None and person.get('person_id'):
                    encoding_json, location_json = json.dumps(person['face_encoding'].tolist()), json.dumps(person['face_location'])
                    cursor.execute('INSERT INTO face_encodings (person_id, image_id, face_encoding, face_location) VALUES (?, ?, ?, ?)',
                                   (person['person_id'], image_id, encoding_json, location_json))
                    face_encoding_id = cursor.lastrowid
                
                bbox_json = json.dumps(person['bbox'])
                cursor.execute('''
                    INSERT INTO person_detections (image_id, person_id, person_index, bbox, confidence, has_face, face_encoding_id, 
                    is_locally_identified, local_full_name, local_short_name, local_notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (image_id, person.get('person_id'), person['person_index'], bbox_json, person['confidence'], person['has_face'], 
                     face_encoding_id, person.get('is_locally_identified', False), person.get('local_full_name'), 
                     person.get('local_short_name'), person.get('local_notes')))
            
            for face_data in unmatched_faces:
                if face_data['face_encoding'] is not None and face_data.get('person_id'):
                    encoding_json, location_json = json.dumps(face_data['face_encoding'].tolist()), json.dumps(face_data['face_location'])
                    cursor.execute('INSERT INTO face_encodings (person_id, image_id, face_encoding, face_location) VALUES (?, ?, ?, ?)',
                                   (face_data['person_id'], image_id, encoding_json, location_json))
            
            for dog in dog_detections:
                bbox_json = json.dumps(dog['bbox'])
                cursor.execute('INSERT INTO dog_detections (image_id, dog_id, dog_index, bbox, confidence) VALUES (?, ?, ?, ?, ?)',
                               (image_id, dog.get('dog_id'), dog.get('dog_index'), bbox_json, dog['confidence'])) 
            conn.commit()
        except Exception as e: self.log(f"Ошибка при сохранении в БД: {str(e)}")
        finally: conn.close()
            
    def process_images(self):
        try:
            source = self.source_dir.get()
            image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
            
            image_files = []
            if self.include_subdirs.get():
                for root, _, files in os.walk(source):
                    for file in files:
                        if Path(file).suffix.lower() in image_extensions:
                            image_files.append(os.path.join(root, file))
            else:
                for file in os.listdir(source):
                    path = os.path.join(source, file)
                    if os.path.isfile(path) and Path(file).suffix.lower() in image_extensions:
                        image_files.append(path)
                        
            self.log(f"Найдено изображений: {len(image_files)}")
            self.processed_decision_for_all = None
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('PRAGMA foreign_keys = ON;')
            
            for i, image_path in enumerate(image_files):
                if not self.processing:
                    self.log("Обработка прервана пользователем.")
                    break
                    
                self.update_status(f"Обработка {i+1}/{len(image_files)}: {os.path.basename(image_path)}", 'processing')
                self.log(f"\nОбработка: {os.path.basename(image_path)}")
                self.update_image(image_path, None)
                
                if self.is_image_processed(image_path):
                    self.log(f"  Изображение уже было обработано ранее")
                    process_mode, decision = self.processed_mode.get(), self.processed_decision_for_all
                    if decision is None:
                        if process_mode in ('skip', 'process'): decision = process_mode
                        elif process_mode == 'ask':
                            dialog_event = threading.Event()
                            dialog_result = {'result': None, 'apply_to_all': False}
                            def callback(result, apply_to_all):
                                dialog_result['result'] = result
                                dialog_result['apply_to_all'] = apply_to_all
                                dialog_event.set()
                            self.update_queue.put(('show_processed_dialog', (image_path, callback)))
                            dialog_event.wait()
                            decision = dialog_result['result']
                            if dialog_result['apply_to_all']: self.processed_decision_for_all = decision

                    if decision == 'skip': self.log(f"  Пропускаем."); continue
                    elif decision == 'cancel': self.log(f"  Обработка отменена пользователем."); break
                    elif decision == 'process': self.log(f"  Обрабатываем заново."); self.clear_image_data(image_path)

                file_stat = os.stat(image_path)
                created_date, now = datetime.fromtimestamp(file_stat.st_ctime).isoformat(), datetime.now().isoformat()
                cursor.execute('INSERT INTO images (filename, filepath, created_date, file_size, processed_date) VALUES (?, ?, ?, ?, ?)',
                               (os.path.basename(image_path), image_path, created_date, file_stat.st_size, now))
                image_id = cursor.lastrowid
                conn.commit()
                
                (num_bodies, num_faces, num_dogs, face_encodings, person_detections, 
                 annotated_image, unmatched_faces, dog_detections) = self.detect_faces_and_bodies(image_path, image_id)
                    
                self.update_image(image_path, annotated_image)
                self.log(f"  Найдено фигур: {num_bodies}, лиц: {num_faces}, собак: {num_dogs}")
                cursor.execute('UPDATE images SET num_bodies = ?, num_faces = ?, num_dogs = ? WHERE id = ?', (num_bodies, num_faces, num_dogs, image_id))
                conn.commit()
                
                self.save_to_database(image_path, image_id, num_bodies, num_faces, num_dogs, face_encodings, person_detections, unmatched_faces, dog_detections)
                
            conn.close()
            self.log(f"\nОбработка завершена!")
            self.update_status("Обработка завершена", 'complete')
            self.update_queue.put(('refresh_people', None))
            self.update_queue.put(('refresh_dogs', None))
        except Exception as e:
            self.log(f"Критическая ошибка в процессе обработки: {str(e)}")
            self.update_status("Ошибка в процессе обработки!", 'error')
            import traceback; self.log(f"  Traceback: {traceback.format_exc()}")
        finally:
            self.processing = False
            self.update_queue.put(('enable_buttons', None))


def main():
    root = tk.Tk()
    app = FaceDetectionV2(root)
    root.mainloop()

if __name__ == "__main__":
    main()