"""
Generate Unknown IDs v1.1.0
Программа для генерации уникальных ID для всех неизвестных людей и собак
в базе данных распознавания лиц

Версия 1.1.0:
- Полностью переработан UI/UX в едином стиле с другими утилитами
  (тема 'clam', улучшенная компоновка, цветная статусная строка).
- Все операции с БД вынесены в отдельный поток для предотвращения
  зависания интерфейса.
- Добавлены кнопки "Копировать лог" и "Выход".
- Улучшена обратная связь с пользователем через статусную строку.
"""

import sqlite3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime
import threading
import queue
import os

VERSION = "1.1.0"

class UnknownIDGenerator:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Generate Unknown IDs v{VERSION}")
        self.root.geometry("1000x800")
        self.root.minsize(800, 600)

        # --- Стили ---
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            pass # Fallback
        self.style.configure('TLabelFrame.Label', font=('Arial', 10, 'bold'))
        self.style.configure('Status.TLabel', font=('Arial', 11, 'bold'), padding=5)
        self.style.configure('Idle.Status.TLabel', background='lightblue', foreground='black')
        self.style.configure('Processing.Status.TLabel', background='lightyellow', foreground='black')
        self.style.configure('Complete.Status.TLabel', background='lightgreen', foreground='black')
        self.style.configure('Error.Status.TLabel', background='lightcoral', foreground='black')
        self.style.configure('Accent.TButton', font=('Arial', 10, 'bold'), foreground='navy')

        # Переменные
        self.db_path = tk.StringVar()
        self.preview_data = None
        self.is_running = False
        self.update_queue = queue.Queue()

        self.create_for_persons = tk.BooleanVar(value=True)
        self.create_for_dogs = tk.BooleanVar(value=True)
        self.use_photo_info = tk.BooleanVar(value=True)

        self.create_widgets()
        self.process_queue()
        self.update_status("Выберите базу данных и нажмите 'Анализировать'", "idle")

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Верхняя панель ---
        top_frame = ttk.LabelFrame(main_frame, text="База данных", padding="10")
        top_frame.pack(fill=tk.X, pady=(0, 5))
        top_frame.columnconfigure(0, weight=1)
        
        db_entry_frame = ttk.Frame(top_frame)
        db_entry_frame.grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))
        ttk.Entry(db_entry_frame, textvariable=self.db_path, width=70).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(top_frame, text="Выбрать...", command=self.browse_db).grid(row=0, column=1)

        # --- Панель управления ---
        control_frame = ttk.Frame(main_frame, padding=(0, 10))
        control_frame.pack(fill=tk.X)
        self.analyze_btn = ttk.Button(control_frame, text="Анализировать БД", command=lambda: self.start_action(self.analyze_database))
        self.analyze_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.preview_btn = ttk.Button(control_frame, text="Предпросмотр изменений", command=lambda: self.start_action(self.preview_changes), state=tk.DISABLED)
        self.preview_btn.pack(side=tk.LEFT, padx=5)
        self.apply_btn = ttk.Button(control_frame, text="Применить изменения", command=lambda: self.start_action(self.apply_changes), state=tk.DISABLED, style="Accent.TButton")
        self.apply_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Копировать лог", command=self.copy_log_to_clipboard).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Выход", command=self.root.destroy).pack(side=tk.RIGHT)

        # --- Опции ---
        options_frame = ttk.LabelFrame(main_frame, text="Опции", padding="10")
        options_frame.pack(fill=tk.X, pady=5)
        ttk.Checkbutton(options_frame, text="Создать ID для неизвестных людей", variable=self.create_for_persons).pack(anchor=tk.W)
        ttk.Checkbutton(options_frame, text="Создать ID для неизвестных собак", variable=self.create_for_dogs).pack(anchor=tk.W)
        ttk.Checkbutton(options_frame, text="Добавить информацию о фото в примечания", variable=self.use_photo_info).pack(anchor=tk.W)

        # --- Notebook для результатов ---
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Вкладка лога
        log_frame = ttk.Frame(self.notebook)
        self.notebook.add(log_frame, text="Лог операций")
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        self.info_label = ttk.Label(log_frame, text="", font=('Arial', 10, 'bold'), padding=5)
        self.info_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Вкладки предпросмотра
        self.persons_tree = self.create_preview_tab("Предпросмотр - Люди")
        self.dogs_tree = self.create_preview_tab("Предпросмотр - Собаки")

        # --- Статусная строка ---
        self.status_bar = ttk.Label(self.root, text="", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    def create_preview_tab(self, title):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=title)
        columns = ('Фото ID', 'Файл', 'Индекс', 'Новый ID', 'Примечание')
        tree = ttk.Treeview(frame, columns=columns, show='headings')
        for col in columns:
            tree.heading(col, text=col)
            w = {'Файл': 300, 'Примечание': 250}.get(col, 80)
            tree.column(col, width=w)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        return tree

    def browse_db(self):
        filename = filedialog.askopenfilename(title="Выберите базу данных", filetypes=[("SQLite DB", "*.db"), ("Все файлы", "*.*")])
        if filename:
            self.db_path.set(filename)
            self.update_status(f"Выбрана база: {os.path.basename(filename)}", "idle")
            self.update_queue.put(('toggle_buttons', ('disabled', 'disabled')))
            self.preview_data = None
            
    def copy_log_to_clipboard(self):
        content = self.log_text.get('1.0', tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.update_status("Лог скопирован в буфер обмена.", 'idle')

    def log(self, message):
        self.update_queue.put(('log', f"{datetime.now().strftime('%H:%M:%S')} - {message}\n"))

    def update_status(self, message, status_type):
        self.update_queue.put(('status', (message, status_type)))

    def process_queue(self):
        try:
            while True:
                action, data = self.update_queue.get_nowait()
                if action == 'log': self.log_text.insert(tk.END, data); self.log_text.see(tk.END)
                elif action == 'status': self.status_bar.config(text=data[0]); self.status_bar.config(style=data[1].title()+'.Status.TLabel')
                elif action == 'toggle_buttons': self.preview_btn.config(state=data[0]); self.apply_btn.config(state=data[1])
                elif action == 'update_info_label': self.info_label.config(text=data)
                elif action == 'clear_trees':
                    for item in self.persons_tree.get_children(): self.persons_tree.delete(item)
                    for item in self.dogs_tree.get_children(): self.dogs_tree.delete(item)
                elif action == 'insert_person': self.persons_tree.insert('', tk.END, values=data)
                elif action == 'insert_dog': self.dogs_tree.insert('', tk.END, values=data)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)

    def start_action(self, target_method):
        if self.is_running: return
        if not self.db_path.get(): messagebox.showerror("Ошибка", "Выберите базу данных"); return
        
        self.is_running = True
        self.analyze_btn.config(state=tk.DISABLED); self.preview_btn.config(state=tk.DISABLED); self.apply_btn.config(state=tk.DISABLED)
        thread = threading.Thread(target=target_method, daemon=True)
        thread.start()

    def end_action(self):
        self.is_running = False
        self.analyze_btn.config(state=tk.NORMAL)
        # Состояние других кнопок будет установлено логикой методов
        if self.preview_data:
             self.update_queue.put(('toggle_buttons', ('normal', 'normal')))
        elif hasattr(self, 'analysis_result') and self.analysis_result:
             self.update_queue.put(('toggle_buttons', ('normal', 'disabled')))

    def analyze_database(self):
        self.update_status("Анализ базы данных...", "processing")
        self.log("=== Анализ базы данных ===")
        self.analysis_result = False
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('persons', 'person_detections', 'dogs', 'dog_detections')")
                tables = [row[0] for row in cursor.fetchall()]
                has_dogs = 'dogs' in tables and 'dog_detections' in tables

                cursor.execute("SELECT COUNT(*) FROM person_detections WHERE person_id IS NULL")
                persons_without_id = cursor.fetchone()[0]
                self.log(f"Детекций людей без ID: {persons_without_id}")

                dogs_without_id = 0
                if has_dogs:
                    cursor.execute("SELECT COUNT(*) FROM dog_detections WHERE dog_id IS NULL")
                    dogs_without_id = cursor.fetchone()[0]
                    self.log(f"Детекций собак без ID: {dogs_without_id}")
                
                info_text = f"Найдено: {persons_without_id} детекций людей без ID"
                if has_dogs: info_text += f", {dogs_without_id} детекций собак без ID"
                self.update_queue.put(('update_info_label', info_text))

                if persons_without_id > 0 or dogs_without_id > 0:
                    self.analysis_result = True
                    self.update_status("Анализ завершен. Можно выполнить предпросмотр.", "complete")
                else:
                    self.log("\nНет записей для обработки!")
                    self.update_status("Анализ завершен. Нет записей для обработки.", "complete")
        except Exception as e:
            self.log(f"Ошибка анализа: {e}")
            self.update_status(f"Ошибка анализа: {e}", "error")
        finally:
            self.end_action()
            
    def preview_changes(self):
        self.update_status("Создание предпросмотра...", "processing")
        self.log("\n=== Предпросмотр изменений ===")
        self.update_queue.put(('clear_trees', None))
        
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                self.preview_data = {'persons': [], 'dogs': []}
                
                if self.create_for_persons.get():
                    cursor.execute("SELECT pd.id, pd.image_id, i.filename, i.filepath, pd.person_index, pd.has_face, i.created_date FROM person_detections pd JOIN images i ON pd.image_id = i.id WHERE pd.person_id IS NULL ORDER BY i.id, pd.person_index")
                    for row in cursor.fetchall():
                        det_id, img_id, fname, fpath, p_idx, has_face, c_date = row
                        notes = f"Авто: {datetime.now():%Y-%m-%d %H:%M}. Фото: {fname}, Индекс: {p_idx}" if self.use_photo_info.get() else ""
                        self.preview_data['persons'].append({'detection_id': det_id, 'notes': notes})
                        self.update_queue.put(('insert_person', (img_id, fname, p_idx, "Новый", f"{'С лицом' if has_face else 'Без лица'}")))

                if self.create_for_dogs.get():
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dog_detections'")
                    if cursor.fetchone():
                        cursor.execute("SELECT dd.id, dd.image_id, i.filename, i.filepath, dd.dog_index, i.created_date FROM dog_detections dd JOIN images i ON dd.image_id = i.id WHERE dd.dog_id IS NULL ORDER BY i.id, dd.dog_index")
                        for row in cursor.fetchall():
                            det_id, img_id, fname, fpath, d_idx, c_date = row
                            notes = f"Авто: {datetime.now():%Y-%m-%d %H:%M}. Фото: {fname}, Индекс: {d_idx}" if self.use_photo_info.get() else ""
                            self.preview_data['dogs'].append({'detection_id': det_id, 'notes': notes})
                            self.update_queue.put(('insert_dog', (img_id, fname, d_idx, "Новый", "Неизвестная")))
                
                self.log(f"Будет создано ID: {len(self.preview_data['persons'])} для людей, {len(self.preview_data['dogs'])} для собак.")
                if self.preview_data['persons'] or self.preview_data['dogs']:
                    self.update_status("Предпросмотр готов. Можно применить изменения.", "complete")
                else:
                    self.update_status("Нет изменений для предпросмотра.", "complete")
        except Exception as e:
            self.log(f"Ошибка предпросмотра: {e}")
            self.update_status(f"Ошибка предпросмотра: {e}", "error")
        finally:
            self.end_action()

    def apply_changes(self):
        if not self.preview_data:
            messagebox.showerror("Ошибка", "Сначала выполните предпросмотр"); return
        
        count_p = len(self.preview_data['persons'])
        count_d = len(self.preview_data['dogs'])
        if not messagebox.askyesno("Подтверждение", f"Применить изменения?\n\nСоздать {count_p} ID для людей и {count_d} ID для собак?"):
            return

        self.update_status("Применение изменений...", "processing")
        self.log("\n=== Применение изменений ===")
        
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN TRANSACTION")
                try:
                    now_iso = datetime.now().isoformat()
                    # Люди
                    for p_data in self.preview_data['persons']:
                        cursor.execute("INSERT INTO persons (is_known, notes, created_date, updated_date) VALUES (0, ?, ?, ?)", (p_data['notes'], now_iso, now_iso))
                        cursor.execute("UPDATE person_detections SET person_id = ? WHERE id = ?", (cursor.lastrowid, p_data['detection_id']))
                    self.log(f"✓ Создано ID для людей: {count_p}")
                    # Собаки
                    for d_data in self.preview_data['dogs']:
                        cursor.execute("INSERT INTO dogs (is_known, notes, created_date, updated_date) VALUES (0, ?, ?, ?)", (d_data['notes'], now_iso, now_iso))
                        cursor.execute("UPDATE dog_detections SET dog_id = ? WHERE id = ?", (cursor.lastrowid, d_data['detection_id']))
                    self.log(f"✓ Создано ID для собак: {count_d}")
                    conn.commit()
                    self.log("\n✅ Все изменения успешно применены!")
                    self.update_status("Изменения успешно применены!", "complete")
                    messagebox.showinfo("Успех", f"Успешно создано {count_p} ID для людей и {count_d} ID для собак.")
                except Exception as e:
                    conn.rollback()
                    raise e
            
            self.preview_data = None
            self.update_queue.put(('toggle_buttons', ('disabled', 'disabled')))
            self.start_action(self.analyze_database) # Повторный анализ
        except Exception as e:
            self.log(f"❌ Ошибка при применении изменений: {e}")
            self.update_status(f"Ошибка применения: {e}", "error")
            messagebox.showerror("Ошибка", f"Ошибка при применении изменений:\n{e}")
        finally:
            # end_action вызовется из повторного анализа
            pass

def main():
    root = tk.Tk()
    app = UnknownIDGenerator(root)
    root.mainloop()

if __name__ == "__main__":
    main()