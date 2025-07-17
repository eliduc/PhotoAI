"""
Face Detection v3.3 
Программа для распознавания и учета людей и собак на фотографиях

Версия: 3.3
- Добавлена новая функциональность: возможность выбора людей и собак
  из справочной БД при идентификации.
- В диалоговые окна PersonDialog и DogDialog добавлена третья вкладка
  "Выбрать из справочной БД", которая позволяет импортировать записи.
- Реализована логика создания новой записи в основной БД при импорте
  из справочной, включая сохранение векторов лиц.
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
import traceback

# Версия программы
VERSION = "3.2.0"

def orient_image(img: Image.Image) -> Image.Image:
    """Применяет поворот к изображению на основе его EXIF-данных."""
    try:
        exif = img.getexif()
        orientation_tag = 274
        if orientation_tag in exif:
            orientation = exif[orientation_tag]
            if orientation == 3: img = img.rotate(180, expand=True)
            elif orientation == 6: img = img.rotate(270, expand=True)
            elif orientation == 8: img = img.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError):
        pass
    return img

class BaseDialog(tk.Toplevel):
    """Базовый класс для всех диалоговых окон с улучшенным центрированием."""
    def center_window(self):
        self.update_idletasks()
        req_width = self.winfo_reqwidth()
        req_height = self.winfo_reqheight()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (req_width // 2)
        y = (screen_height // 2) - (req_height // 2) - 50
        y = max(y, 20)
        self.geometry(f'{req_width}x{req_height}+{x}+{y}')

class ProcessedImageDialog(BaseDialog):
    def __init__(self, parent, image_path):
        super().__init__(parent)
        self.parent = parent; self.result = None; self.apply_to_all = False
        self.title("Изображение уже обработано"); self.resizable(False, False); self.transient(parent); self.grab_set()
        main_frame = ttk.Frame(self, padding="20"); main_frame.pack(fill=tk.BOTH, expand=True)
        message = f"Изображение '{os.path.basename(image_path)}' уже было обработано ранее.\nОбработать его заново?"
        ttk.Label(main_frame, text=message, wraplength=450).pack(pady=10)
        self.apply_to_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(main_frame, text="Применить это решение для всех последующих изображений", variable=self.apply_to_all_var).pack(pady=10)
        button_frame = ttk.Frame(main_frame); button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        ttk.Button(button_frame, text="Да, обработать", command=self.process).pack(side=tk.LEFT, padx=5, expand=True)
        ttk.Button(button_frame, text="Нет, пропустить", command=self.skip).pack(side=tk.LEFT, padx=5, expand=True)
        ttk.Button(button_frame, text="Отмена", command=self.cancel).pack(side=tk.RIGHT, padx=5, expand=True)
        self.center_window()
    def process(self): self.result = 'process'; self.apply_to_all = self.apply_to_all_var.get(); self.destroy()
    def skip(self): self.result = 'skip'; self.apply_to_all = self.apply_to_all_var.get(); self.destroy()
    def cancel(self): self.result = 'cancel'; self.destroy()

class PersonDialog(BaseDialog):
    def __init__(self, parent, image, face_location, existing_persons=None, ref_persons=None, db_path=None):
        super().__init__(parent)
        self.parent = parent; self.result = None
        self.existing_persons = existing_persons or []
        self.ref_persons = ref_persons or []
        self.db_path = db_path
        self.title("Идентификация человека"); self.resizable(True, True); self.transient(parent); self.grab_set(); self.protocol("WM_DELETE_WINDOW", self.save_unknown)
        main_frame = ttk.Frame(self); main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        face_frame = ttk.Frame(main_frame); face_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        top, right, bottom, left = face_location; face_img = image[top:bottom, left:right]; face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB); face_img = Image.fromarray(face_img)
        face_img.thumbnail((150, 150), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(face_img)
        face_label = ttk.Label(face_frame, image=photo); face_label.image = photo; face_label.pack()
        ttk.Label(face_frame, text="Обнаружен новый человек", font=('Arial', 12, 'bold')).pack(pady=5)
        self.notebook = ttk.Notebook(main_frame); self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Вкладка 1: Новый человек
        new_person_frame = ttk.Frame(self.notebook); self.notebook.add(new_person_frame, text="Новый человек")
        input_frame = ttk.Frame(new_person_frame, padding="20"); input_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(input_frame, text="Полное имя:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5); self.full_name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.full_name_var, width=40).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text="Короткое имя:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5); self.short_name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.short_name_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text="Примечание:").grid(row=2, column=0, sticky=tk.W+tk.N, padx=5, pady=5); text_frame = ttk.Frame(input_frame); text_frame.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        self.notes_text = tk.Text(text_frame, width=40, height=4, wrap=tk.WORD); notes_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.notes_text.yview); self.notes_text.configure(yscrollcommand=notes_scroll.set)
        self.notes_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); notes_scroll.pack(side=tk.RIGHT, fill=tk.Y); input_frame.columnconfigure(1, weight=1)
        
        # Вкладка 2: Выбрать из основной БД
        if self.existing_persons:
            existing_frame = ttk.Frame(self.notebook); self.notebook.add(existing_frame, text="Выбрать из БД")
            tree_frame = ttk.Frame(existing_frame, padding="10"); tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', 'Полное имя', 'Короткое имя'); self.person_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.person_tree.heading(col, text=col); self.person_tree.column(col, width=50 if col == 'ID' else 200)
            tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.person_tree.yview); self.person_tree.configure(yscrollcommand=tree_scroll.set)
            for person in self.existing_persons: self.person_tree.insert('', tk.END, values=(person['id'], person['full_name'], person['short_name']))
            self.person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Вкладка 3: Выбрать из справочной БД
        if self.ref_persons:
            ref_frame = ttk.Frame(self.notebook); self.notebook.add(ref_frame, text="Выбрать из справочной БД")
            ref_tree_frame = ttk.Frame(ref_frame, padding="10"); ref_tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', 'Полное имя', 'Короткое имя'); self.ref_person_tree = ttk.Treeview(ref_tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.ref_person_tree.heading(col, text=col); self.ref_person_tree.column(col, width=50 if col == 'ID' else 200)
            ref_tree_scroll = ttk.Scrollbar(ref_tree_frame, orient="vertical", command=self.ref_person_tree.yview); self.ref_person_tree.configure(yscrollcommand=ref_tree_scroll.set)
            for person in self.ref_persons: self.ref_person_tree.insert('', tk.END, values=(person['id'], person['full_name'], person['short_name']))
            self.ref_person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); ref_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        button_frame = ttk.Frame(self); button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10); left_buttons = ttk.Frame(button_frame); left_buttons.pack(side=tk.LEFT); right_buttons = ttk.Frame(button_frame); right_buttons.pack(side=tk.RIGHT)
        ttk.Button(left_buttons, text="Сохранить как известного", command=self.save_known).pack(side=tk.LEFT, padx=5)
        ttk.Button(left_buttons, text="Оставить неизвестным", command=self.save_unknown).pack(side=tk.LEFT, padx=5)
        ttk.Button(right_buttons, text="Отмена", command=self.cancel).pack(side=tk.RIGHT, padx=5)
        self.center_window(); self.full_name_var.set(""); self.notebook.select(0); self.after(100, lambda: self.focus_force())
    
    def check_person_exists(self, full_name, short_name):
        if not self.db_path: return False, []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, full_name, short_name FROM persons WHERE is_known = 1 AND full_name = ? AND short_name = ?', (full_name, short_name)); return (dups := cursor.fetchall()), dups
    
    def save_known(self):
        try:
            active_tab_text = self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError:
            active_tab_text = "Новый человек"

        # --- Логика для вкладки "Новый человек" ---
        if active_tab_text == "Новый человек":
            full_name = self.full_name_var.get().strip(); short_name = self.short_name_var.get().strip() or full_name.split()[0]
            if not full_name: messagebox.showwarning("Предупреждение", "Введите полное имя", parent=self); return
            exists, duplicates = self.check_person_exists(full_name, short_name)
            if exists: messagebox.showwarning("Человек уже существует", f"В базе данных уже есть человек с такими же именами:\n\nПолное имя: {duplicates[0][1]}\nКороткое имя: {duplicates[0][2]}\n\nЕсли это другой человек, измените имя. Если тот же, выберите его из другой вкладки.", parent=self); return
            self.result = {'action': 'new_known', 'full_name': full_name, 'short_name': short_name, 'notes': self.notes_text.get('1.0', tk.END).strip()}; self.destroy()
        
        # --- Логика для вкладки "Выбрать из БД" ---
        elif active_tab_text == "Выбрать из БД":
            if not hasattr(self, 'person_tree') or not (selection := self.person_tree.selection()): messagebox.showwarning("Предупреждение", "Выберите человека из списка", parent=self); return
            self.result = {'action': 'existing', 'person_id': self.person_tree.item(selection[0])['values'][0]}; self.destroy()

        # --- Логика для вкладки "Выбрать из справочной БД" ---
        elif active_tab_text == "Выбрать из справочной БД":
            if not hasattr(self, 'ref_person_tree') or not (selection := self.ref_person_tree.selection()): messagebox.showwarning("Предупреждение", "Выберите человека из списка", parent=self); return
            selected_id = self.ref_person_tree.item(selection[0])['values'][0]
            person_info = next((p for p in self.ref_persons if p['id'] == selected_id), None)
            self.result = {'action': 'existing_ref', 'person_info': person_info}; self.destroy()

    def save_unknown(self): self.result = {'action': 'unknown'}; self.destroy()
    def cancel(self): self.result = None; self.destroy()

class DogDialog(BaseDialog):
    def __init__(self, parent, image, dog_bbox, existing_dogs=None, ref_dogs=None, db_path=None):
        super().__init__(parent); self.parent = parent; self.result = None
        self.existing_dogs = existing_dogs or []; self.ref_dogs = ref_dogs or []; self.db_path = db_path
        self.title("Идентификация собаки"); self.resizable(True, True); self.transient(parent); self.grab_set(); self.protocol("WM_DELETE_WINDOW", self.save_unknown)
        main_frame = ttk.Frame(self); main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        dog_frame = ttk.Frame(main_frame); dog_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        x1, y1, x2, y2 = dog_bbox; dog_img = image[y1:y2, x1:x2]; dog_img = cv2.cvtColor(dog_img, cv2.COLOR_BGR2RGB); dog_img = Image.fromarray(dog_img)
        dog_img.thumbnail((200, 200), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(dog_img)
        dog_label = ttk.Label(dog_frame, image=photo); dog_label.image = photo; dog_label.pack()
        ttk.Label(dog_frame, text="Обнаружена собака", font=('Arial', 12, 'bold')).pack(pady=5)
        self.notebook = ttk.Notebook(main_frame); self.notebook.pack(fill=tk.BOTH, expand=True)
        # Вкладка "Новая собака"
        new_dog_frame = ttk.Frame(self.notebook); self.notebook.add(new_dog_frame, text="Новая собака")
        input_frame = ttk.Frame(new_dog_frame, padding="20"); input_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(input_frame, text="Кличка:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5); self.name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.name_var, width=40).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text="Порода:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5); self.breed_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.breed_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text="Владелец:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5); self.owner_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.owner_var, width=40).grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text="Примечание:").grid(row=3, column=0, sticky=tk.W+tk.N, padx=5, pady=5); text_frame = ttk.Frame(input_frame); text_frame.grid(row=3, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        self.notes_text = tk.Text(text_frame, width=40, height=3, wrap=tk.WORD); self.notes_text.pack(fill=tk.BOTH, expand=True); input_frame.columnconfigure(1, weight=1)
        # Вкладка "Выбрать из основной БД"
        if self.existing_dogs:
            existing_frame = ttk.Frame(self.notebook); self.notebook.add(existing_frame, text="Выбрать из БД")
            tree_frame = ttk.Frame(existing_frame, padding="10"); tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', 'Кличка', 'Порода', 'Владелец'); self.dog_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.dog_tree.heading(col, text=col); self.dog_tree.column(col, width=50 if col == 'ID' else 180)
            tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.dog_tree.yview); self.dog_tree.configure(yscrollcommand=tree_scroll.set)
            for dog in self.existing_dogs: self.dog_tree.insert('', tk.END, values=(dog['id'], dog['name'], dog['breed'] or 'Не указана', dog['owner'] or 'Не указан'))
            self.dog_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        # Вкладка "Выбрать из справочной БД"
        if self.ref_dogs:
            ref_frame = ttk.Frame(self.notebook); self.notebook.add(ref_frame, text="Выбрать из справочной БД")
            ref_tree_frame = ttk.Frame(ref_frame, padding="10"); ref_tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', 'Кличка', 'Порода', 'Владелец'); self.ref_dog_tree = ttk.Treeview(ref_tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.ref_dog_tree.heading(col, text=col); self.ref_dog_tree.column(col, width=50 if col == 'ID' else 180)
            ref_tree_scroll = ttk.Scrollbar(ref_tree_frame, orient="vertical", command=self.ref_dog_tree.yview); self.ref_dog_tree.configure(yscrollcommand=ref_tree_scroll.set)
            for dog in self.ref_dogs: self.ref_dog_tree.insert('', tk.END, values=(dog['id'], dog['name'], dog['breed'] or '', dog['owner'] or ''))
            self.ref_dog_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); ref_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        button_frame = ttk.Frame(self); button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10); left_button_frame = ttk.Frame(button_frame); left_button_frame.pack(side=tk.LEFT); right_button_frame = ttk.Frame(button_frame); right_button_frame.pack(side=tk.RIGHT)
        ttk.Button(left_button_frame, text="Сохранить как известную", command=self.save_known).pack(side=tk.LEFT, padx=5)
        ttk.Button(left_button_frame, text="Оставить неизвестной", command=self.save_unknown).pack(side=tk.LEFT, padx=5)
        ttk.Button(right_button_frame, text="Отмена", command=self.cancel).pack(side=tk.RIGHT, padx=5)
        self.center_window()
    def check_dog_exists(self, name, breed, owner):
        if not self.db_path: return False, []
        with sqlite3.connect(self.db_path) as conn:
            cursor=conn.cursor(); cursor.execute('SELECT id, name, breed, owner FROM dogs WHERE is_known=1 AND name=? AND(? = "" OR breed = ? ) AND (? = "" OR owner = ?)', (name, breed, breed, owner, owner)); return (dups := cursor.fetchall()), dups
    
    def save_known(self):
        try:
            active_tab_text = self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError:
            active_tab_text = "Новая собака"
            
        # --- Логика для вкладки "Новая собака" ---
        if active_tab_text == "Новая собака":
            name = self.name_var.get().strip(); breed = self.breed_var.get().strip(); owner = self.owner_var.get().strip()
            if not name: messagebox.showwarning("Предупреждение", "Введите кличку собаки", parent=self); return
            exists, duplicates = self.check_dog_exists(name, breed, owner)
            if exists: messagebox.showwarning("Собака уже существует", f"Собака с такими данными уже есть в БД:\nКличка: {duplicates[0][1]}\nПорода: {duplicates[0][2]}\nВладелец: {duplicates[0][3]}", parent=self); return
            self.result = {'action':'new_known', 'name':name, 'breed':breed, 'owner':owner, 'notes':self.notes_text.get('1.0', tk.END).strip()}; self.destroy()
        
        # --- Логика для вкладки "Выбрать из БД" ---
        elif active_tab_text == "Выбрать из БД":
            if not hasattr(self, 'dog_tree') or not (selection := self.dog_tree.selection()): messagebox.showwarning("Предупреждение", "Выберите собаку из списка", parent=self); return
            self.result = {'action':'existing', 'dog_id':self.dog_tree.item(selection[0])['values'][0]}; self.destroy()
            
        # --- Логика для вкладки "Выбрать из справочной БД" ---
        elif active_tab_text == "Выбрать из справочной БД":
            if not hasattr(self, 'ref_dog_tree') or not (selection := self.ref_dog_tree.selection()): messagebox.showwarning("Предупреждение", "Выберите собаку из списка", parent=self); return
            selected_id = self.ref_dog_tree.item(selection[0])['values'][0]
            dog_info = next((d for d in self.ref_dogs if d['id'] == selected_id), None)
            self.result = {'action': 'existing_ref', 'dog_info': dog_info}; self.destroy()

    def save_unknown(self): self.result = {'action':'unknown'}; self.destroy()
    def cancel(self): self.result = None; self.destroy()

class BodyWithoutFaceDialog(BaseDialog):
    def __init__(self, parent, image, body_bbox, existing_persons=None, db_path=None):
        super().__init__(parent); self.parent = parent; self.result = None; self.existing_persons = existing_persons or []; self.db_path = db_path
        self.title("Человек без распознанного лица"); self.resizable(True, True); self.transient(parent); self.grab_set()
        main_frame = ttk.Frame(self); main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        body_frame = ttk.Frame(main_frame); body_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        x1, y1, x2, y2 = body_bbox; body_img = image[y1:y2, x1:x2]; body_img = cv2.cvtColor(body_img, cv2.COLOR_BGR2RGB); body_img = Image.fromarray(body_img)
        body_img.thumbnail((200, 300), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(body_img)
        body_label = ttk.Label(body_frame, image=photo); body_label.image = photo; body_label.pack()
        ttk.Label(body_frame, text="Человек без распознанного лица", font=('Arial', 12, 'bold')).pack(pady=5)
        info_text = "Лицо этого человека не видно. Вы можете указать его данные, и они будут сохранены только для данного фото."; ttk.Label(main_frame, text=info_text, wraplength=650, justify=tk.CENTER).pack(pady=10)
        self.notebook = ttk.Notebook(main_frame); self.notebook.pack(fill=tk.BOTH, expand=True)
        input_tab = ttk.Frame(self.notebook); self.notebook.add(input_tab, text="Ввести данные")
        input_frame = ttk.Frame(input_tab, padding="20"); input_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(input_frame, text="Полное имя:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5); self.full_name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.full_name_var, width=40).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text="Короткое имя:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5); self.short_name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.short_name_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text="Примечание:").grid(row=2, column=0, sticky=tk.W+tk.N, padx=5, pady=5); text_frame = ttk.Frame(input_frame); text_frame.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        self.notes_text = tk.Text(text_frame, width=40, height=3, wrap=tk.WORD); self.notes_text.pack(fill=tk.BOTH, expand=True); input_frame.columnconfigure(1, weight=1)
        if self.existing_persons:
            existing_tab = ttk.Frame(self.notebook); self.notebook.add(existing_tab, text="Выбрать из БД")
            tree_frame = ttk.Frame(existing_tab, padding="10"); tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', 'Полное имя', 'Короткое имя'); self.person_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.person_tree.heading(col, text=col); self.person_tree.column(col, width=50 if col == 'ID' else 250)
            tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.person_tree.yview); self.person_tree.configure(yscrollcommand=tree_scroll.set)
            for person in self.existing_persons: self.person_tree.insert('', tk.END, values=(person['id'], person['full_name'], person['short_name']))
            self.person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            ttk.Button(existing_tab, text="Использовать выбранного", command=self.confirm_db_selection).pack(pady=10)
        button_frame = ttk.Frame(self); button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        ttk.Button(button_frame, text="Сохранить информацию", command=self.save_local_info).pack(side=tk.LEFT, padx=5)
        if self.existing_persons: ttk.Button(button_frame, text="Выбрать из БД", command=self.switch_to_db_tab).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Пропустить (неизвестный)", command=self.skip).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Отмена", command=self.cancel).pack(side=tk.RIGHT, padx=5)
        self.center_window()
    def save_local_info(self):
        full_name = self.full_name_var.get().strip()
        if not full_name: messagebox.showwarning("Предупреждение", "Введите полное имя или нажмите 'Пропустить'"); return
        self.result = {'action':'local_known', 'full_name':full_name, 'short_name':self.short_name_var.get().strip() or full_name.split()[0], 'notes':self.notes_text.get('1.0', tk.END).strip()}; self.destroy()
    def switch_to_db_tab(self): self.notebook.select(1)
    def confirm_db_selection(self):
        if not hasattr(self, 'person_tree') or not (selection := self.person_tree.selection()): messagebox.showwarning("Предупреждение", "Выберите человека из списка"); return
        self.result = {'action':'existing', 'person_id':self.person_tree.item(selection[0])['values'][0]}; self.destroy()
    def skip(self): self.result = {'action':'unknown'}; self.destroy()
    def cancel(self): self.result = None; self.destroy()

class ConfirmPersonDialog(BaseDialog):
    def __init__(self, parent, image, face_location, person_info):
        super().__init__(parent); self.result = None; self.person_info = person_info
        self.title("Найдено совпадение в справочной БД"); self.resizable(False, False); self.transient(parent); self.grab_set()
        main_frame = ttk.Frame(self, padding=20); main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text="Найдено возможное совпадение!", font=('Arial', 14, 'bold')).pack(pady=(0, 10))
        top, right, bottom, left = face_location; face_img = image[top:bottom, left:right]; face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB); face_img = Image.fromarray(face_img)
        face_img.thumbnail((150, 150), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(face_img)
        face_label = ttk.Label(main_frame, image=photo); face_label.image = photo; face_label.pack(pady=10)
        info_frame = ttk.LabelFrame(main_frame, text="Информация из справочной БД", padding=10); info_frame.pack(fill=tk.X, pady=10)
        ttk.Label(info_frame, text=f"Полное имя: {person_info['full_name']}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"Короткое имя: {person_info['short_name']}").pack(anchor=tk.W)
        if person_info.get('notes'): ttk.Label(info_frame, text=f"Примечание: {person_info['notes']}").pack(anchor=tk.W)
        ttk.Label(main_frame, text="Это тот же самый человек?", font=('Arial', 11, 'bold')).pack(pady=10)
        button_frame = ttk.Frame(main_frame); button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="Да, это он", command=self.confirm).pack(side=tk.LEFT, expand=True, padx=5)
        ttk.Button(button_frame, text="Нет, это другой человек", command=self.reject).pack(side=tk.RIGHT, expand=True, padx=5)
        self.center_window()
    def confirm(self): self.result = {'confirmed': True, 'person_info': self.person_info}; self.destroy()
    def reject(self): self.result = {'confirmed': False}; self.destroy()


class FaceDetectionV2:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Face Detection v{VERSION} - Распознавание и учет людей и собак")
        # ... остальной код __init__ без изменений ...
        self.root.geometry("1400x900")
        self.style = ttk.Style(self.root)
        try: self.style.theme_use('clam')
        except tk.TclError: print("Тема 'clam' не найдена.")
        self.style.configure('TNotebook.Tab', font=('Arial', 12, 'bold'), padding=[10, 5]); self.style.configure('Status.TLabel', font=('Arial', 11, 'bold'), padding=5)
        self.style.configure('Idle.Status.TLabel', background='lightblue', foreground='black'); self.style.configure('Processing.Status.TLabel', background='lightyellow', foreground='black')
        self.style.configure('Complete.Status.TLabel', background='lightgreen', foreground='black'); self.style.configure('Error.Status.TLabel', background='lightcoral', foreground='black')
        self.update_queue = queue.Queue()
        self.source_dir = tk.StringVar(value=""); self.db_path_var = tk.StringVar(value=""); self.ref_db_path_var = tk.StringVar(value="")
        self.include_subdirs = tk.BooleanVar(value=False); self.face_threshold = tk.DoubleVar(value=0.6); self.yolo_conf = tk.DoubleVar(value=0.5); self.yolo_model = tk.StringVar(value="yolov8n.pt")
        self.processing = False; self.processed_mode = tk.StringVar(value="skip"); self.processed_decision_for_all = None
        self.db_path = None; self.ref_db_path = None
        self.yolo = None 
        self.create_widgets()
        self.version_label = ttk.Label(self.root, text=f"v{VERSION}", font=('Arial', 10)); self.version_label.place(relx=0.99, y=5, anchor='ne')
        self.process_queue()
        self.update_status("Готов к работе. Выберите или создайте БД.", 'idle')

    # ... все методы до get_existing_dogs без изменений ...
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.update_queue.put(('log', f"[{timestamp}] {message}\n"))

    def process_queue(self):
        try:
            while True:
                action, data = self.update_queue.get_nowait()
                if action == 'log': self.log_text.insert(tk.END, data); self.log_text.see(tk.END)
                elif action == 'image': self.display_image(data[0], data[1])
                elif action == 'status':
                    message, status_type = data
                    self.status_label.config(text=message)
                    self.status_label.config(style=f"{status_type.title()}.Status.TLabel")
                elif action == 'enable_buttons': self.start_btn.config(state=tk.NORMAL if self.db_path else tk.DISABLED); self.stop_btn.config(state=tk.DISABLED)
                elif action == 'show_person_dialog': self.show_person_dialog_main(data)
                elif action == 'show_confirm_person_dialog': self.show_confirm_person_dialog_main(data)
                elif action == 'show_body_dialog': self.show_body_dialog_main(data)
                elif action == 'show_dog_dialog': self.show_dog_dialog_main(data)
                elif action == 'show_processed_dialog': self.show_processed_dialog_main(data)
                elif action == 'refresh_people': self.refresh_people_list()
                elif action == 'refresh_dogs': self.refresh_dogs_list()
        except queue.Empty: pass
        finally: self.root.after(100, self.process_queue)

    def create_widgets(self):
        main_notebook = ttk.Notebook(self.root); main_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        scan_frame = ttk.Frame(main_notebook); main_notebook.add(scan_frame, text="Сканирование")
        self.create_scan_tab(scan_frame)
        people_frame = ttk.Frame(main_notebook); main_notebook.add(people_frame, text="База людей")
        self.create_people_tab(people_frame)
        dogs_frame = ttk.Frame(main_notebook); main_notebook.add(dogs_frame, text="База собак")
        self.create_dogs_tab(dogs_frame)

    def create_scan_tab(self, parent):
        dir_frame = ttk.LabelFrame(parent, text="Настройки сканирования", padding="10"); dir_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=5); dir_frame.columnconfigure(1, weight=1)
        ttk.Label(dir_frame, text="Директория с фото:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(dir_frame, textvariable=self.source_dir, width=60).grid(row=0, column=1, padx=5, sticky=tk.EW)
        ttk.Button(dir_frame, text="Обзор...", command=self.browse_source).grid(row=0, column=2)
        ttk.Checkbutton(dir_frame, text="Включая поддиректории", variable=self.include_subdirs).grid(row=0, column=3, padx=20)
        ttk.Label(dir_frame, text="Актуальная БД:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(dir_frame, textvariable=self.db_path_var, width=60, state='readonly').grid(row=1, column=1, padx=5, sticky=tk.EW)
        db_button_frame = ttk.Frame(dir_frame); db_button_frame.grid(row=1, column=2, columnspan=2, sticky=tk.W)
        ttk.Button(db_button_frame, text="Обзор...", command=self.select_database_file).pack(side=tk.LEFT)
        ttk.Button(db_button_frame, text="Создать новую...", command=self.create_new_database).pack(side=tk.LEFT, padx=5)
        ttk.Label(dir_frame, text="Справочная БД (векторы):").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(dir_frame, textvariable=self.ref_db_path_var, width=60, state='readonly').grid(row=2, column=1, padx=5, sticky=tk.EW)
        ref_db_button_frame = ttk.Frame(dir_frame); ref_db_button_frame.grid(row=2, column=2, columnspan=2, sticky=tk.W)
        ttk.Button(ref_db_button_frame, text="Обзор...", command=self.select_reference_database).pack(side=tk.LEFT)
        ttk.Button(ref_db_button_frame, text="Очистить", command=self.clear_reference_database).pack(side=tk.LEFT, padx=5)
        control_frame = ttk.Frame(parent, padding="10"); control_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5)
        self.start_btn = ttk.Button(control_frame, text="🚀 Начать сканирование", command=self.start_processing, state=tk.DISABLED); self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(control_frame, text="🛑 Остановить", command=self.stop_processing, state=tk.DISABLED); self.stop_btn.pack(side=tk.LEFT, padx=5)
        self.exit_btn = ttk.Button(control_frame, text="Выход", command=self.root.destroy); self.exit_btn.pack(side=tk.RIGHT, padx=5)
        self.status_label = ttk.Label(control_frame, text="Готов к работе. Выберите или создайте БД.", style="Idle.Status.TLabel"); self.status_label.pack(side=tk.LEFT, padx=20, fill=tk.X, expand=True)
        image_frame = ttk.LabelFrame(parent, text="Текущее изображение", padding="10"); image_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        self.image_label = ttk.Label(image_frame); self.image_label.pack(expand=True, fill=tk.BOTH)
        log_frame = ttk.LabelFrame(parent, text="Лог обработки", padding="10"); log_frame.grid(row=2, column=1, sticky="nsew", padx=10, pady=10)
        self.log_text = scrolledtext.ScrolledText(log_frame, width=50, height=30, wrap=tk.WORD); self.log_text.pack(fill=tk.BOTH, expand=True)
        parent.grid_rowconfigure(2, weight=1); parent.grid_columnconfigure(0, weight=2); parent.grid_columnconfigure(1, weight=1)

    def create_people_tab(self, parent):
        toolbar = ttk.Frame(parent); toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        self.btn_refresh_people = ttk.Button(toolbar, text="Обновить", command=self.refresh_people_list, state=tk.DISABLED); self.btn_refresh_people.pack(side=tk.LEFT, padx=5)
        self.btn_edit_person = ttk.Button(toolbar, text="Редактировать", command=self.edit_person, state=tk.DISABLED); self.btn_edit_person.pack(side=tk.LEFT, padx=5)
        self.btn_delete_person = ttk.Button(toolbar, text="Удалить", command=self.delete_person, state=tk.DISABLED); self.btn_delete_person.pack(side=tk.LEFT, padx=5)
        columns = ('ID', 'Статус', 'Полное имя', 'Короткое имя', 'Кол-во фото', 'Примечание'); self.people_tree = ttk.Treeview(parent, columns=columns, show='headings')
        self.people_tree.heading('ID', text='ID'); self.people_tree.column('ID', width=50, anchor='center'); self.people_tree.heading('Статус', text='Статус'); self.people_tree.column('Статус', width=100); self.people_tree.heading('Полное имя', text='Полное имя'); self.people_tree.column('Полное имя', width=200); self.people_tree.heading('Короткое имя', text='Короткое имя'); self.people_tree.column('Короткое имя', width=150); self.people_tree.heading('Кол-во фото', text='Фото'); self.people_tree.column('Кол-во фото', width=80, anchor='center'); self.people_tree.heading('Примечание', text='Примечание'); self.people_tree.column('Примечание', width=300)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.people_tree.yview); self.people_tree.configure(yscrollcommand=scrollbar.set)
        self.people_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5); scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def create_dogs_tab(self, parent):
        toolbar = ttk.Frame(parent); toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        self.btn_refresh_dogs = ttk.Button(toolbar, text="Обновить", command=self.refresh_dogs_list, state=tk.DISABLED); self.btn_refresh_dogs.pack(side=tk.LEFT, padx=5)
        self.btn_edit_dog = ttk.Button(toolbar, text="Редактировать", command=self.edit_dog, state=tk.DISABLED); self.btn_edit_dog.pack(side=tk.LEFT, padx=5)
        self.btn_delete_dog = ttk.Button(toolbar, text="Удалить", command=self.delete_dog, state=tk.DISABLED); self.btn_delete_dog.pack(side=tk.LEFT, padx=5)
        columns = ('ID', 'Статус', 'Кличка', 'Порода', 'Владелец', 'Кол-во фото', 'Примечание'); self.dogs_tree = ttk.Treeview(parent, columns=columns, show='headings')
        for col, w in [('ID',50), ('Статус',100), ('Кличка',150), ('Порода',150), ('Владелец',150), ('Кол-во фото',80), ('Примечание',200)]: self.dogs_tree.heading(col, text=col); self.dogs_tree.column(col, width=w)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.dogs_tree.yview); self.dogs_tree.configure(yscrollcommand=scrollbar.set)
        self.dogs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5); scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def set_db_dependent_widgets_state(self, state):
        self.start_btn.config(state=state); self.btn_refresh_people.config(state=state); self.btn_edit_person.config(state=state); self.btn_delete_person.config(state=state); self.btn_refresh_dogs.config(state=state); self.btn_edit_dog.config(state=state); self.btn_delete_dog.config(state=state)

    def init_database(self, db_path):
        try:
            if db_dir := os.path.dirname(db_path): os.makedirs(db_dir, exist_ok=True)
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                base_tables_sql = """
                CREATE TABLE IF NOT EXISTS persons (id INTEGER PRIMARY KEY, is_known BOOLEAN, full_name TEXT, short_name TEXT, notes TEXT, created_date TEXT, updated_date TEXT);
                CREATE TABLE IF NOT EXISTS dogs (id INTEGER PRIMARY KEY, is_known BOOLEAN, name TEXT, breed TEXT, owner TEXT, notes TEXT, created_date TEXT, updated_date TEXT);
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY, filename TEXT, filepath TEXT, created_date TEXT, file_size INTEGER,
                    num_bodies INTEGER, num_faces INTEGER, num_dogs INTEGER, processed_date TEXT,
                    ai_short_description TEXT, ai_long_description TEXT, ai_processed_date TEXT, ai_llm_used TEXT, ai_language TEXT
                );
                CREATE TABLE IF NOT EXISTS face_encodings (id INTEGER PRIMARY KEY, person_id INTEGER, image_id INTEGER, face_encoding TEXT, face_location TEXT, FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE CASCADE, FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS person_detections (id INTEGER PRIMARY KEY, image_id INTEGER, person_id INTEGER, person_index INTEGER, bbox TEXT, confidence REAL, has_face BOOLEAN, face_encoding_id INTEGER, is_locally_identified BOOLEAN, local_full_name TEXT, local_short_name TEXT, local_notes TEXT, FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE, FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE CASCADE, FOREIGN KEY(face_encoding_id) REFERENCES face_encodings(id) ON DELETE SET NULL);
                CREATE TABLE IF NOT EXISTS dog_detections (id INTEGER PRIMARY KEY, image_id INTEGER, dog_id INTEGER, dog_index INTEGER, bbox TEXT, confidence REAL, FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE, FOREIGN KEY(dog_id) REFERENCES dogs(id) ON DELETE CASCADE);
                """
                for statement in base_tables_sql.strip().split(';'):
                    if statement.strip(): cursor.execute(statement)
                cursor.execute('PRAGMA foreign_keys = ON;')
            return True
        except Exception as e: messagebox.showerror("Ошибка", f"Не удалось создать БД: {e}"); return False

    def validate_database_structure(self, db_path):
        REQUIRED_TABLES = {'persons':['id','full_name'], 'dogs':['id','name'], 'images':['id','filepath'], 'face_encodings':['id','person_id'], 'person_detections':['id','image_id'], 'dog_detections':['id','image_id']}
        try:
            with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'"); tables = {row[0] for row in cursor.fetchall()}
                if not set(REQUIRED_TABLES.keys()).issubset(tables): messagebox.showerror("Ошибка", "Неверная структура БД. Отсутствуют таблицы."); return False
            return True
        except Exception as e: messagebox.showerror("Ошибка", f"Ошибка чтения БД: {e}"); return False

    def select_database_file(self):
        if filepath := filedialog.askopenfilename(title="Выберите актуальную базу данных", filetypes=[("SQLite DB", "*.db")]):
            if self.validate_database_structure(filepath):
                self.db_path = filepath; self.db_path_var.set(filepath); self.log(f"Актуальная БД загружена: {filepath}"); self.set_db_dependent_widgets_state(tk.NORMAL); self.refresh_people_list(); self.refresh_dogs_list(); self.update_status("БД загружена. Готов к сканированию.", 'complete')
            else: self.log("Файл БД имеет неверную структуру."); self.db_path = None; self.db_path_var.set(""); self.set_db_dependent_widgets_state(tk.DISABLED)

    def create_new_database(self):
        if filepath := filedialog.asksaveasfilename(title="Создать новую базу данных", defaultextension=".db", filetypes=[("SQLite DB", "*.db")]):
            if self.init_database(filepath):
                self.db_path = filepath; self.db_path_var.set(filepath); self.set_db_dependent_widgets_state(tk.NORMAL); self.refresh_people_list(); self.refresh_dogs_list(); self.update_status("Новая БД создана. Готов к сканированию.", 'complete')
            else: self.db_path = None; self.db_path_var.set(""); self.set_db_dependent_widgets_state(tk.DISABLED)

    def select_reference_database(self):
        if filepath := filedialog.askopenfilename(title="Выберите справочную базу данных", filetypes=[("SQLite DB", "*.db")]):
            if self.validate_database_structure(filepath): self.ref_db_path = filepath; self.ref_db_path_var.set(filepath); self.log(f"Справочная БД загружена: {filepath}")
            else: self.log("Файл справочной БД имеет неверную структуру.")

    def clear_reference_database(self): self.ref_db_path = None; self.ref_db_path_var.set(""); self.log("Справочная БД очищена.")

    def browse_source(self):
        if directory := filedialog.askdirectory(title="Выберите директорию с фото"): self.source_dir.set(directory)

    def update_image(self, image_path, annotated_image=None): self.update_queue.put(('image', (image_path, annotated_image)))

    def update_status(self, message, status_type): self.update_queue.put(('status', (message, status_type)))

    def is_image_processed(self, image_path):
        if not self.db_path: return False
        with sqlite3.connect(self.db_path) as conn:
            cursor=conn.cursor(); cursor.execute('SELECT id FROM images WHERE filepath = ? AND num_bodies IS NOT NULL', (image_path,)); return cursor.fetchone() is not None

    def clear_image_data(self, image_path):
        if not self.db_path: return
        with sqlite3.connect(self.db_path) as conn:
            cursor=conn.cursor(); cursor.execute('PRAGMA foreign_keys=ON;')
            if result := cursor.execute('SELECT id FROM images WHERE filepath = ?', (image_path,)).fetchone():
                cursor.execute('DELETE FROM images WHERE id = ?', (result[0],)); self.log(f"Старые данные для {os.path.basename(image_path)} удалены.")

    def display_image(self, image_path, annotated_image=None):
        """
        Отображает изображение, используя надежный метод для предотвращения утечек памяти.
        """
        try:
            if annotated_image is not None:
                image = Image.fromarray(cv2.cvtColor(annotated_image, cv2.COLOR_BGR2RGB))
            else:
                image = orient_image(Image.open(image_path))

            self.image_label.update_idletasks()
            w, h = self.image_label.winfo_width(), self.image_label.winfo_height()
            max_w, max_h = (w - 20) if w > 20 else 700, (h - 20) if h > 20 else 700
            
            image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            
            # Создаем новый объект PhotoImage и сохраняем его в наш атрибут
            self.displayed_photo = ImageTk.PhotoImage(image)
            
            # Конфигурируем Label, чтобы он использовал новый объект
            self.image_label.config(image=self.displayed_photo)

        except Exception as e:
            self.log(f"Ошибка отображения: {e}")
            # Очищаем изображение в случае ошибки
            self.image_label.config(image=None)
            self.image_label.config(text=f"Не удалось показать\n{os.path.basename(image_path)}")
            
    def start_processing(self):
        if not self.db_path: messagebox.showerror("Ошибка", "Выберите или создайте файл БД."); return
        if not self.source_dir.get() or not os.path.exists(self.source_dir.get()): messagebox.showerror("Ошибка", "Укажите директорию с фото."); return
        if not self.processing:
            self.processing = True; self.start_btn.config(state=tk.DISABLED); self.stop_btn.config(state=tk.NORMAL); self.update_status("Инициализация...", 'processing')
            try:
                if self.yolo is None: self.yolo = YOLO(self.yolo_model.get()); self.log(f"Модель YOLO {self.yolo_model.get()} загружена.")
            except Exception as e: self.log(f"Ошибка загрузки YOLO: {e}"); self.stop_processing(); return
            threading.Thread(target=self.process_images, daemon=True).start()

    def stop_processing(self): self.processing = False; self.log("Остановка обработки..."); self.update_status("Остановка...", 'idle'); self.start_btn.config(state=tk.NORMAL); self.stop_btn.config(state=tk.DISABLED)

    def refresh_people_list(self):
        if not self.db_path: return
        for item in self.people_tree.get_children(): self.people_tree.delete(item)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor(); cursor.execute("SELECT p.id, CASE WHEN p.is_known THEN 'Известный' ELSE 'Неизвестный' END, p.full_name, p.short_name, COUNT(DISTINCT pd.image_id), p.notes FROM persons p LEFT JOIN person_detections pd ON p.id = pd.person_id GROUP BY p.id ORDER BY p.is_known DESC, p.full_name")
                for row in cursor.fetchall(): self.people_tree.insert('', tk.END, values=row)
        except Exception as e: self.log(f"Ошибка обновления списка людей: {e}")

    def refresh_dogs_list(self):
        if not self.db_path: return
        for item in self.dogs_tree.get_children(): self.dogs_tree.delete(item)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor(); cursor.execute("SELECT d.id, CASE WHEN d.is_known THEN 'Известная' ELSE 'Неизвестная' END, d.name, d.breed, d.owner, COUNT(DISTINCT dd.image_id), d.notes FROM dogs d LEFT JOIN dog_detections dd ON d.id = dd.dog_id GROUP BY d.id ORDER BY d.is_known DESC, d.name")
                for row in cursor.fetchall(): self.dogs_tree.insert('', tk.END, values=row)
        except Exception as e: self.log(f"Ошибка обновления списка собак: {e}")

    def edit_person(self): messagebox.showinfo("В разработке", "Функция редактирования в разработке.")

    def delete_person(self):
        if not (sel := self.people_tree.selection()): messagebox.showwarning("Предупреждение", "Выберите человека для удаления"); return
        if messagebox.askyesno("Подтверждение", "Удалить этого человека и все связанные данные? Действие необратимо."):
            person_id = self.people_tree.item(sel[0])['values'][0]
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor(); cursor.execute('PRAGMA foreign_keys = ON;'); cursor.execute('DELETE FROM persons WHERE id = ?', (person_id,));
                self.refresh_people_list(); messagebox.showinfo("Успех", "Человек удален")
            except Exception as e: messagebox.showerror("Ошибка", f"Ошибка удаления: {e}")

    def edit_dog(self): messagebox.showinfo("В разработке", "Функция редактирования в разработке.")

    def delete_dog(self):
        if not (sel := self.dogs_tree.selection()): messagebox.showwarning("Предупреждение", "Выберите собаку для удаления"); return
        if messagebox.askyesno("Подтверждение", "Удалить эту собаку и все связанные данные? Действие необратимо."):
            dog_id = self.dogs_tree.item(sel[0])['values'][0]
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor(); cursor.execute('PRAGMA foreign_keys = ON;'); cursor.execute('DELETE FROM dogs WHERE id = ?', (dog_id,));
                self.refresh_dogs_list(); messagebox.showinfo("Успех", "Собака удалена")
            except Exception as e: messagebox.showerror("Ошибка", f"Ошибка удаления: {e}")

    def get_existing_persons(self, db_path=None):
        target_db = db_path or self.db_path
        if not target_db: return []
        try:
            with sqlite3.connect(target_db) as conn:
                conn.row_factory = sqlite3.Row; cursor = conn.cursor()
                cursor.execute('SELECT id, full_name, short_name, notes FROM persons WHERE is_known = 1 ORDER BY full_name')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e: self.log(f"Ошибка чтения списка людей из {os.path.basename(target_db)}: {e}"); return []

    def get_existing_dogs(self, db_path=None):
        target_db = db_path or self.db_path
        if not target_db: return []
        try:
            with sqlite3.connect(target_db) as conn:
                conn.row_factory = sqlite3.Row; cursor = conn.cursor()
                cursor.execute('SELECT id, name, breed, owner, notes FROM dogs WHERE is_known = 1 ORDER BY name')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e: self.log(f"Ошибка чтения списка собак из {os.path.basename(target_db)}: {e}"); return []

    def show_person_dialog_main(self, data):
        image, face_location, face_encoding, callback = data
        ref_persons = self.get_existing_persons(self.ref_db_path) if self.ref_db_path else []
        dialog = PersonDialog(self.root, image, face_location, self.get_existing_persons(), ref_persons, self.db_path)
        self.root.wait_window(dialog); callback(dialog.result)

    def show_dog_dialog_main(self, data):
        image, dog_bbox, callback = data
        ref_dogs = self.get_existing_dogs(self.ref_db_path) if self.ref_db_path else []
        dialog = DogDialog(self.root, image, dog_bbox, self.get_existing_dogs(), ref_dogs, self.db_path)
        self.root.wait_window(dialog); callback(dialog.result)
    
    # ... Остальные show_..._dialog_main методы без изменений ...
    def show_confirm_person_dialog_main(self, data): image, face_location, person_info, callback = data; dialog = ConfirmPersonDialog(self.root, image, face_location, person_info); self.root.wait_window(dialog); callback(dialog.result)
    def show_body_dialog_main(self, data): image, body_bbox, callback = data; dialog = BodyWithoutFaceDialog(self.root, image, body_bbox, self.get_existing_persons(), self.db_path); self.root.wait_window(dialog); callback(dialog.result)
    def show_processed_dialog_main(self, data): image_path, callback = data; dialog = ProcessedImageDialog(self.root, image_path); self.root.wait_window(dialog); callback(dialog.result, dialog.apply_to_all)


    def create_or_update_person(self, result, conn):
        cursor = conn.cursor(); now = datetime.now().isoformat(); person_id = None
        if result['action'] == 'new_known':
            cursor.execute('INSERT INTO persons (is_known, full_name, short_name, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?)', (result['full_name'], result['short_name'], result['notes'], now, now)); person_id = cursor.lastrowid; self.log(f"  Создан новый человек: {result['full_name']}")
        elif result['action'] == 'unknown':
            cursor.execute('INSERT INTO persons (is_known, created_date, updated_date) VALUES (0, ?, ?)', (now, now)); person_id = cursor.lastrowid; self.log(f"  Добавлен неизвестный (ID: {person_id})")
        elif result['action'] == 'existing': person_id = result['person_id']
        return person_id

    def create_or_update_dog(self, result, conn):
        cursor = conn.cursor(); now = datetime.now().isoformat(); dog_id = None
        if result['action'] == 'new_known': cursor.execute('INSERT INTO dogs (is_known, name, breed, owner, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?, ?)', (result['name'], result.get('breed',''), result.get('owner',''), result.get('notes',''), now, now)); dog_id = cursor.lastrowid
        elif result['action'] == 'unknown': cursor.execute('INSERT INTO dogs (is_known, created_date, updated_date) VALUES (0, ?, ?)', (now, now)); dog_id = cursor.lastrowid
        elif result['action'] == 'existing': dog_id = result['dog_id']
        return dog_id

    def get_or_create_person_by_name(self, person_info, conn):
        cursor = conn.cursor(); cursor.execute("SELECT id FROM persons WHERE full_name = ?", (person_info['full_name'],))
        if result := cursor.fetchone():
            self.log(f"  Человек '{person_info['full_name']}' уже существует в актуальной БД. ID: {result[0]}"); return result[0]
        else:
            now = datetime.now().isoformat()
            cursor.execute('INSERT INTO persons (is_known, full_name, short_name, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?)',
                           (person_info['full_name'], person_info['short_name'], person_info.get('notes', ''), now, now))
            new_id = cursor.lastrowid; self.log(f"  Человек '{person_info['full_name']}' импортирован в актуальную БД. Новый ID: {new_id}"); self.update_queue.put(('refresh_people', None)); return new_id
    
    def get_or_create_dog_by_name(self, dog_info, conn):
        cursor = conn.cursor(); cursor.execute("SELECT id FROM dogs WHERE name = ?", (dog_info['name'],))
        if result := cursor.fetchone():
            self.log(f"  Собака '{dog_info['name']}' уже существует в актуальной БД. ID: {result[0]}"); return result[0]
        else:
            now = datetime.now().isoformat()
            cursor.execute('INSERT INTO dogs (is_known, name, breed, owner, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?, ?)',
                           (dog_info['name'], dog_info.get('breed', ''), dog_info.get('owner', ''), dog_info.get('notes', ''), now, now))
            new_id = cursor.lastrowid; self.log(f"  Собака '{dog_info['name']}' импортирована в актуальную БД. Новый ID: {new_id}"); self.update_queue.put(('refresh_dogs', None)); return new_id

    def get_name_from_db(self, entity_id, conn, entity_type='person'):
        if not entity_id: return "Неизвестный"
        table, column = ('persons', 'short_name') if entity_type == 'person' else ('dogs', 'name')
        try: cursor = conn.cursor(); cursor.execute(f'SELECT {column} FROM {table} WHERE id = ?', (entity_id,)); return (result[0] if (result := cursor.fetchone()) else None) or "Неизвестный"
        except Exception: return "Неизвестный"

    def identify_person(self, face_encoding_to_check, db_path, main_conn=None):
        if not db_path: return None
        conn = main_conn if main_conn and db_path == self.db_path else sqlite3.connect(db_path)
        try:
            conn.row_factory = sqlite3.Row; cursor = conn.cursor()
            cursor.execute("SELECT p.id, p.full_name, p.short_name, p.notes, fe.face_encoding FROM face_encodings fe JOIN persons p ON fe.person_id = p.id WHERE p.is_known = 1")
            rows = cursor.fetchall(); known_face_encodings, known_face_metadata = [], []
            for row in rows:
                try: known_face_encodings.append(np.array(json.loads(row['face_encoding']))); known_face_metadata.append(dict(row))
                except (json.JSONDecodeError, TypeError): continue
            if not known_face_encodings: return None
            matches = face_recognition.compare_faces(known_face_encodings, face_encoding_to_check, tolerance=self.face_threshold.get())
            if True in matches: return known_face_metadata[matches.index(True)]
        except Exception as e: self.log(f"Ошибка идентификации в {os.path.basename(db_path)}: {e}")
        finally:
            if not main_conn: conn.close()
        return None

    def detect_faces_and_bodies(self, image_path, image_id, conn):
        try:
            pil_image = Image.open(image_path); oriented_pil_image = orient_image(pil_image)
            image = cv2.cvtColor(np.array(oriented_pil_image), cv2.COLOR_RGB2BGR); rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = self.yolo(image, conf=self.yolo_conf.get())
            person_detections, dog_detections = [], []; person_idx_counter, dog_idx_counter = 0, 0
            if results and results[0].boxes:
                for box in results[0].boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy()); confidence, class_id = float(box.conf[0]), int(box.cls[0])
                    if class_id == 0: person_detections.append({'person_index': person_idx_counter, 'bbox': [x1, y1, x2, y2], 'confidence': confidence, 'has_face': False}); person_idx_counter += 1
                    elif class_id == 16: dog_detections.append({'dog_index': dog_idx_counter, 'bbox': [x1, y1, x2, y2], 'confidence': confidence}); dog_idx_counter += 1
            self.log(f"  YOLO обнаружил: {len(person_detections)} людей, {len(dog_detections)} собак.")
            face_locations = face_recognition.face_locations(rgb_image, model='hog'); face_encodings = face_recognition.face_encodings(rgb_image, face_locations)
            self.log(f"  Найдено лиц: {len(face_locations)}"); unmatched_face_data = list(zip(face_locations, face_encodings))
            for person in person_detections:
                px1, py1, px2, py2 = person['bbox']; best_face_idx, max_overlap = -1, 0.1
                for i, (face_loc, _) in enumerate(unmatched_face_data):
                    top, right, bottom, left = face_loc
                    if not (px1 < right and px2 > left and py1 < bottom and py2 > top): continue
                    inter_x1, inter_y1, inter_x2, inter_y2 = max(px1, left), max(py1, top), min(px2, right), min(py2, bottom)
                    intersection_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1); face_area = (right - left) * (bottom - top)
                    if face_area > 0 and (overlap := intersection_area / face_area) > max_overlap: max_overlap, best_face_idx = overlap, i
                if best_face_idx != -1: face_loc, face_enc = unmatched_face_data.pop(best_face_idx); person.update({'has_face': True, 'face_location': face_loc, 'face_encoding': face_enc})
            
            for person in person_detections:
                if not self.processing: break
                person_result = None
                if person.get('has_face'):
                    match = self.identify_person(person['face_encoding'], self.db_path, main_conn=conn)
                    if not match and self.ref_db_path:
                        ref_match = self.identify_person(person['face_encoding'], self.ref_db_path)
                        if ref_match:
                            dialog_event = threading.Event(); dialog_result = {}; cb = lambda r: (dialog_result.update({'result': r}), dialog_event.set())
                            self.update_queue.put(('show_confirm_person_dialog', (image, person['face_location'], ref_match, cb))); dialog_event.wait()
                            if dialog_result.get('result', {}).get('confirmed'): person['person_id'] = self.get_or_create_person_by_name(dialog_result['result']['person_info'], conn); continue
                    if match: person['person_id'] = match['person_id']; self.log(f"  Распознан (основная БД): {match['short_name']}"); continue
                    dialog_event = threading.Event(); dialog_result = {}; cb = lambda r: (dialog_result.update({'result': r}), dialog_event.set())
                    self.update_queue.put(('show_person_dialog', (image, person['face_location'], person['face_encoding'], cb))); dialog_event.wait()
                    person_result = dialog_result.get('result')
                else:
                    dialog_event = threading.Event(); dialog_result = {}; cb = lambda r: (dialog_result.update({'result': r}), dialog_event.set())
                    self.update_queue.put(('show_body_dialog', (image, person['bbox'], cb))); dialog_event.wait()
                    person_result = dialog_result.get('result')
                if person_result:
                    if person_result['action'] == 'existing': person['person_id'] = person_result['person_id']
                    elif person_result['action'] == 'existing_ref': person['person_id'] = self.get_or_create_person_by_name(person_result['person_info'], conn); person['dialog_result'] = {'action': 'new_known'}
                    elif person_result['action'] == 'local_known': person.update({'is_locally_identified': True, 'local_full_name': person_result['full_name'], 'local_short_name': person_result['short_name'], 'local_notes': person_result['notes']})
                    else: person['person_id'] = self.create_or_update_person(person_result, conn); person['dialog_result'] = person_result
            
            for dog in dog_detections:
                if not self.processing: break
                dialog_event = threading.Event(); dialog_result = {}; cb = lambda r: (dialog_result.update({'result': r}), dialog_event.set())
                self.update_queue.put(('show_dog_dialog', (image, dog['bbox'], cb))); dialog_event.wait()
                if res := dialog_result.get('result'):
                    if res['action'] == 'existing_ref': dog['dog_id'] = self.get_or_create_dog_by_name(res['dog_info'], conn)
                    else: dog['dog_id'] = self.create_or_update_dog(res, conn)

            annotated_image = image.copy()
            for person in person_detections:
                p_id = person.get('person_id'); name = person.get('local_short_name') or self.get_name_from_db(p_id, conn, 'person')
                x1, y1, x2, y2 = person['bbox']; cv2.rectangle(annotated_image, (x1, y1), (x2, y2), (255, 0, 0), 2); cv2.putText(annotated_image, name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)
                if person.get('has_face'): top, right, bottom, left = person['face_location']; cv2.rectangle(annotated_image, (left, top), (right, bottom), (0, 255, 0), 2)
            for dog in dog_detections:
                d_id = dog.get('dog_id'); name = self.get_name_from_db(d_id, conn, 'dog'); x1, y1, x2, y2 = dog['bbox']
                cv2.rectangle(annotated_image, (x1, y1), (x2, y2), (0, 0, 255), 2); cv2.putText(annotated_image, name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
            
            return len(person_detections), len(face_locations), len(dog_detections), person_detections, annotated_image, unmatched_face_data, dog_detections
        except Exception as e: self.log(f"Критическая ошибка при детекции: {e}\n{traceback.format_exc()}"); return 0, 0, 0, [], None, [], []

    def save_to_database(self, image_id, person_detections, unmatched_faces, dog_detections, conn):
        try:
            cursor = conn.cursor()
            for person in person_detections:
                person_id = person.get('person_id'); face_encoding_id = None
                if person.get('has_face') and person.get('dialog_result', {}).get('action') == 'new_known':
                    enc_str = json.dumps(person['face_encoding'].tolist()); loc_str = json.dumps(person['face_location'])
                    cursor.execute('INSERT INTO face_encodings (person_id, image_id, face_encoding, face_location) VALUES (?, ?, ?, ?)', (person_id, image_id, enc_str, loc_str)); face_encoding_id = cursor.lastrowid
                cursor.execute("INSERT INTO person_detections (image_id, person_id, person_index, bbox, confidence, has_face, face_encoding_id, is_locally_identified, local_full_name, local_short_name, local_notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (image_id, person_id, person['person_index'], json.dumps(person['bbox']), person['confidence'], person.get('has_face', False), face_encoding_id, person.get('is_locally_identified', False), person.get('local_full_name'), person.get('local_short_name'), person.get('local_notes')))
            for face_loc, face_enc in unmatched_faces:
                now = datetime.now().isoformat()
                cursor.execute('INSERT INTO persons (is_known, created_date, updated_date) VALUES (0, ?, ?)', (now, now)); person_id = cursor.lastrowid
                enc_str = json.dumps(face_enc.tolist()); loc_str = json.dumps(face_loc)
                cursor.execute('INSERT INTO face_encodings (person_id, image_id, face_encoding, face_location) VALUES (?, ?, ?, ?)', (person_id, image_id, enc_str, loc_str)); face_encoding_id = cursor.lastrowid
                cursor.execute('INSERT INTO person_detections (image_id, person_id, has_face, face_encoding_id) VALUES (?, ?, 1, ?)', (image_id, person_id, face_encoding_id))
                self.log(f"  Сохранено лицо без фигуры как 'Неизвестный' (ID: {person_id})")
            for dog in dog_detections:
                cursor.execute('INSERT INTO dog_detections (image_id, dog_id, dog_index, bbox, confidence) VALUES (?, ?, ?, ?, ?)', (image_id, dog.get('dog_id'), dog['dog_index'], json.dumps(dog['bbox']), dog['confidence']))
        except Exception as e: self.log(f"Ошибка сохранения в БД: {e}\n{traceback.format_exc()}")

    def process_images(self):
        try:
            source = self.source_dir.get(); image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}; image_files = []
            if self.include_subdirs.get():
                for root, _, files in os.walk(source):
                    for file in files:
                        if Path(file).suffix.lower() in image_extensions: image_files.append(os.path.join(root, file))
            else:
                for file in os.listdir(source):
                    if os.path.isfile(path := os.path.join(source, file)) and Path(file).suffix.lower() in image_extensions: image_files.append(path)
            self.log(f"Найдено изображений: {len(image_files)}"); self.processed_decision_for_all = None
            for i, image_path in enumerate(image_files):
                if not self.processing: self.log("Обработка прервана."); break
                self.update_status(f"Обработка {i+1}/{len(image_files)}: {os.path.basename(image_path)}", 'processing'); self.log(f"\nОбработка: {os.path.basename(image_path)}"); self.update_image(image_path)
                if self.is_image_processed(image_path):
                    decision = self.processed_decision_for_all or self.processed_mode.get()
                    if decision == 'skip': self.log("  Пропущено (уже обработано)."); continue
                    if decision == 'ask':
                        dialog_event = threading.Event(); dialog_res = {}; cb = lambda res, apply_all: (dialog_res.update({'res':res, 'apply_all':apply_all}), dialog_event.set())
                        self.update_queue.put(('show_processed_dialog', (image_path, cb))); dialog_event.wait()
                        decision = dialog_res.get('res')
                        if dialog_res.get('apply_all'): self.processed_decision_for_all = decision
                    if decision == 'cancel': self.log("Обработка отменена."); break
                    if decision == 'skip': self.log("  Пропущено (уже обработано)."); continue
                    self.clear_image_data(image_path)
                with sqlite3.connect(self.db_path, timeout=10) as conn:
                    cursor = conn.cursor(); cursor.execute('PRAGMA foreign_keys = ON;')
                    file_stat = os.stat(image_path); created_date, now = datetime.fromtimestamp(file_stat.st_ctime).isoformat(), datetime.now().isoformat()
                    cursor.execute('INSERT INTO images (filename, filepath, created_date, file_size, processed_date) VALUES (?, ?, ?, ?, ?)',(os.path.basename(image_path), image_path, created_date, file_stat.st_size, now)); image_id = cursor.lastrowid
                    num_bodies, num_faces, num_dogs, person_detections, annotated_image, unmatched_faces, dog_detections = self.detect_faces_and_bodies(image_path, image_id, conn)
                    self.update_image(image_path, annotated_image); self.log(f"  Найдено фигур: {num_bodies}, лиц: {num_faces}, собак: {num_dogs}")
                    cursor.execute('UPDATE images SET num_bodies = ?, num_faces = ?, num_dogs = ? WHERE id = ?', (num_bodies, num_faces, num_dogs, image_id))
                    self.save_to_database(image_id, person_detections, unmatched_faces, dog_detections, conn)
            self.log("\nОбработка завершена!"); self.update_status("Обработка завершена", 'complete'); self.update_queue.put(('refresh_people', None)); self.update_queue.put(('refresh_dogs', None))
        except Exception as e: self.log(f"Критическая ошибка: {e}\n{traceback.format_exc()}"); self.update_status("Ошибка!", 'error')
        finally: self.processing = False; self.update_queue.put(('enable_buttons', None))

def main():
    root = tk.Tk()
    app = FaceDetectionV2(root)
    root.mainloop()

if __name__ == "__main__":
    main()