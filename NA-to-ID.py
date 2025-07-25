"""
Generate Unknown IDs v1.2.0
Program for generating unique IDs for all unknown persons and dogs
in the face recognition database

Version 1.2.0:
- Added multilingual support (EN/RU) with language selector
- Moved copy log button to icon in the log area
- English is now the default language
- All UI elements and messages support both languages
"""

import sqlite3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime
import threading
import queue
import os

VERSION = "1.2"

class UnknownIDGenerator:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Generate Unknown IDs v{VERSION}")
        self.root.geometry("1000x800")
        self.root.minsize(800, 600)

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
        self.preview_data = None
        self.is_running = False
        self.update_queue = queue.Queue()
        self.language = tk.StringVar(value='EN')

        self.create_for_persons = tk.BooleanVar(value=True)
        self.create_for_dogs = tk.BooleanVar(value=True)
        self.use_photo_info = tk.BooleanVar(value=True)

        # Language strings
        self.strings = {}
        self.init_language_strings()

        self.create_widgets()
        self.process_queue()
        self.update_status(self.strings['select_db_and_analyze'], "idle")

    def init_language_strings(self):
        # Define all UI strings for both languages
        self.all_strings = {
            'EN': {
                # UI elements
                'database': 'Database',
                'browse': 'Browse...',
                'analyze_db': 'Analyze DB',
                'preview_changes': 'Preview Changes',
                'apply_changes': 'Apply Changes',
                'exit': 'Exit',
                'options': 'Options',
                'create_for_persons': 'Create IDs for unknown persons',
                'create_for_dogs': 'Create IDs for unknown dogs',
                'use_photo_info': 'Add photo information to notes',
                'log_operations': 'Operation Log',
                'preview_persons': 'Preview - Persons',
                'preview_dogs': 'Preview - Dogs',
                
                # Status messages
                'select_db_and_analyze': 'Select database and click "Analyze"',
                'db_selected': 'Selected database: {}',
                'log_copied': 'Log copied to clipboard.',
                'analyzing_db': 'Analyzing database...',
                'analysis_title': '=== Database Analysis ===',
                'persons_without_id': 'Person detections without ID: {}',
                'dogs_without_id': 'Dog detections without ID: {}',
                'found_info': 'Found: {} person detections without ID',
                'found_info_with_dogs': ', {} dog detections without ID',
                'no_records': '\nNo records to process!',
                'analysis_complete': 'Analysis complete. You can preview changes.',
                'analysis_complete_no_records': 'Analysis complete. No records to process.',
                'analysis_error': 'Analysis error: {}',
                'creating_preview': 'Creating preview...',
                'preview_title': '\n=== Preview Changes ===',
                'preview_ready': 'Preview ready. You can apply changes.',
                'no_changes_preview': 'No changes to preview.',
                'preview_error': 'Preview error: {}',
                'will_create_ids': 'Will create IDs: {} for persons, {} for dogs.',
                'applying_changes': 'Applying changes...',
                'apply_title': '\n=== Applying Changes ===',
                'created_persons': '✓ Created IDs for persons: {}',
                'created_dogs': '✓ Created IDs for dogs: {}',
                'changes_applied': '\n✅ All changes successfully applied!',
                'changes_applied_status': 'Changes successfully applied!',
                'apply_error': '❌ Error applying changes: {}',
                'apply_error_status': 'Apply error: {}',
                
                # Dialog messages
                'error': 'Error',
                'select_db_error': 'Select database',
                'preview_first_error': 'Perform preview first',
                'confirmation': 'Confirmation',
                'apply_confirmation': 'Apply changes?\n\nCreate {} IDs for persons and {} IDs for dogs?',
                'success': 'Success',
                'success_message': 'Successfully created {} IDs for persons and {} IDs for dogs.',
                
                # Table columns
                'photo_id': 'Photo ID',
                'file': 'File',
                'index': 'Index',
                'new_id': 'New ID',
                'note': 'Note',
                
                # Other
                'with_face': 'With face',
                'without_face': 'Without face',
                'new': 'New',
                'unknown': 'Unknown',
                'auto_note': 'Auto: {}. Photo: {}, Index: {}'
            },
            'RU': {
                # UI elements
                'database': 'База данных',
                'browse': 'Выбрать...',
                'analyze_db': 'Анализировать БД',
                'preview_changes': 'Предпросмотр изменений',
                'apply_changes': 'Применить изменения',
                'exit': 'Выход',
                'options': 'Опции',
                'create_for_persons': 'Создать ID для неизвестных людей',
                'create_for_dogs': 'Создать ID для неизвестных собак',
                'use_photo_info': 'Добавить информацию о фото в примечания',
                'log_operations': 'Лог операций',
                'preview_persons': 'Предпросмотр - Люди',
                'preview_dogs': 'Предпросмотр - Собаки',
                
                # Status messages
                'select_db_and_analyze': 'Выберите базу данных и нажмите "Анализировать"',
                'db_selected': 'Выбрана база: {}',
                'log_copied': 'Лог скопирован в буфер обмена.',
                'analyzing_db': 'Анализ базы данных...',
                'analysis_title': '=== Анализ базы данных ===',
                'persons_without_id': 'Детекций людей без ID: {}',
                'dogs_without_id': 'Детекций собак без ID: {}',
                'found_info': 'Найдено: {} детекций людей без ID',
                'found_info_with_dogs': ', {} детекций собак без ID',
                'no_records': '\nНет записей для обработки!',
                'analysis_complete': 'Анализ завершен. Можно выполнить предпросмотр.',
                'analysis_complete_no_records': 'Анализ завершен. Нет записей для обработки.',
                'analysis_error': 'Ошибка анализа: {}',
                'creating_preview': 'Создание предпросмотра...',
                'preview_title': '\n=== Предпросмотр изменений ===',
                'preview_ready': 'Предпросмотр готов. Можно применить изменения.',
                'no_changes_preview': 'Нет изменений для предпросмотра.',
                'preview_error': 'Ошибка предпросмотра: {}',
                'will_create_ids': 'Будет создано ID: {} для людей, {} для собак.',
                'applying_changes': 'Применение изменений...',
                'apply_title': '\n=== Применение изменений ===',
                'created_persons': '✓ Создано ID для людей: {}',
                'created_dogs': '✓ Создано ID для собак: {}',
                'changes_applied': '\n✅ Все изменения успешно применены!',
                'changes_applied_status': 'Изменения успешно применены!',
                'apply_error': '❌ Ошибка при применении изменений: {}',
                'apply_error_status': 'Ошибка применения: {}',
                
                # Dialog messages
                'error': 'Ошибка',
                'select_db_error': 'Выберите базу данных',
                'preview_first_error': 'Сначала выполните предпросмотр',
                'confirmation': 'Подтверждение',
                'apply_confirmation': 'Применить изменения?\n\nСоздать {} ID для людей и {} ID для собак?',
                'success': 'Успех',
                'success_message': 'Успешно создано {} ID для людей и {} ID для собак.',
                
                # Table columns
                'photo_id': 'ID фото',
                'file': 'Файл',
                'index': 'Индекс',
                'new_id': 'Новый ID',
                'note': 'Примечание',
                
                # Other
                'with_face': 'С лицом',
                'without_face': 'Без лица',
                'new': 'Новый',
                'unknown': 'Неизвестная',
                'auto_note': 'Авто: {}. Фото: {}, Индекс: {}'
            }
        }
        self.strings = self.all_strings[self.language.get()]

    def update_ui_language(self):
        # Update strings dictionary
        self.strings = self.all_strings[self.language.get()]
        
        # Update all UI elements
        self.analyze_btn.config(text=self.strings['analyze_db'])
        self.preview_btn.config(text=self.strings['preview_changes'])
        self.apply_btn.config(text=self.strings['apply_changes'])
        
        # Update labelframes
        for widget in self.root.winfo_children():
            self.update_widget_texts(widget)
        
        # Update notebook tabs
        self.notebook.tab(0, text=self.strings['log_operations'])
        self.notebook.tab(1, text=self.strings['preview_persons'])
        self.notebook.tab(2, text=self.strings['preview_dogs'])
        
        # Update tree columns
        for tree in [self.persons_tree, self.dogs_tree]:
            tree.heading('#1', text=self.strings['photo_id'])
            tree.heading('#2', text=self.strings['file'])
            tree.heading('#3', text=self.strings['index'])
            tree.heading('#4', text=self.strings['new_id'])
            tree.heading('#5', text=self.strings['note'])

    def update_widget_texts(self, widget):
        # Recursively update text for all widgets
        if isinstance(widget, ttk.LabelFrame):
            if widget.winfo_parent().endswith('!frame2'):  # Top panel
                widget.config(text=self.strings['database'])
            elif widget.winfo_parent().endswith('!frame3'):  # Options
                widget.config(text=self.strings['options'])
        elif isinstance(widget, ttk.Button):
            if widget['text'] == 'Выбрать...' or widget['text'] == 'Browse...':
                widget.config(text=self.strings['browse'])
            elif widget['text'] == 'Выход' or widget['text'] == 'Exit':
                widget.config(text=self.strings['exit'])
        elif isinstance(widget, ttk.Checkbutton):
            if widget == self.cb_persons:
                widget.config(text=self.strings['create_for_persons'])
            elif widget == self.cb_dogs:
                widget.config(text=self.strings['create_for_dogs'])
            elif widget == self.cb_photo:
                widget.config(text=self.strings['use_photo_info'])
        
        # Process children
        for child in widget.winfo_children():
            self.update_widget_texts(child)

    def create_widgets(self):
        # --- Header with language selector and version ---
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill=tk.X, padx=10, pady=(5, 0))

        # Both elements on the right side
        right_frame = ttk.Frame(header_frame)
        right_frame.pack(side=tk.RIGHT)

        # Language selector
        ttk.Label(right_frame, text="Language:").pack(side=tk.LEFT, padx=(0, 5))
        lang_combo = ttk.Combobox(right_frame, textvariable=self.language, values=['EN', 'RU'], width=5, state='readonly')
        lang_combo.pack(side=tk.LEFT, padx=(0, 10))
        lang_combo.bind('<<ComboboxSelected>>', lambda e: self.update_ui_language())

        # Version
        ttk.Label(right_frame, text=f"Version {VERSION}", font=('Arial', 10)).pack(side=tk.LEFT)

        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Top panel ---
        top_frame = ttk.LabelFrame(main_frame, text=self.strings['database'], padding="10")
        top_frame.pack(fill=tk.X, pady=(0, 5))
        top_frame.columnconfigure(0, weight=1)
        
        db_entry_frame = ttk.Frame(top_frame)
        db_entry_frame.grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))
        ttk.Entry(db_entry_frame, textvariable=self.db_path, width=70).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(top_frame, text=self.strings['browse'], command=self.browse_db).grid(row=0, column=1)

        # --- Control panel ---
        control_frame = ttk.Frame(main_frame, padding=(0, 10))
        control_frame.pack(fill=tk.X)
        self.analyze_btn = ttk.Button(control_frame, text=self.strings['analyze_db'], command=lambda: self.start_action(self.analyze_database))
        self.analyze_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.preview_btn = ttk.Button(control_frame, text=self.strings['preview_changes'], command=lambda: self.start_action(self.preview_changes), state=tk.DISABLED)
        self.preview_btn.pack(side=tk.LEFT, padx=5)
        self.apply_btn = ttk.Button(control_frame, text=self.strings['apply_changes'], command=lambda: self.start_action(self.apply_changes), state=tk.DISABLED, style="Accent.TButton")
        self.apply_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text=self.strings['exit'], command=self.root.destroy).pack(side=tk.RIGHT)

        # --- Options ---
        options_frame = ttk.LabelFrame(main_frame, text=self.strings['options'], padding="10")
        options_frame.pack(fill=tk.X, pady=5)
        self.cb_persons = ttk.Checkbutton(options_frame, text=self.strings['create_for_persons'], variable=self.create_for_persons)
        self.cb_persons.pack(anchor=tk.W)
        self.cb_dogs = ttk.Checkbutton(options_frame, text=self.strings['create_for_dogs'], variable=self.create_for_dogs)
        self.cb_dogs.pack(anchor=tk.W)
        self.cb_photo = ttk.Checkbutton(options_frame, text=self.strings['use_photo_info'], variable=self.use_photo_info)
        self.cb_photo.pack(anchor=tk.W)

        # --- Notebook for results ---
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Log tab with copy button
        log_frame = ttk.Frame(self.notebook)
        self.notebook.add(log_frame, text=self.strings['log_operations'])
        
        # Frame for log with copy button
        log_container = ttk.Frame(log_frame)
        log_container.pack(fill=tk.BOTH, expand=True)
        
        # Copy button in top-right corner of log
        copy_btn = ttk.Button(log_container, text="📋", command=self.copy_log_to_clipboard, width=3)
        copy_btn.place(relx=1.0, x=-5, y=1, anchor='ne')

        self.log_text = scrolledtext.ScrolledText(log_container, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(35, 0))
        
        self.info_label = ttk.Label(log_frame, text="", font=('Arial', 10, 'bold'), padding=5)
        self.info_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Preview tabs
        self.persons_tree = self.create_preview_tab(self.strings['preview_persons'])
        self.dogs_tree = self.create_preview_tab(self.strings['preview_dogs'])

        # --- Status bar ---
        self.status_bar = ttk.Label(self.root, text="", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    def create_preview_tab(self, title):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=title)
        columns = (self.strings['photo_id'], self.strings['file'], self.strings['index'], 
                  self.strings['new_id'], self.strings['note'])
        tree = ttk.Treeview(frame, columns=columns, show='headings')
        for i, col in enumerate(columns):
            tree.heading(f'#{i+1}', text=col)
            if col == self.strings['file']:
                tree.column(f'#{i+1}', width=300)
            elif col == self.strings['note']:
                tree.column(f'#{i+1}', width=250)
            else:
                tree.column(f'#{i+1}', width=80)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        return tree

    def browse_db(self):
        filename = filedialog.askopenfilename(
            title=self.strings['database'], 
            filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")]
        )
        if filename:
            self.db_path.set(filename)
            self.update_status(self.strings['db_selected'].format(os.path.basename(filename)), "idle")
            self.update_queue.put(('toggle_buttons', ('disabled', 'disabled')))
            self.preview_data = None
            
    def copy_log_to_clipboard(self):
        content = self.log_text.get('1.0', tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.update_status(self.strings['log_copied'], 'idle')

    def log(self, message):
        self.update_queue.put(('log', f"{datetime.now().strftime('%H:%M:%S')} - {message}\n"))

    def update_status(self, message, status_type):
        self.update_queue.put(('status', (message, status_type)))

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
                    self.preview_btn.config(state=data[0])
                    self.apply_btn.config(state=data[1])
                elif action == 'update_info_label': 
                    self.info_label.config(text=data)
                elif action == 'clear_trees':
                    for item in self.persons_tree.get_children(): 
                        self.persons_tree.delete(item)
                    for item in self.dogs_tree.get_children(): 
                        self.dogs_tree.delete(item)
                elif action == 'insert_person': 
                    self.persons_tree.insert('', tk.END, values=data)
                elif action == 'insert_dog': 
                    self.dogs_tree.insert('', tk.END, values=data)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)

    def start_action(self, target_method):
        if self.is_running: 
            return
        if not self.db_path.get(): 
            messagebox.showerror(self.strings['error'], self.strings['select_db_error'])
            return
        
        self.is_running = True
        self.analyze_btn.config(state=tk.DISABLED)
        self.preview_btn.config(state=tk.DISABLED)
        self.apply_btn.config(state=tk.DISABLED)
        thread = threading.Thread(target=target_method, daemon=True)
        thread.start()

    def end_action(self):
        self.is_running = False
        self.analyze_btn.config(state=tk.NORMAL)
        # State of other buttons will be set by method logic
        if self.preview_data:
             self.update_queue.put(('toggle_buttons', ('normal', 'normal')))
        elif hasattr(self, 'analysis_result') and self.analysis_result:
             self.update_queue.put(('toggle_buttons', ('normal', 'disabled')))

    def analyze_database(self):
        self.update_status(self.strings['analyzing_db'], "processing")
        self.log(self.strings['analysis_title'])
        self.analysis_result = False
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('persons', 'person_detections', 'dogs', 'dog_detections')")
                tables = [row[0] for row in cursor.fetchall()]
                has_dogs = 'dogs' in tables and 'dog_detections' in tables

                cursor.execute("SELECT COUNT(*) FROM person_detections WHERE person_id IS NULL")
                persons_without_id = cursor.fetchone()[0]
                self.log(self.strings['persons_without_id'].format(persons_without_id))

                dogs_without_id = 0
                if has_dogs:
                    cursor.execute("SELECT COUNT(*) FROM dog_detections WHERE dog_id IS NULL")
                    dogs_without_id = cursor.fetchone()[0]
                    self.log(self.strings['dogs_without_id'].format(dogs_without_id))
                
                info_text = self.strings['found_info'].format(persons_without_id)
                if has_dogs: 
                    info_text += self.strings['found_info_with_dogs'].format(dogs_without_id)
                self.update_queue.put(('update_info_label', info_text))

                if persons_without_id > 0 or dogs_without_id > 0:
                    self.analysis_result = True
                    self.update_status(self.strings['analysis_complete'], "complete")
                else:
                    self.log(self.strings['no_records'])
                    self.update_status(self.strings['analysis_complete_no_records'], "complete")
        except Exception as e:
            self.log(self.strings['analysis_error'].format(e))
            self.update_status(self.strings['analysis_error'].format(e), "error")
        finally:
            self.end_action()
            
    def preview_changes(self):
        self.update_status(self.strings['creating_preview'], "processing")
        self.log(self.strings['preview_title'])
        self.update_queue.put(('clear_trees', None))
        
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                self.preview_data = {'persons': [], 'dogs': []}
                
                if self.create_for_persons.get():
                    cursor.execute("""
                        SELECT pd.id, pd.image_id, i.filename, i.filepath, pd.person_index, 
                               pd.has_face, i.created_date 
                        FROM person_detections pd 
                        JOIN images i ON pd.image_id = i.id 
                        WHERE pd.person_id IS NULL 
                        ORDER BY i.id, pd.person_index
                    """)
                    for row in cursor.fetchall():
                        det_id, img_id, fname, fpath, p_idx, has_face, c_date = row
                        notes = self.strings['auto_note'].format(
                            datetime.now().strftime('%Y-%m-%d %H:%M'), fname, p_idx
                        ) if self.use_photo_info.get() else ""
                        self.preview_data['persons'].append({'detection_id': det_id, 'notes': notes})
                        face_text = self.strings['with_face'] if has_face else self.strings['without_face']
                        self.update_queue.put(('insert_person', (img_id, fname, p_idx, self.strings['new'], face_text)))

                if self.create_for_dogs.get():
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dog_detections'")
                    if cursor.fetchone():
                        cursor.execute("""
                            SELECT dd.id, dd.image_id, i.filename, i.filepath, dd.dog_index, 
                                   i.created_date 
                            FROM dog_detections dd 
                            JOIN images i ON dd.image_id = i.id 
                            WHERE dd.dog_id IS NULL 
                            ORDER BY i.id, dd.dog_index
                        """)
                        for row in cursor.fetchall():
                            det_id, img_id, fname, fpath, d_idx, c_date = row
                            notes = self.strings['auto_note'].format(
                                datetime.now().strftime('%Y-%m-%d %H:%M'), fname, d_idx
                            ) if self.use_photo_info.get() else ""
                            self.preview_data['dogs'].append({'detection_id': det_id, 'notes': notes})
                            self.update_queue.put(('insert_dog', (img_id, fname, d_idx, self.strings['new'], self.strings['unknown'])))
                
                self.log(self.strings['will_create_ids'].format(
                    len(self.preview_data['persons']), len(self.preview_data['dogs'])
                ))
                if self.preview_data['persons'] or self.preview_data['dogs']:
                    self.update_status(self.strings['preview_ready'], "complete")
                else:
                    self.update_status(self.strings['no_changes_preview'], "complete")
        except Exception as e:
            self.log(self.strings['preview_error'].format(e))
            self.update_status(self.strings['preview_error'].format(e), "error")
        finally:
            self.end_action()

    def apply_changes(self):
        if not self.preview_data:
            messagebox.showerror(self.strings['error'], self.strings['preview_first_error'])
            return
        
        count_p = len(self.preview_data['persons'])
        count_d = len(self.preview_data['dogs'])
        if not messagebox.askyesno(
            self.strings['confirmation'], 
            self.strings['apply_confirmation'].format(count_p, count_d)
        ):
            return

        self.update_status(self.strings['applying_changes'], "processing")
        self.log(self.strings['apply_title'])
        
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN TRANSACTION")
                try:
                    now_iso = datetime.now().isoformat()
                    # Persons
                    for p_data in self.preview_data['persons']:
                        cursor.execute(
                            "INSERT INTO persons (is_known, notes, created_date, updated_date) VALUES (0, ?, ?, ?)", 
                            (p_data['notes'], now_iso, now_iso)
                        )
                        cursor.execute(
                            "UPDATE person_detections SET person_id = ? WHERE id = ?", 
                            (cursor.lastrowid, p_data['detection_id'])
                        )
                    self.log(self.strings['created_persons'].format(count_p))
                    # Dogs
                    for d_data in self.preview_data['dogs']:
                        cursor.execute(
                            "INSERT INTO dogs (is_known, notes, created_date, updated_date) VALUES (0, ?, ?, ?)", 
                            (d_data['notes'], now_iso, now_iso)
                        )
                        cursor.execute(
                            "UPDATE dog_detections SET dog_id = ? WHERE id = ?", 
                            (cursor.lastrowid, d_data['detection_id'])
                        )
                    self.log(self.strings['created_dogs'].format(count_d))
                    conn.commit()
                    self.log(self.strings['changes_applied'])
                    self.update_status(self.strings['changes_applied_status'], "complete")
                    messagebox.showinfo(
                        self.strings['success'], 
                        self.strings['success_message'].format(count_p, count_d)
                    )
                except Exception as e:
                    conn.rollback()
                    raise e
            
            self.preview_data = None
            self.update_queue.put(('toggle_buttons', ('disabled', 'disabled')))
            self.start_action(self.analyze_database)  # Re-analyze
        except Exception as e:
            self.log(self.strings['apply_error'].format(e))
            self.update_status(self.strings['apply_error_status'].format(e), "error")
            messagebox.showerror(self.strings['error'], self.strings['apply_error'].format(e))
        finally:
            # end_action will be called from re-analysis
            pass

def main():
    root = tk.Tk()
    app = UnknownIDGenerator(root)
    root.mainloop()

if __name__ == "__main__":
    main()