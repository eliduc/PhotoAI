"""
Face Database Cleaner GUI v1.5.0
Графическое приложение для поиска и слияния дубликатов, включая поиск
людей по схожести векторов лиц.

Версия: 1.5.0
- Полностью переработан интерфейс в стиле Face Detection v2.8 для
  единообразного, чистого и современного вида (тема 'clam').
- Улучшена читаемость: увеличены шрифты, добавлены отступы, элементы сгруппированы.
- Добавлена цветная статусная строка для интуитивного отображения состояния
  (готовность, обработка, успех, ошибка).
- Добавлены пояснения к настройкам порогов схожести для фото и лиц.
- Улучшен диалог слияния людей: форма для итоговых данных теперь находится
  между сравниваемыми людьми для большей наглядности.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import sqlite3
import os
import threading
import json
import traceback
from datetime import datetime
from PIL import Image, ImageTk

try:
    import imagehash
except ImportError:
    messagebox.showerror("Отсутствует библиотека", "Необходима библиотека 'ImageHash'.\nУстановите ее: pip install ImageHash")
    exit()
try:
    import numpy as np
except ImportError:
    messagebox.showerror("Отсутствует библиотека", "Необходима библиотека 'numpy'.\nУстановите ее: pip install numpy")
    exit()


VERSION = "1.5.0"

# --- ДИАЛОГОВЫЕ ОКНА ---

class DuplicatePhotosDialog(tk.Toplevel):
    def __init__(self, parent, duplicate_groups):
        super().__init__(parent)
        self.duplicate_groups = duplicate_groups
        self.result = {'delete_ids': [], 'delete_files': False}
        self.checkbox_vars = {}
        self.title("Найденные дубликаты фотографий")
        self.geometry("1000x750")

        top_panel = ttk.Frame(self, padding=10)
        top_panel.pack(fill=tk.X, side=tk.TOP)

        self.delete_files_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top_panel, text="Физически удалить файлы с диска (НЕОБРАТИМО!)", variable=self.delete_files_var).pack(side=tk.LEFT)

        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_frame, text="Подтвердить удаление", command=self.confirm).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(btn_frame, text="Отмена", command=self.cancel).pack(side=tk.RIGHT, expand=True, fill=tk.X)

        canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, padding=5)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.populate_duplicates(scrollable_frame)
        self.transient(parent); self.grab_set(); self.focus_set()

    def populate_duplicates(self, parent_frame):
        thumb_size = (150, 150)
        for i, group in enumerate(self.duplicate_groups):
            group_frame = ttk.LabelFrame(parent_frame, text=f"Группа {i+1}", padding=10)
            group_frame.pack(fill=tk.X, expand=True, padx=10, pady=5)
            for image_id, filepath, _, _, size_kb in group:
                item_frame = ttk.Frame(group_frame)
                item_frame.pack(side=tk.LEFT, padx=5, pady=5, anchor=tk.N)
                try:
                    with Image.open(filepath) as img:
                        w, h = img.size
                        img.thumbnail(thumb_size, Image.Resampling.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                    img_label = ttk.Label(item_frame, image=photo)
                    img_label.image = photo
                    img_label.pack()
                    info_text = f"{os.path.basename(filepath)}\n{w}x{h} - {size_kb} KB"
                    ttk.Label(item_frame, text=info_text, justify=tk.CENTER).pack()
                    cb_var = tk.BooleanVar(value=False)
                    ttk.Checkbutton(item_frame, text="Удалить", variable=cb_var).pack()
                    self.checkbox_vars[image_id] = (cb_var, filepath)
                except Exception:
                    error_frame = ttk.Frame(item_frame, width=thumb_size[0], height=thumb_size[1], borderwidth=1, relief="solid")
                    error_frame.pack_propagate(False)
                    error_frame.pack()
                    ttk.Label(error_frame, text="Ошибка\nзагрузки", wraplength=140).pack(expand=True)
                    ttk.Label(item_frame, text=f"{os.path.basename(filepath)}", justify=tk.CENTER).pack()

    def confirm(self):
        self.result['delete_ids'] = [img_id for img_id, (var, _) in self.checkbox_vars.items() if var.get()]
        if not self.result['delete_ids']:
            messagebox.showinfo("Нет выбора", "Не выбрано ни одного фото для удаления.", parent=self)
            return
        self.result['delete_files'] = self.delete_files_var.get()
        if self.result['delete_files']:
            if not messagebox.askyesno("Подтверждение", "Вы уверены, что хотите НАВСЕГДА удалить файлы с диска?", icon='warning', parent=self):
                return
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()

class MergeSimilarPeopleDialog(tk.Toplevel):
    def __init__(self, parent, pairs_to_review, person_data):
        super().__init__(parent)
        self.parent = parent
        self.pairs = pairs_to_review
        self.person_data = person_data
        self.current_pair_index = 0
        self.merge_actions = []

        self.title("Объединение людей со схожими лицами")
        self.geometry("1100x700")
        self.minsize(1000, 600)

        self.full_name_var = tk.StringVar()
        self.short_name_var = tk.StringVar()

        self.main_frame = ttk.Frame(self, padding=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.info_label = ttk.Label(self.main_frame, text="", font=("Arial", 12))
        self.info_label.pack(pady=10)

        self.comparison_frame = ttk.Frame(self.main_frame)
        self.comparison_frame.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_frame, text="Объединить", command=self.merge, style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Пропустить", command=self.skip).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Завершить и сохранить", command=self.finish).pack(side=tk.RIGHT, padx=5)

        self.load_pair()
        self.transient(parent); self.grab_set(); self.focus_set()

    def load_pair(self):
        for widget in self.comparison_frame.winfo_children():
            widget.destroy()

        if self.current_pair_index >= len(self.pairs):
            self.finish()
            return

        self.info_label.config(text=f"Пара {self.current_pair_index + 1} из {len(self.pairs)}. Решите, что делать с этими людьми.")
        id1, id2 = self.pairs[self.current_pair_index]
        self.person1_id, self.person2_id = id1, id2

        # --- УЛУЧШЕННЫЙ МАКЕТ: 3 КОЛОНКИ ---
        frame1 = self.create_person_frame(self.comparison_frame, "Человек 1", self.person_data[id1])
        frame1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        ttk.Button(frame1, text="Использовать эти данные ->", command=lambda: self.populate_form(self.person_data[id1]['info'])).pack(pady=10)

        form_frame = self.create_merge_form(self.comparison_frame)
        form_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        frame2 = self.create_person_frame(self.comparison_frame, "Человек 2", self.person_data[id2])
        frame2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        ttk.Button(frame2, text="<- Использовать эти данные", command=lambda: self.populate_form(self.person_data[id2]['info'])).pack(pady=10)

        self.populate_form(self.person_data[id1]['info'])

    def create_person_frame(self, parent, title, data):
        p_frame = ttk.LabelFrame(parent, text=title, padding=10)
        faces_frame = ttk.Frame(p_frame)
        faces_frame.pack(pady=5, fill=tk.X)
        ttk.Label(faces_frame, text="Примеры лиц:").pack()
        face_container = ttk.Frame(faces_frame)
        face_container.pack()

        for face_info in data['faces'][:4]:
            try:
                with Image.open(face_info['filepath']) as img:
                    face_box = (face_info['location'][3], face_info['location'][0], face_info['location'][1], face_info['location'][2])
                    face_img = img.crop(face_box)
                    face_img.thumbnail((80, 80), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(face_img)
                    face_label = ttk.Label(face_container, image=photo)
                    face_label.image = photo
                    face_label.pack(side=tk.LEFT, padx=2)
            except Exception: pass

        ttk.Separator(p_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        info = data['info']
        for key, value in info.items():
            ttk.Label(p_frame, text=f"{key.replace('_',' ').title()}: {value}").pack(anchor=tk.W)
        return p_frame

    def create_merge_form(self, parent):
        form_frame = ttk.LabelFrame(parent, text="Итоговые данные (после слияния)", padding=10)
        ttk.Label(form_frame, text="Полное имя:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(form_frame, textvariable=self.full_name_var, width=40).grid(row=0, column=1, sticky=tk.EW, pady=2)
        ttk.Label(form_frame, text="Короткое имя:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(form_frame, textvariable=self.short_name_var, width=40).grid(row=1, column=1, sticky=tk.EW, pady=2)
        ttk.Label(form_frame, text="Примечание:").grid(row=2, column=0, sticky=tk.NW, pady=2)
        self.notes_text = scrolledtext.ScrolledText(form_frame, width=30, height=5, wrap=tk.WORD)
        self.notes_text.grid(row=2, column=1, sticky=tk.EW, pady=2)
        form_frame.columnconfigure(1, weight=1)
        return form_frame

    def populate_form(self, info):
        self.full_name_var.set(info.get('full_name', ''))
        self.short_name_var.set(info.get('short_name', ''))
        self.notes_text.delete('1.0', tk.END)
        self.notes_text.insert('1.0', info.get('notes') or "")

    def skip(self):
        self.current_pair_index += 1
        self.load_pair()

    def merge(self):
        full_name = self.full_name_var.get().strip()
        if not full_name:
            messagebox.showwarning("Нужно имя", "Полное имя не может быть пустым.", parent=self)
            return
        action = {'id_to_keep': min(self.person1_id, self.person2_id),
                  'id_to_delete': max(self.person1_id, self.person2_id),
                  'full_name': full_name,
                  'short_name': self.short_name_var.get().strip() or full_name.split()[0],
                  'notes': self.notes_text.get('1.0', tk.END).strip()}
        self.merge_actions.append(action)
        self.skip()

    def finish(self):
        self.destroy()

# --- ОСНОВНОЙ КЛАСС ПРИЛОЖЕНИЯ ---

class FaceDBCleanerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"FaceDB Cleaner GUI v{VERSION}")
        self.root.geometry("800x650")
        self.root.minsize(700, 600)

        # --- УЛУЧШЕНИЕ UI/UX: Стили и тема ---
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            pass # Если тема недоступна, используется тема по умолчанию
        self.style.configure('TLabelFrame.Label', font=('Arial', 10, 'bold'))
        self.style.configure('Status.TLabel', font=('Arial', 10, 'bold'), padding=5)
        self.style.configure('Idle.Status.TLabel', background='lightblue', foreground='black')
        self.style.configure('Processing.Status.TLabel', background='lightyellow', foreground='black')
        self.style.configure('Complete.Status.TLabel', background='lightgreen', foreground='black')
        self.style.configure('Error.Status.TLabel', background='lightcoral', foreground='black')
        self.style.configure('Accent.TButton', font=('Arial', 10, 'bold'), foreground='navy')


        self.db_path = tk.StringVar()
        self.is_running = False

        self.clean_people_var = tk.BooleanVar(value=True)
        self.clean_dogs_var = tk.BooleanVar(value=True)
        self.clean_photos_var = tk.BooleanVar(value=False)
        self.clean_similar_faces_var = tk.BooleanVar(value=False)
        self.photo_hash_threshold = tk.IntVar(value=5)
        self.face_similarity_threshold = tk.DoubleVar(value=0.5)

        self.create_widgets()
        self.update_status("Выберите файл и опции для начала работы.", 'idle')

    def create_widgets(self):
        main_pane = ttk.Frame(self.root, padding=10)
        main_pane.pack(fill=tk.BOTH, expand=True)

        # --- Верхняя панель выбора файла ---
        top_frame = ttk.LabelFrame(main_pane, text="База данных", padding=10)
        top_frame.pack(side=tk.TOP, fill=tk.X)
        top_frame.columnconfigure(0, weight=1)
        ttk.Entry(top_frame, textvariable=self.db_path, width=70).grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))
        ttk.Button(top_frame, text="Выбрать...", command=self.browse_db).grid(row=0, column=1)

        # --- Панель опций ---
        options_frame = ttk.LabelFrame(main_pane, text="Опции очистки", padding=10)
        options_frame.pack(fill=tk.X, pady=10)

        ttk.Checkbutton(options_frame, text="Объединить дубликаты людей (по точному совпадению имен)", variable=self.clean_people_var).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(options_frame, text="Объединить дубликаты собак (по точным данным)", variable=self.clean_dogs_var).pack(anchor=tk.W, pady=2)

        # Поиск дубликатов фото
        photo_frame = ttk.Frame(options_frame)
        photo_frame.pack(fill=tk.X, anchor=tk.W, pady=(8,0))
        ttk.Checkbutton(photo_frame, text="Найти и удалить дубликаты фото", variable=self.clean_photos_var).pack(side=tk.LEFT)
        ttk.Label(photo_frame, text="Порог схожести (0=точно, 10=свободно):").pack(side=tk.LEFT, padx=(20, 5))
        ttk.Scale(photo_frame, from_=0, to=10, variable=self.photo_hash_threshold, orient=tk.HORIZONTAL, length=150, command=lambda v: self.photo_hash_threshold.set(int(float(v)))).pack(side=tk.LEFT)
        ttk.Label(photo_frame, textvariable=self.photo_hash_threshold, font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=5)

        # Поиск схожих лиц
        face_sim_frame = ttk.Frame(options_frame)
        face_sim_frame.pack(fill=tk.X, anchor=tk.W, pady=(5,0))
        ttk.Checkbutton(face_sim_frame, text="Найти людей со схожими лицами (но разными именами)", variable=self.clean_similar_faces_var).pack(side=tk.LEFT)
        ttk.Label(face_sim_frame, text="Порог схожести (меньше = строже):").pack(side=tk.LEFT, padx=(20, 5))
        ttk.Scale(face_sim_frame, from_=0.3, to=0.7, variable=self.face_similarity_threshold, orient=tk.HORIZONTAL, length=150).pack(side=tk.LEFT)
        face_thr_label = ttk.Label(face_sim_frame, text=f"{self.face_similarity_threshold.get():.2f}", font=('Arial', 10, 'bold'))
        face_thr_label.pack(side=tk.LEFT, padx=5)
        self.face_similarity_threshold.trace_add('write', lambda *args: face_thr_label.config(text=f"{self.face_similarity_threshold.get():.2f}"))

        # --- Панель логов и управления ---
        log_frame = ttk.LabelFrame(main_pane, text="Лог выполнения", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)

        control_frame = ttk.Frame(log_frame)
        control_frame.pack(fill=tk.X, pady=(0, 5))
        self.start_btn = ttk.Button(control_frame, text="🚀 Начать очистку", command=self.start_cleaning, style="Accent.TButton")
        self.start_btn.pack(side=tk.LEFT)
        self.copy_btn = ttk.Button(control_frame, text="📋 Копировать лог", width=18, command=self.copy_log_to_clipboard)
        self.copy_btn.pack(side=tk.RIGHT)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state=tk.DISABLED, relief=tk.SOLID, borderwidth=1)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.status_label = ttk.Label(self.root, text="", relief=tk.SUNKEN, anchor=tk.W, style="Idle.Status.TLabel")
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

    def update_status(self, message, status_type):
        self.status_label.config(text=message)
        style_map = {'idle': 'Idle.Status.TLabel', 'processing': 'Processing.Status.TLabel',
                     'complete': 'Complete.Status.TLabel', 'error': 'Error.Status.TLabel'}
        self.status_label.config(style=style_map.get(status_type, 'Idle.Status.TLabel'))

    def copy_log_to_clipboard(self):
        content = self.log_text.get('1.0', tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.update_status("Лог скопирован в буфер обмена.", 'idle')

    def browse_db(self):
        if self.is_running: return
        filename = filedialog.askopenfilename(title="Выберите базу данных", filetypes=[("SQLite DB", "*.db"), ("Все файлы", "*.*")])
        if filename:
            self.db_path.set(filename)
            self.update_status(f"Выбрана база данных: {os.path.basename(filename)}", 'idle')

    def log(self, message):
        self.root.after(0, self._log_threadsafe, message)

    def _log_threadsafe(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def start_cleaning(self):
        if self.is_running: return
        db_path_val = self.db_path.get()
        if not db_path_val or not os.path.exists(db_path_val):
            messagebox.showerror("Ошибка", "Путь к базе данных не указан или файл не существует.")
            return
        if not any([self.clean_people_var.get(), self.clean_dogs_var.get(), self.clean_photos_var.get(), self.clean_similar_faces_var.get()]):
            messagebox.showwarning("Нет выбора", "Выберите хотя бы одну опцию для очистки.")
            return

        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete('1.0', tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.update_status("Выполнение...", 'processing')

        thread = threading.Thread(target=self.cleaning_thread, args=(db_path_val,), daemon=True)
        thread.start()

    def cleaning_thread(self, db_path_val):
        conn = None
        try:
            self.log(f"Подключение к БД: {db_path_val}")
            conn = sqlite3.connect(db_path_val)
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")

            results = {'exact_persons': 0, 'dogs': 0, 'photos': 0, 'similar_persons': 0}

            if self.clean_people_var.get():
                results['exact_persons'] = self.merge_exact_duplicates(cursor, 'persons')
            if self.clean_dogs_var.get():
                results['dogs'] = self.merge_exact_duplicates(cursor, 'dogs')
            if self.clean_photos_var.get():
                results['photos'] = self.process_photo_duplicates(cursor)
            if self.clean_similar_faces_var.get():
                results['similar_persons'] = self.process_similar_faces(cursor)

            if any(results.values()):
                conn.commit()
                self.log("\n------------------------------------")
                self.log("✅ Все изменения успешно сохранены.")
                if results['exact_persons'] > 0: self.log(f"   - Объединено людей по именам: {results['exact_persons']}")
                if results['dogs'] > 0: self.log(f"   - Объединено собак по данным: {results['dogs']}")
                if results['photos'] > 0: self.log(f"   - Удалено дубликатов фото: {results['photos']}")
                if results['similar_persons'] > 0: self.log(f"   - Объединено людей по лицам: {results['similar_persons']}")
                self.log("------------------------------------")
                self.update_status("Очистка успешно завершена!", 'complete')
            else:
                self.log("\n------------------------------------")
                self.log("База данных не требовала изменений.")
                self.log("------------------------------------")
                self.update_status("Очистка завершена. Изменения не требовались.", 'complete')

        except Exception as e:
            self.log(f"\n❌ ПРОИЗОШЛА ОШИБКА: {e}\n{traceback.format_exc()}")
            if conn:
                conn.rollback()
                self.update_status("Ошибка! Изменения отменены.", 'error')
        finally:
            if conn:
                conn.close()
            self.is_running = False
            self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL))

    def process_photo_duplicates(self, cursor):
        self.log("\n--- Поиск дубликатов фотографий (может занять время) ---")
        cursor.execute("SELECT id, filepath, 0, 0, file_size FROM images")
        all_images = cursor.fetchall()
        hashes = {}
        self.log(f"Хеширование {len(all_images)} изображений...")

        for i, (img_id, filepath, _, _, _) in enumerate(all_images):
            if not os.path.exists(filepath):
                self.log(f"  ! Файл не найден, пропуск: {filepath}")
                continue
            try:
                with Image.open(filepath) as img:
                    img_hash = imagehash.phash(img)
                if img_hash not in hashes:
                    hashes[img_hash] = []
                hashes[img_hash].append(img_id)
            except Exception as e:
                self.log(f"  ! Ошибка чтения файла {filepath}: {e}")
                continue
            if (i + 1) % 50 == 0:
                self.update_status(f"Хеширование... {i+1}/{len(all_images)}", 'processing')

        self.log("Поиск схожих изображений...")
        threshold = self.photo_hash_threshold.get()
        groups, processed_hashes = [], set()
        hash_list = list(hashes.keys())

        for i in range(len(hash_list)):
            h1 = hash_list[i]
            if h1 in processed_hashes: continue
            current_group_hashes = {h1}
            for j in range(i + 1, len(hash_list)):
                h2 = hash_list[j]
                if h2 in processed_hashes: continue
                if (h1 - h2) <= threshold:
                    current_group_hashes.add(h2)

            # Группа считается дубликатами, если в ней >1 хеша ИЛИ у одного хеша >1 картинки
            if len(current_group_hashes) > 1 or any(len(hashes[h]) > 1 for h in current_group_hashes):
                image_ids_in_group = [img_id for h in current_group_hashes for img_id in hashes[h]]
                processed_hashes.update(current_group_hashes)
                placeholders = ','.join('?' * len(image_ids_in_group))
                cursor.execute(f"SELECT id, filepath, 0, 0, file_size FROM images WHERE id IN ({placeholders})", image_ids_in_group)
                groups.append(cursor.fetchall())

        if not groups:
            self.log("Дубликаты фотографий не найдены."); return 0

        self.log(f"Найдено {len(groups)} групп дубликатов. Открытие окна выбора...")
        dialog_result = None
        event = threading.Event()

        def run_dialog():
            nonlocal dialog_result
            dialog = DuplicatePhotosDialog(self.root, groups)
            self.root.wait_window(dialog)
            dialog_result = dialog.result
            event.set()

        self.root.after(0, run_dialog)
        event.wait()

        if not dialog_result or not dialog_result['delete_ids']:
            self.log("Удаление фотографий отменено пользователем."); return 0

        ids_to_delete = dialog_result['delete_ids']
        self.log(f"\nУдаление {len(ids_to_delete)} выбранных фотографий из БД...")
        placeholders = ','.join('?' * len(ids_to_delete))

        paths_to_delete_physically = []
        if dialog_result['delete_files']:
            cursor.execute(f"SELECT filepath FROM images WHERE id IN ({placeholders})", ids_to_delete)
            paths_to_delete_physically = [row[0] for row in cursor.fetchall()]

        cursor.execute(f"DELETE FROM images WHERE id IN ({placeholders})", ids_to_delete)
        self.log(f"  - Удалено {cursor.rowcount} записей из 'images' (связанные записи удалены каскадно).")

        if paths_to_delete_physically:
            self.log("Физическое удаление файлов с диска..."); deleted_count = 0
            for fpath in paths_to_delete_physically:
                try:
                    if os.path.exists(fpath):
                        os.remove(fpath)
                        deleted_count += 1
                except OSError as e:
                    self.log(f"  - Ошибка удаления файла {fpath}: {e}")
            self.log(f"  - Физически удалено {deleted_count} файлов.")
        return len(ids_to_delete)

    def merge_exact_duplicates(self, cursor, table_name='persons'):
        if table_name == 'persons':
            self.log("\n--- Объединение дубликатов людей (по именам) ---")
            group_by_fields, id_field, name_field = ["full_name", "short_name"], "person_id", "full_name"
            update_tables = ["person_detections", "face_encodings"]
        elif table_name == 'dogs':
            self.log("\n--- Объединение дубликатов собак ---")
            group_by_fields, id_field, name_field = ["name", "breed", "owner"], "dog_id", "name"
            update_tables = ["dog_detections"]
        else: return 0

        group_by_sql = ", ".join([f"lower(trim(COALESCE({field},'')))" for field in group_by_fields])
        cursor.execute(f"SELECT group_concat(id) FROM {table_name} WHERE is_known = 1 AND {name_field} IS NOT NULL AND trim({name_field}) != '' GROUP BY {group_by_sql} HAVING count(*) > 1")
        duplicates = cursor.fetchall()

        if not duplicates:
            self.log(f"Дубликаты в '{table_name}' не найдены."); return 0

        total_merged_count = 0
        self.log(f"Найдено {len(duplicates)} групп дубликатов в '{table_name}'.")

        for (ids_str,) in duplicates:
            ids = sorted([int(id_val) for id_val in ids_str.split(',')])
            id_to_keep, ids_to_delete = ids[0], ids[1:]
            cursor.execute(f"SELECT {name_field} FROM {table_name} WHERE id = ?", (id_to_keep,))
            name = cursor.fetchone()[0]
            self.log(f"  - Слияние дубликатов для '{name}' (ID: {id_to_keep}) <- {ids_to_delete}")
            placeholders = ','.join('?' * len(ids_to_delete))

            for update_table in update_tables:
                cursor.execute(f"UPDATE {update_table} SET {id_field} = ? WHERE {id_field} IN ({placeholders})", [id_to_keep] + ids_to_delete)
            cursor.execute(f"DELETE FROM {table_name} WHERE id IN ({placeholders})", ids_to_delete)
            total_merged_count += len(ids_to_delete)
        return total_merged_count

    def process_similar_faces(self, cursor):
        self.log("\n--- Поиск людей со схожими лицами ---")
        self.update_status("Загрузка данных о людях и их лицах...", 'processing')

        sql = """
            SELECT p.id, p.full_name, p.short_name, p.notes,
                   fe.face_encoding, fe.face_location, i.filepath
            FROM persons p
            JOIN face_encodings fe ON p.id = fe.person_id
            JOIN images i ON fe.image_id = i.id
            WHERE p.is_known = 1
            ORDER BY p.id;
        """
        cursor.execute(sql)
        all_rows = cursor.fetchall()

        if not all_rows:
            self.log("В базе данных нет известных людей с лицами для анализа."); return 0

        person_data = {}
        for pid, full_name, short_name, notes, enc_json, loc_json, filepath in all_rows:
            if pid not in person_data:
                person_data[pid] = {
                    'info': {'id': pid, 'full_name': full_name, 'short_name': short_name, 'notes': notes},
                    'faces': []
                }
            if enc_json and loc_json:
                person_data[pid]['faces'].append({
                    'encoding': np.array(json.loads(enc_json)),
                    'location': json.loads(loc_json),
                    'filepath': filepath})

        self.log(f"Найдено {len(person_data)} известных людей с лицами для анализа.")
        if len(person_data) < 2:
            self.log("Для сравнения необходимо как минимум 2 человека. Анализ пропущен."); return 0

        avg_encodings = {pid: np.mean([f['encoding'] for f in data['faces']], axis=0) for pid, data in person_data.items() if data['faces']}

        self.update_status("Сравнение лиц...", 'processing')
        person_ids = list(avg_encodings.keys())
        pairs_to_review = []
        threshold = self.face_similarity_threshold.get()

        for i in range(len(person_ids)):
            for j in range(i + 1, len(person_ids)):
                id1, id2 = person_ids[i], person_ids[j]
                if np.linalg.norm(avg_encodings[id1] - avg_encodings[id2]) < threshold:
                    pairs_to_review.append((id1, id2))

        if not pairs_to_review:
            self.log("Потенциально одинаковых людей с разными именами не найдено."); return 0

        self.log(f"Найдено {len(pairs_to_review)} потенциальных пар. Открытие окна для объединения...")
        dialog = None
        event = threading.Event()
        def run_dialog():
            nonlocal dialog
            dialog = MergeSimilarPeopleDialog(self.root, pairs_to_review, person_data)
            self.root.wait_window(dialog)
            event.set()
        self.root.after(0, run_dialog)
        event.wait()

        if not dialog or not dialog.merge_actions:
            self.log("Объединение людей отменено или пропущено."); return 0

        self.log(f"\nВыполнение {len(dialog.merge_actions)} слияний...")
        merged_count = 0
        for action in dialog.merge_actions:
            id_k, id_d = action['id_to_keep'], action['id_to_delete']
            self.log(f"  - Объединение ID {id_d} -> ID {id_k} с именем '{action['full_name']}'")
            cursor.execute("UPDATE persons SET full_name=?, short_name=?, notes=?, updated_date=? WHERE id=?",
                         (action['full_name'], action['short_name'], action['notes'], datetime.now().isoformat(), id_k))
            cursor.execute("UPDATE person_detections SET person_id=? WHERE person_id=?", (id_k, id_d))
            cursor.execute("UPDATE face_encodings SET person_id=? WHERE person_id=?", (id_k, id_d))
            cursor.execute("DELETE FROM persons WHERE id=?", (id_d,))
            merged_count += 1
        return merged_count

def main():
    root = tk.Tk()
    app = FaceDBCleanerGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()