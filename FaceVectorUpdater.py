"""
Face Vectors Updater v1.2.0
Программа для обновления и оптимизации векторов лиц в базе данных.

Версия 1.2.0:
- Полностью переработан UI/UX в едином стиле с другими утилитами.
- Исправлена критическая ошибка: добавлена коррекция ориентации изображений (EXIF)
  перед вычислением векторов, что предотвращало создание некорректных данных.
- Все операции с БД вынесены в отдельный поток для устранения зависаний интерфейса.
- Сохранен весь оригинальный функционал (Анализ, Обновление, Оптимизация).
"""

import sqlite3
import face_recognition
import numpy as np
import cv2
import json
from datetime import datetime
import os
from pathlib import Path
from collections import defaultdict
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
from PIL import Image, ExifTags

VERSION = "1.2.0"


def correct_image_orientation(image: Image.Image) -> Image.Image:
    """Применяет поворот к изображению PIL на основе его EXIF-данных."""
    try:
        exif = image.getexif()
        orientation_tag = next((k for k, v in ExifTags.TAGS.items() if v == 'Orientation'), None)

        if orientation_tag in exif:
            orientation = exif[orientation_tag]
            if orientation == 3: image = image.rotate(180, expand=True)
            elif orientation == 6: image = image.rotate(270, expand=True)
            elif orientation == 8: image = image.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError):
        pass # Игнорируем ошибки, если EXIF отсутствует или некорректен
    return image


class FaceVectorsUpdater:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Face Vectors Updater v{VERSION}")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)

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
        self.is_running = False
        self.update_queue = queue.Queue()
        
        self.create_widgets()
        self.process_queue()
        self.update_status("Выберите базу данных", "idle")
        
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        top_frame = ttk.LabelFrame(main_frame, text="База данных", padding="10")
        top_frame.pack(fill=tk.X, pady=(0, 5))
        top_frame.columnconfigure(0, weight=1)
        
        db_entry_frame = ttk.Frame(top_frame)
        db_entry_frame.grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))
        ttk.Entry(db_entry_frame, textvariable=self.db_path, width=70).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(top_frame, text="Выбрать...", command=self.browse_db).grid(row=0, column=1)

        control_frame = ttk.Frame(main_frame, padding=(0, 10))
        control_frame.pack(fill=tk.X)
        self.analyze_btn = ttk.Button(control_frame, text="Анализировать БД", command=lambda: self.start_action(self.analyze_database))
        self.analyze_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.update_btn = ttk.Button(control_frame, text="Обновить все векторы", command=lambda: self.start_action(self.update_vectors), state=tk.DISABLED)
        self.update_btn.pack(side=tk.LEFT, padx=5)
        self.optimize_btn = ttk.Button(control_frame, text="Оптимизировать (усреднить)", command=lambda: self.start_action(self.optimize_vectors), state=tk.DISABLED, style="Accent.TButton")
        self.optimize_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Копировать лог", command=self.copy_log_to_clipboard).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Выход", command=self.root.destroy).pack(side=tk.RIGHT)
        
        log_frame = ttk.LabelFrame(main_frame, text="Лог операций", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.status_bar = ttk.Label(self.root, text="", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def browse_db(self):
        filename = filedialog.askopenfilename(title="Выберите базу данных", filetypes=[("SQLite DB", "*.db"), ("Все файлы", "*.*")])
        if filename:
            self.db_path.set(filename)
            self.update_status(f"Выбрана база: {os.path.basename(filename)}", "idle")
            self.update_queue.put(('toggle_buttons', ('disabled', 'disabled')))

    def log(self, message):
        self.update_queue.put(('log', f"{datetime.now().strftime('%H:%M:%S')} - {message}\n"))

    def update_status(self, message, status_type):
        self.update_queue.put(('status', (message, status_type)))
        
    def copy_log_to_clipboard(self):
        content = self.log_text.get('1.0', tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.update_status("Лог скопирован в буфер обмена.", 'idle')

    def process_queue(self):
        try:
            while True:
                action, data = self.update_queue.get_nowait()
                if action == 'log': self.log_text.insert(tk.END, data); self.log_text.see(tk.END)
                elif action == 'status': self.status_bar.config(text=data[0]); self.status_bar.config(style=data[1].title()+'.Status.TLabel')
                elif action == 'toggle_buttons': self.update_btn.config(state=data[0]); self.optimize_btn.config(state=data[1])
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)

    def start_action(self, target_method):
        if self.is_running: return
        if not self.db_path.get() or not os.path.exists(self.db_path.get()):
            messagebox.showerror("Ошибка", "Выберите существующий файл базы данных")
            return
        
        self.is_running = True
        self.analyze_btn.config(state=tk.DISABLED)
        self.update_btn.config(state=tk.DISABLED)
        self.optimize_btn.config(state=tk.DISABLED)
        
        thread = threading.Thread(target=target_method, daemon=True)
        thread.start()

    def end_action(self, success=True):
        self.is_running = False
        self.analyze_btn.config(state=tk.NORMAL)
        if success:
            self.update_queue.put(('toggle_buttons', ('normal', 'normal')))

    def analyze_database(self):
        self.update_status("Анализ базы данных...", "processing")
        self.log("=== Анализ базы данных ===")
        success = False
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM persons WHERE is_known = 1")
                self.log(f"Известных людей в БД: {cursor.fetchone()[0]}")
                
                cursor.execute("SELECT COUNT(*) FROM person_detections pd JOIN persons p ON pd.person_id = p.id WHERE p.is_known = 1 AND pd.has_face = 1")
                self.log(f"Детекций с лицами известных людей: {cursor.fetchone()[0]}")
                
                cursor.execute("SELECT COUNT(*) FROM face_encodings")
                self.log(f"Всего векторов лиц в БД: {cursor.fetchone()[0]}")

                cursor.execute("SELECT COUNT(DISTINCT p.id) FROM persons p WHERE p.is_known = 1 AND NOT EXISTS (SELECT 1 FROM face_encodings fe WHERE fe.person_id = p.id)")
                persons_without_vectors = cursor.fetchone()[0]
                if persons_without_vectors > 0:
                    self.log(f"⚠️ Известных людей без векторов: {persons_without_vectors}")
                
                cursor.execute("SELECT p.full_name, COUNT(fe.id) c FROM persons p JOIN face_encodings fe ON p.id = fe.person_id WHERE p.is_known = 1 GROUP BY p.id HAVING c > 1 ORDER BY c DESC LIMIT 10")
                multi_vector_persons = cursor.fetchall()
                if multi_vector_persons:
                    self.log(f"\nЛюди с множественными векторами (топ-10):")
                    for name, count in multi_vector_persons: self.log(f"  {name}: {count} векторов")
                
                self.update_status("Анализ завершен.", "complete")
                success = True
        except Exception as e:
            self.log(f"Ошибка анализа: {e}")
            self.update_status(f"Ошибка анализа: {e}", "error")
        finally:
            self.end_action(success)

    def update_vectors(self):
        self.log("\n=== Обновление векторов лиц ===")
        success = False
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT p.id, p.full_name FROM persons p WHERE p.is_known = 1 ORDER BY p.full_name")
                persons = cursor.fetchall()
                total_persons = len(persons)
                
                for idx, (person_id, person_name) in enumerate(persons):
                    self.update_status(f"Обновление {idx+1}/{total_persons}: {person_name}", "processing")
                    
                    cursor.execute("SELECT pd.id, i.filepath FROM person_detections pd JOIN images i ON pd.image_id = i.id WHERE pd.person_id = ? AND pd.has_face = 1", (person_id,))
                    detections = cursor.fetchall()

                    if not detections:
                        self.log(f"⚠️ {person_name}: нет детекций с лицами для обновления.")
                        continue
                        
                    new_encodings = []
                    for detection_id, image_path in detections:
                        if not os.path.exists(image_path): continue
                        try:
                            pil_image = Image.open(image_path)
                            oriented_image = correct_image_orientation(pil_image)
                            image_np = cv2.cvtColor(np.array(oriented_image), cv2.COLOR_RGB2BGR)
                            
                            face_locations = face_recognition.face_locations(image_np, model='hog')
                            if face_locations:
                                face_encodings = face_recognition.face_encodings(image_np, face_locations)
                                if face_encodings:
                                    new_encodings.append({'encoding': face_encodings[0], 'detection_id': detection_id})
                        except Exception:
                            continue
                            
                    if new_encodings:
                        cursor.execute('DELETE FROM face_encodings WHERE person_id = ?', (person_id,))
                        for enc_data in new_encodings:
                            encoding_json = json.dumps(enc_data['encoding'].tolist())
                            cursor.execute("SELECT image_id FROM person_detections WHERE id = ?", (enc_data['detection_id'],))
                            image_id_res = cursor.fetchone()
                            if image_id_res:
                                cursor.execute("INSERT INTO face_encodings (person_id, image_id, face_encoding, face_location) VALUES (?, ?, ?, NULL)",
                                               (person_id, image_id_res[0], encoding_json))
                        self.log(f"✓ {person_name}: обновлено {len(new_encodings)} векторов")
                    else:
                        self.log(f"✗ {person_name}: не удалось извлечь новые векторы.")
                conn.commit()
                self.log("\nОбновление всех векторов завершено!")
                self.update_status("Обновление завершено.", "complete")
                success = True
        except Exception as e:
            self.log(f"Ошибка обновления векторов: {e}")
            self.update_status(f"Ошибка обновления: {e}", "error")
        finally:
            self.end_action(success)

    def optimize_vectors(self):
        self.log("\n=== Оптимизация (усреднение) векторов ===")
        success = False
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS person_average_encodings (id INTEGER PRIMARY KEY, person_id INTEGER UNIQUE, average_encoding TEXT, num_samples INTEGER, created_date TEXT, FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE)")
                
                cursor.execute("SELECT p.id, p.full_name FROM persons p JOIN face_encodings fe ON p.id = fe.person_id WHERE p.is_known = 1 GROUP BY p.id HAVING COUNT(fe.id) > 0")
                persons = cursor.fetchall()
                total_persons = len(persons)
                
                for idx, (person_id, person_name) in enumerate(persons):
                    self.update_status(f"Оптимизация {idx+1}/{total_persons}: {person_name}", "processing")
                    cursor.execute("SELECT face_encoding FROM face_encodings WHERE person_id = ?", (person_id,))
                    
                    encodings = [np.array(json.loads(row[0])) for row in cursor.fetchall()]
                    if encodings:
                        average_encoding = np.mean(encodings, axis=0)
                        cursor.execute("INSERT OR REPLACE INTO person_average_encodings (person_id, average_encoding, num_samples, created_date) VALUES (?, ?, ?, ?)",
                                       (person_id, json.dumps(average_encoding.tolist()), len(encodings), datetime.now().isoformat()))
                        self.log(f"✓ {person_name}: создан усредненный вектор из {len(encodings)} образцов.")
                conn.commit()
                self.log("\nОптимизация векторов завершена!")
                self.update_status("Оптимизация завершена.", "complete")
                success = True
        except Exception as e:
            self.log(f"Ошибка оптимизации: {e}")
            self.update_status(f"Ошибка оптимизации: {e}", "error")
        finally:
            self.end_action(success)


def main():
    root = tk.Tk()
    app = FaceVectorsUpdater(root)
    root.mainloop()

if __name__ == "__main__":
    main()