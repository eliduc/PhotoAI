"""
Face Vectors Updater v1.3.0
Program for updating and optimizing face vectors in the database.

Version 1.3.0:
- All code comments translated to English for better international collaboration.
- Minor code cleanup and consistency improvements.

Version 1.2.0:
- Completely redesigned UI/UX in unified style with other utilities.
- Fixed critical bug: added image orientation correction (EXIF) before computing vectors,
  preventing creation of incorrect data.
- All DB operations moved to separate thread to prevent UI freezing.
- Preserved all original functionality (Analysis, Update, Optimization).
- Added multilingual interface support (EN/RU).
- Copy log button replaced with compact icon in the corner.
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

VERSION = "1.3.0"

# Translations
TRANSLATIONS = {
    'EN': {
        # Main window
        'window_title': f"Face Vectors Updater v{VERSION}",
        'select_database': 'Database',
        'choose_button': 'Choose...',
        'analyze_button': 'Analyze DB',
        'update_button': 'Update all vectors',
        'optimize_button': 'Optimize (average)',
        'exit_button': 'Exit',
        'log_title': 'Operation Log',
        'language_label': 'Language:',
        
        # Status messages
        'status_ready': 'Select a database',
        'status_analyzing': 'Analyzing database...',
        'status_analysis_complete': 'Analysis completed.',
        'status_updating': 'Updating {idx}/{total}: {name}',
        'status_update_complete': 'Update completed.',
        'status_optimizing': 'Optimizing {idx}/{total}: {name}',
        'status_optimization_complete': 'Optimization completed.',
        'status_error': 'Error: {error}',
        
        # Log messages
        'log_db_selected': 'Database selected: {path}',
        'log_analysis_start': '=== Database Analysis ===',
        'log_known_people': 'Known people in DB: {count}',
        'log_detections_with_faces': 'Detections with faces of known people: {count}',
        'log_total_vectors': 'Total face vectors in DB: {count}',
        'log_people_without_vectors': '⚠️ Known people without vectors: {count}',
        'log_people_with_multiple': '\nPeople with multiple vectors (top-10):',
        'log_person_vector_count': '  {name}: {count} vectors',
        
        'log_update_start': '\n=== Updating Face Vectors ===',
        'log_no_detections': '⚠️ {name}: no face detections to update.',
        'log_vectors_updated': '✓ {name}: updated {count} vectors',
        'log_no_vectors_extracted': '✗ {name}: could not extract new vectors.',
        'log_update_complete': '\nAll vectors update completed!',
        
        'log_optimization_start': '\n=== Optimizing (Averaging) Vectors ===',
        'log_average_created': '✓ {name}: created average vector from {count} samples.',
        'log_optimization_complete': '\nVector optimization completed!',
        
        'log_copied': 'Log copied to clipboard.',
        
        # Error messages
        'error_title': 'Error',
        'error_no_db': 'Select an existing database file',
        'error_analysis': 'Analysis error: {error}',
        'error_update': 'Update error: {error}',
        'error_optimization': 'Optimization error: {error}'
    },
    'RU': {
        # Main window
        'window_title': f"Обновление векторов лиц v{VERSION}",
        'select_database': 'База данных',
        'choose_button': 'Выбрать...',
        'analyze_button': 'Анализировать БД',
        'update_button': 'Обновить все векторы',
        'optimize_button': 'Оптимизировать (усреднить)',
        'exit_button': 'Выход',
        'log_title': 'Лог операций',
        'language_label': 'Language:',
        
        # Status messages
        'status_ready': 'Выберите базу данных',
        'status_analyzing': 'Анализ базы данных...',
        'status_analysis_complete': 'Анализ завершен.',
        'status_updating': 'Обновление {idx}/{total}: {name}',
        'status_update_complete': 'Обновление завершено.',
        'status_optimizing': 'Оптимизация {idx}/{total}: {name}',
        'status_optimization_complete': 'Оптимизация завершена.',
        'status_error': 'Ошибка: {error}',
        
        # Log messages
        'log_db_selected': 'Выбрана база: {path}',
        'log_analysis_start': '=== Анализ базы данных ===',
        'log_known_people': 'Известных людей в БД: {count}',
        'log_detections_with_faces': 'Детекций с лицами известных людей: {count}',
        'log_total_vectors': 'Всего векторов лиц в БД: {count}',
        'log_people_without_vectors': '⚠️ Известных людей без векторов: {count}',
        'log_people_with_multiple': '\nЛюди с множественными векторами (топ-10):',
        'log_person_vector_count': '  {name}: {count} векторов',
        
        'log_update_start': '\n=== Обновление векторов лиц ===',
        'log_no_detections': '⚠️ {name}: нет детекций с лицами для обновления.',
        'log_vectors_updated': '✓ {name}: обновлено {count} векторов',
        'log_no_vectors_extracted': '✗ {name}: не удалось извлечь новые векторы.',
        'log_update_complete': '\nОбновление всех векторов завершено!',
        
        'log_optimization_start': '\n=== Оптимизация (усреднение) векторов ===',
        'log_average_created': '✓ {name}: создан усредненный вектор из {count} образцов.',
        'log_optimization_complete': '\nОптимизация векторов завершена!',
        
        'log_copied': 'Лог скопирован в буфер обмена.',
        
        # Error messages
        'error_title': 'Ошибка',
        'error_no_db': 'Выберите существующий файл базы данных',
        'error_analysis': 'Ошибка анализа: {error}',
        'error_update': 'Ошибка обновления: {error}',
        'error_optimization': 'Ошибка оптимизации: {error}'
    }
}


def correct_image_orientation(image: Image.Image) -> Image.Image:
    """Applies rotation to PIL image based on its EXIF data."""
    try:
        exif = image.getexif()
        orientation_tag = next((k for k, v in ExifTags.TAGS.items() if v == 'Orientation'), None)

        if orientation_tag in exif:
            orientation = exif[orientation_tag]
            if orientation == 3: image = image.rotate(180, expand=True)
            elif orientation == 6: image = image.rotate(270, expand=True)
            elif orientation == 8: image = image.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError):
        pass # Ignore errors if EXIF is missing or incorrect
    return image


class FaceVectorsUpdater:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Face Vectors Updater v{VERSION}")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)

        # Language setting
        self.current_language = tk.StringVar(value="EN")
        self.current_language.trace_add('write', self.on_language_change)
        
        # --- Styles ---
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

        # Variables
        self.db_path = tk.StringVar()
        self.is_running = False
        self.update_queue = queue.Queue()
        
        self.create_widgets()
        self.process_queue()
        self.update_status(self.tr('status_ready'), "idle")
        
    def tr(self, key, **kwargs):
        """Get translated string for current language"""
        text = TRANSLATIONS.get(self.current_language.get(), TRANSLATIONS['EN']).get(key, key)
        if kwargs:
            text = text.format(**kwargs)
        return text
    
    def on_language_change(self, *args):
        """Update UI when language changes"""
        self.root.title(self.tr('window_title'))
        self.db_label.config(text=self.tr('select_database'))
        self.browse_btn.config(text=self.tr('choose_button'))
        self.analyze_btn.config(text=self.tr('analyze_button'))
        self.update_btn.config(text=self.tr('update_button'))
        self.optimize_btn.config(text=self.tr('optimize_button'))
        self.exit_btn.config(text=self.tr('exit_button'))
        self.log_frame.config(text=self.tr('log_title'))
        self.lang_label.config(text=self.tr('language_label'))
        
        # Update status with current status type
        current_status = getattr(self, 'current_status_type', 'idle')
        if current_status == 'idle':
            self.update_status(self.tr('status_ready'), 'idle')
        
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Top right frame for version and language
        top_right_frame = ttk.Frame(self.root)
        top_right_frame.place(relx=1.0, y=0, anchor='ne')
        
        # Language selector
        self.lang_label = ttk.Label(top_right_frame, text=self.tr('language_label'))
        self.lang_label.pack(side=tk.LEFT, padx=(0, 5))
        
        lang_combo = ttk.Combobox(top_right_frame, textvariable=self.current_language, 
                                  values=['EN', 'RU'], state='readonly', width=5)
        lang_combo.pack(side=tk.LEFT, padx=(0, 10))
        
        # Version label
        version_label = ttk.Label(top_right_frame, text=f"v{VERSION}", font=('Arial', 9))
        version_label.pack(side=tk.LEFT, padx=(0, 10))

        # Database selection
        top_frame = ttk.LabelFrame(main_frame, text=self.tr('select_database'), padding="10")
        top_frame.pack(fill=tk.X, pady=(0, 5))
        top_frame.columnconfigure(0, weight=1)
        
        self.db_label = ttk.Label(top_frame, text=self.tr('select_database'))
        
        db_entry_frame = ttk.Frame(top_frame)
        db_entry_frame.grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))
        ttk.Entry(db_entry_frame, textvariable=self.db_path, width=70).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.browse_btn = ttk.Button(top_frame, text=self.tr('choose_button'), command=self.browse_db)
        self.browse_btn.grid(row=0, column=1)

        # Control buttons
        control_frame = ttk.Frame(main_frame, padding=(0, 10))
        control_frame.pack(fill=tk.X)
        
        self.analyze_btn = ttk.Button(control_frame, text=self.tr('analyze_button'), 
                                      command=lambda: self.start_action(self.analyze_database))
        self.analyze_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.update_btn = ttk.Button(control_frame, text=self.tr('update_button'), 
                                     command=lambda: self.start_action(self.update_vectors), 
                                     state=tk.DISABLED)
        self.update_btn.pack(side=tk.LEFT, padx=5)
        
        self.optimize_btn = ttk.Button(control_frame, text=self.tr('optimize_button'), 
                                       command=lambda: self.start_action(self.optimize_vectors), 
                                       state=tk.DISABLED, style="Accent.TButton")
        self.optimize_btn.pack(side=tk.LEFT, padx=5)
        
        self.exit_btn = ttk.Button(control_frame, text=self.tr('exit_button'), 
                                   command=self.root.destroy)
        self.exit_btn.pack(side=tk.RIGHT)
        
        # Log frame
        self.log_frame = ttk.LabelFrame(main_frame, text=self.tr('log_title'), padding="10")
        self.log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Create a frame for the log text and copy button
        log_container = ttk.Frame(self.log_frame)
        log_container.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_container, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Copy button in the corner of log field
        self.copy_btn = ttk.Button(log_container, text="📋", width=3, command=self.copy_log_to_clipboard)
        self.copy_btn.place(relx=1.0, rely=0, x=-5, y=2, anchor="ne")

        # Status bar
        self.status_bar = ttk.Label(self.root, text="", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def browse_db(self):
        filename = filedialog.askopenfilename(
            title=self.tr('select_database'), 
            filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")]
        )
        if filename:
            self.db_path.set(filename)
            self.update_status(self.tr('log_db_selected', path=os.path.basename(filename)), "idle")
            self.update_queue.put(('toggle_buttons', ('disabled', 'disabled')))

    def log(self, message):
        self.update_queue.put(('log', f"{datetime.now().strftime('%H:%M:%S')} - {message}\n"))

    def update_status(self, message, status_type):
        self.current_status_type = status_type
        self.update_queue.put(('status', (message, status_type)))
        
    def copy_log_to_clipboard(self):
        content = self.log_text.get('1.0', tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.update_status(self.tr('log_copied'), 'idle')

    def process_queue(self):
        try:
            while True:
                action, data = self.update_queue.get_nowait()
                if action == 'log': 
                    self.log_text.insert(tk.END, data)
                    self.log_text.see(tk.END)
                elif action == 'status': 
                    self.status_bar.config(text=data[0])
                    self.status_bar.config(style=data[1].title()+'.Status.TLabel')
                elif action == 'toggle_buttons': 
                    self.update_btn.config(state=data[0])
                    self.optimize_btn.config(state=data[1])
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)

    def start_action(self, target_method):
        if self.is_running: 
            return
        if not self.db_path.get() or not os.path.exists(self.db_path.get()):
            messagebox.showerror(self.tr('error_title'), self.tr('error_no_db'))
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
        self.update_status(self.tr('status_analyzing'), "processing")
        self.log(self.tr('log_analysis_start'))
        success = False
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM persons WHERE is_known = 1")
                self.log(self.tr('log_known_people', count=cursor.fetchone()[0]))
                
                cursor.execute("SELECT COUNT(*) FROM person_detections pd JOIN persons p ON pd.person_id = p.id WHERE p.is_known = 1 AND pd.has_face = 1")
                self.log(self.tr('log_detections_with_faces', count=cursor.fetchone()[0]))
                
                cursor.execute("SELECT COUNT(*) FROM face_encodings")
                self.log(self.tr('log_total_vectors', count=cursor.fetchone()[0]))

                cursor.execute("SELECT COUNT(DISTINCT p.id) FROM persons p WHERE p.is_known = 1 AND NOT EXISTS (SELECT 1 FROM face_encodings fe WHERE fe.person_id = p.id)")
                persons_without_vectors = cursor.fetchone()[0]
                if persons_without_vectors > 0:
                    self.log(self.tr('log_people_without_vectors', count=persons_without_vectors))
                
                cursor.execute("SELECT p.full_name, COUNT(fe.id) c FROM persons p JOIN face_encodings fe ON p.id = fe.person_id WHERE p.is_known = 1 GROUP BY p.id HAVING c > 1 ORDER BY c DESC LIMIT 10")
                multi_vector_persons = cursor.fetchall()
                if multi_vector_persons:
                    self.log(self.tr('log_people_with_multiple'))
                    for name, count in multi_vector_persons: 
                        self.log(self.tr('log_person_vector_count', name=name, count=count))
                
                self.update_status(self.tr('status_analysis_complete'), "complete")
                success = True
        except Exception as e:
            error_msg = self.tr('error_analysis', error=str(e))
            self.log(error_msg)
            self.update_status(error_msg, "error")
        finally:
            self.end_action(success)

    def update_vectors(self):
        self.log(self.tr('log_update_start'))
        success = False
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT p.id, p.full_name FROM persons p WHERE p.is_known = 1 ORDER BY p.full_name")
                persons = cursor.fetchall()
                total_persons = len(persons)
                
                for idx, (person_id, person_name) in enumerate(persons):
                    self.update_status(self.tr('status_updating', idx=idx+1, total=total_persons, name=person_name), "processing")
                    
                    cursor.execute("SELECT pd.id, i.filepath FROM person_detections pd JOIN images i ON pd.image_id = i.id WHERE pd.person_id = ? AND pd.has_face = 1", (person_id,))
                    detections = cursor.fetchall()

                    if not detections:
                        self.log(self.tr('log_no_detections', name=person_name))
                        continue
                        
                    new_encodings = []
                    for detection_id, image_path in detections:
                        if not os.path.exists(image_path): 
                            continue
                        try:
                            pil_image = Image.open(image_path)
                            oriented_image = correct_image_orientation(pil_image)
                            # FIXED: Removed BGR conversion
                            image_np = np.array(oriented_image)
                            
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
                        self.log(self.tr('log_vectors_updated', name=person_name, count=len(new_encodings)))
                    else:
                        self.log(self.tr('log_no_vectors_extracted', name=person_name))
                        
                conn.commit()
                self.log(self.tr('log_update_complete'))
                self.update_status(self.tr('status_update_complete'), "complete")
                success = True
        except Exception as e:
            error_msg = self.tr('error_update', error=str(e))
            self.log(error_msg)
            self.update_status(error_msg, "error")
        finally:
            self.end_action(success)

    def optimize_vectors(self):
        self.log(self.tr('log_optimization_start'))
        success = False
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS person_average_encodings (id INTEGER PRIMARY KEY, person_id INTEGER UNIQUE, average_encoding TEXT, num_samples INTEGER, created_date TEXT, FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE)")
                
                cursor.execute("SELECT p.id, p.full_name FROM persons p JOIN face_encodings fe ON p.id = fe.person_id WHERE p.is_known = 1 GROUP BY p.id HAVING COUNT(fe.id) > 0")
                persons = cursor.fetchall()
                total_persons = len(persons)
                
                for idx, (person_id, person_name) in enumerate(persons):
                    self.update_status(self.tr('status_optimizing', idx=idx+1, total=total_persons, name=person_name), "processing")
                    cursor.execute("SELECT face_encoding FROM face_encodings WHERE person_id = ?", (person_id,))
                    
                    encodings = [np.array(json.loads(row[0])) for row in cursor.fetchall()]
                    if encodings:
                        average_encoding = np.mean(encodings, axis=0)
                        cursor.execute("INSERT OR REPLACE INTO person_average_encodings (person_id, average_encoding, num_samples, created_date) VALUES (?, ?, ?, ?)",
                                       (person_id, json.dumps(average_encoding.tolist()), len(encodings), datetime.now().isoformat()))
                        self.log(self.tr('log_average_created', name=person_name, count=len(encodings)))
                        
                conn.commit()
                self.log(self.tr('log_optimization_complete'))
                self.update_status(self.tr('status_optimization_complete'), "complete")
                success = True
        except Exception as e:
            error_msg = self.tr('error_optimization', error=str(e))
            self.log(error_msg)
            self.update_status(error_msg, "error")
        finally:
            self.end_action(success)


def main():
    root = tk.Tk()
    app = FaceVectorsUpdater(root)
    root.mainloop()

if __name__ == "__main__":
    main()