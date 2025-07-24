# Face Database Viewer v1.7.7
# A program for viewing a database of recognized faces and dogs.
#
# Version: 1.7.7
# - Corrected the SQL query in the "Edit Person/Dog" dialogs.
#   The "Select from DB" list now correctly displays only known entities (where is_known = 1),
#   hiding entries with "None" as their name.
#
# Version: 1.7.6
# - Implemented unsaved changes confirmation for the AI Descriptions tab.
#
# Version: 1.7.5
# - Corrected a layout issue hiding the "Edit" and "Delete" buttons.
# - Redesigned the "AI Descriptions" tab with separate fields and an Edit/Save button.

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sqlite3
from datetime import datetime
from PIL import Image, ImageTk, ImageDraw, ImageFont, ExifTags
import json

# Program Version
VERSION = "1.7.7"

def correct_image_orientation(image: Image.Image) -> Image.Image:
    """Applies rotation to a PIL image based on its EXIF data."""
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
    """Dialog for editing information about a person."""
    def __init__(self, parent, viewer, detection_id, current_person_id=None):
        super().__init__(parent)
        self.viewer = viewer
        self.detection_id = detection_id
        self.current_person_id = current_person_id
        self.result = None
        self.i18n = viewer.i18n
        self.lang = viewer.lang.get()

        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        existing_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(existing_frame, text=self.i18n[self.lang]['select_from_db'])
        columns = ('id', 'full_name', 'short_name', 'status')
        self.person_tree = ttk.Treeview(existing_frame, columns=columns, show='headings', height=12)

        tree_scroll = ttk.Scrollbar(existing_frame, orient="vertical", command=self.person_tree.yview)
        self.person_tree.configure(yscrollcommand=tree_scroll.set)
        self.load_persons()
        self.person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        new_person_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(new_person_frame, text=self.i18n[self.lang]['create_new'])
        new_person_frame.columnconfigure(1, weight=1)

        self.full_name_label = ttk.Label(new_person_frame)
        self.full_name_label.grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.full_name_var = tk.StringVar()
        ttk.Entry(new_person_frame, textvariable=self.full_name_var).grid(row=0, column=1, sticky=tk.EW)
        self.short_name_label = ttk.Label(new_person_frame)
        self.short_name_label.grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.short_name_var = tk.StringVar()
        ttk.Entry(new_person_frame, textvariable=self.short_name_var).grid(row=1, column=1, sticky=tk.EW)
        self.notes_label = ttk.Label(new_person_frame)
        self.notes_label.grid(row=2, column=0, sticky=tk.NW, padx=5, pady=5)
        self.notes_text = tk.Text(new_person_frame, height=4, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.notes_text.grid(row=2, column=1, sticky=tk.NSEW)
        new_person_frame.rowconfigure(2, weight=1)

        local_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(local_frame, text=self.i18n[self.lang]['local_id'])
        local_frame.columnconfigure(1, weight=1)
        self.local_id_label_info = ttk.Label(local_frame, wraplength=500, justify=tk.CENTER)
        self.local_id_label_info.grid(row=0, column=0, columnspan=2, pady=10)
        self.local_full_name_label = ttk.Label(local_frame)
        self.local_full_name_label.grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.local_full_name_var = tk.StringVar()
        ttk.Entry(local_frame, textvariable=self.local_full_name_var).grid(row=1, column=1, sticky=tk.EW)
        self.local_short_name_label = ttk.Label(local_frame)
        self.local_short_name_label.grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.local_short_name_var = tk.StringVar()
        ttk.Entry(local_frame, textvariable=self.local_short_name_var).grid(row=2, column=1, sticky=tk.EW)
        self.local_notes_label = ttk.Label(local_frame)
        self.local_notes_label.grid(row=3, column=0, sticky=tk.NW, padx=5, pady=5)
        self.local_notes_text = tk.Text(local_frame, height=3, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.local_notes_text.grid(row=3, column=1, sticky=tk.NSEW)
        local_frame.rowconfigure(3, weight=1)

        button_frame = ttk.Frame(self, padding=(10, 5))
        button_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.apply_btn = ttk.Button(button_frame, command=self.apply_changes, style="Accent.TButton")
        self.apply_btn.pack(side=tk.LEFT, padx=5)
        self.reset_btn = ttk.Button(button_frame, command=self.remove_link)
        self.reset_btn.pack(side=tk.LEFT, padx=5)
        self.cancel_btn = ttk.Button(button_frame, command=self.cancel)
        self.cancel_btn.pack(side=tk.RIGHT, padx=5)

        self.update_ui_language()
        self.load_current_data()
        self.center_window()

    def update_ui_language(self):
        """Updates all UI element texts to the current language."""
        lang_dict = self.i18n[self.lang]
        self.title(lang_dict['edit_person_dialog_title'])
        self.notebook.tab(0, text=lang_dict['select_from_db'])
        self.notebook.tab(1, text=lang_dict['create_new'])
        self.notebook.tab(2, text=lang_dict['local_id'])
        self.person_tree.heading('id', text=lang_dict['col_id']); self.person_tree.heading('full_name', text=lang_dict['col_full_name'])
        self.person_tree.heading('short_name', text=lang_dict['col_short_name']); self.person_tree.heading('status', text=lang_dict['col_status'])
        self.person_tree.column('id', width=50, anchor='center'); self.person_tree.column('full_name', width=120, anchor='w')
        self.person_tree.column('short_name', width=120, anchor='w'); self.person_tree.column('status', width=120, anchor='w')
        self.full_name_label.config(text=lang_dict['col_full_name'] + ":"); self.short_name_label.config(text=lang_dict['col_short_name'] + ":")
        self.notes_label.config(text=lang_dict['col_notes'] + ":"); self.local_id_label_info.config(text=lang_dict['local_id_info'])
        self.local_full_name_label.config(text=lang_dict['col_full_name'] + ":"); self.local_short_name_label.config(text=lang_dict['col_short_name'] + ":")
        self.local_notes_label.config(text=lang_dict['col_notes'] + ":"); self.apply_btn.config(text=lang_dict['apply_btn'])
        self.reset_btn.config(text=lang_dict['reset_link_btn']); self.cancel_btn.config(text=lang_dict['cancel_btn'])

    def center_window(self):
        self.update_idletasks()
        x, y = (self.winfo_screenwidth()//2)-(self.winfo_width()//2), (self.winfo_screenheight()//2)-(self.winfo_height()//2)
        self.geometry(f'+{x}+{y-50}')

    def load_persons(self):
        known_status = self.i18n[self.lang]['status_known']
        with sqlite3.connect(self.viewer.db_path.get()) as conn:
            # Query only for KNOWN persons to populate the selection list
            query = f"SELECT id, full_name, short_name, '{known_status}' FROM persons WHERE is_known = 1 ORDER BY full_name"
            for row in conn.execute(query):
                self.person_tree.insert('', tk.END, values=row)
                if self.current_person_id and row[0] == self.current_person_id:
                    last_item = self.person_tree.get_children()[-1]
                    self.person_tree.selection_set(last_item); self.person_tree.see(last_item)

    def load_current_data(self):
        with sqlite3.connect(self.viewer.db_path.get()) as conn:
            row = conn.execute("SELECT is_locally_identified, local_full_name, local_short_name, local_notes FROM person_detections WHERE id = ?", (self.detection_id,)).fetchone()
            if row and row[0]:
                self.local_full_name_var.set(row[1] or ''); self.local_short_name_var.set(row[2] or '')
                self.local_notes_text.insert('1.0', row[3] or ''); self.notebook.select(2)

    def apply_changes(self):
        current_tab, ld = self.notebook.index(self.notebook.select()), self.i18n[self.lang]
        if current_tab == 0:
            selection = self.person_tree.selection()
            if not selection: messagebox.showwarning(ld['warning'], ld['warn_select_person'], parent=self); return
            self.result = {'action': 'existing', 'person_id': self.person_tree.item(selection[0])['values'][0]}
        elif current_tab == 1:
            full_name = self.full_name_var.get().strip()
            if not full_name: messagebox.showwarning(ld['warning'], ld['warn_enter_fullname'], parent=self); return
            self.result = {'action': 'new', 'full_name': full_name, 'short_name': self.short_name_var.get().strip() or full_name.split()[0], 'notes': self.notes_text.get('1.0', tk.END).strip()}
        elif current_tab == 2:
            full_name = self.local_full_name_var.get().strip()
            if not full_name: messagebox.showwarning(ld['warning'], ld['warn_enter_fullname_local'], parent=self); return
            self.result = {'action': 'local', 'local_full_name': full_name, 'local_short_name': self.local_short_name_var.get().strip() or full_name.split()[0], 'local_notes': self.local_notes_text.get('1.0', tk.END).strip()}
        self.destroy()

    def remove_link(self):
        if messagebox.askyesno(self.i18n[self.lang]['confirm'], self.i18n[self.lang]['confirm_remove_person_link'], parent=self):
            self.result = {'action': 'remove'}; self.destroy()

    def cancel(self): self.result = None; self.destroy()


class EditDogDialog(tk.Toplevel):
    """Dialog for editing information about a dog."""
    def __init__(self, parent, viewer, detection_id, current_dog_id=None):
        super().__init__(parent)
        self.viewer, self.detection_id, self.current_dog_id, self.result = viewer, detection_id, current_dog_id, None
        self.i18n, self.lang = viewer.i18n, viewer.lang.get()
        self.resizable(True, True); self.transient(parent); self.grab_set()
        main_frame = ttk.Frame(self, padding=10); main_frame.pack(fill=tk.BOTH, expand=True)
        self.notebook = ttk.Notebook(main_frame); self.notebook.pack(fill=tk.BOTH, expand=True)
        existing_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(existing_frame, text=self.i18n[self.lang]['select_from_db'])
        columns = ('id', 'name', 'breed', 'owner', 'status')
        self.dog_tree = ttk.Treeview(existing_frame, columns=columns, show='headings', height=10)
        tree_scroll = ttk.Scrollbar(existing_frame, orient="vertical", command=self.dog_tree.yview)
        self.dog_tree.configure(yscrollcommand=tree_scroll.set); self.load_dogs()
        self.dog_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        new_dog_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(new_dog_frame, text=self.i18n[self.lang]['create_new'])
        new_dog_frame.columnconfigure(1, weight=1); self.name_label = ttk.Label(new_dog_frame)
        self.name_label.grid(row=0, column=0, sticky=tk.W, padx=5, pady=5); self.name_var = tk.StringVar()
        ttk.Entry(new_dog_frame, textvariable=self.name_var).grid(row=0, column=1, sticky=tk.EW)
        self.breed_label = ttk.Label(new_dog_frame); self.breed_label.grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.breed_var = tk.StringVar(); ttk.Entry(new_dog_frame, textvariable=self.breed_var).grid(row=1, column=1, sticky=tk.EW)
        self.owner_label = ttk.Label(new_dog_frame); self.owner_label.grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.owner_var = tk.StringVar(); ttk.Entry(new_dog_frame, textvariable=self.owner_var).grid(row=2, column=1, sticky=tk.EW)
        self.notes_label = ttk.Label(new_dog_frame); self.notes_label.grid(row=3, column=0, sticky=tk.NW, padx=5, pady=5)
        self.notes_text = tk.Text(new_dog_frame, height=3, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.notes_text.grid(row=3, column=1, sticky=tk.NSEW); new_dog_frame.rowconfigure(3, weight=1)
        button_frame = ttk.Frame(self, padding=(10,5)); button_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.apply_btn = ttk.Button(button_frame, command=self.apply_changes, style="Accent.TButton"); self.apply_btn.pack(side=tk.LEFT, padx=5)
        self.reset_btn = ttk.Button(button_frame, command=self.remove_link); self.reset_btn.pack(side=tk.LEFT, padx=5)
        self.cancel_btn = ttk.Button(button_frame, command=self.cancel); self.cancel_btn.pack(side=tk.RIGHT, padx=5)
        self.update_ui_language(); self.center_window()

    def update_ui_language(self):
        lang_dict = self.i18n[self.lang]; self.title(lang_dict['edit_dog_dialog_title']); self.geometry("600x450")
        self.notebook.tab(0, text=lang_dict['select_from_db']); self.notebook.tab(1, text=lang_dict['create_new'])
        self.dog_tree.heading('id', text=lang_dict['col_id']); self.dog_tree.heading('name', text=lang_dict['col_dog_name'])
        self.dog_tree.heading('breed', text=lang_dict['col_breed']); self.dog_tree.heading('owner', text=lang_dict['col_owner'])
        self.dog_tree.heading('status', text=lang_dict['col_status'])
        for col, w in [('id',50),('name',100),('breed',100),('owner',100),('status',100)]: self.dog_tree.column(col, width=w, anchor='center')
        for col in ['name','breed','owner']: self.dog_tree.column(col, anchor='w')
        self.name_label.config(text=lang_dict['col_dog_name']+":"); self.breed_label.config(text=lang_dict['col_breed']+":")
        self.owner_label.config(text=lang_dict['col_owner']+":"); self.notes_label.config(text=lang_dict['col_notes']+":")
        self.apply_btn.config(text=lang_dict['apply_btn']); self.reset_btn.config(text=lang_dict['reset_link_btn'])
        self.cancel_btn.config(text=lang_dict['cancel_btn'])

    def center_window(self):
        self.update_idletasks()
        x, y = (self.winfo_screenwidth()//2)-(self.winfo_width()//2), (self.winfo_screenheight()//2)-(self.winfo_height()//2)
        self.geometry(f'+{x}+{y-50}')

    def load_dogs(self):
        known_status = self.i18n[self.lang]['status_known_fem']
        with sqlite3.connect(self.viewer.db_path.get()) as conn:
            # Query only for KNOWN dogs to populate the selection list
            query = f"SELECT id, name, breed, owner, '{known_status}' FROM dogs WHERE is_known = 1 ORDER BY name"
            for row in conn.execute(query):
                self.dog_tree.insert('', tk.END, values=row)
                if self.current_dog_id and row[0] == self.current_dog_id:
                    last_item = self.dog_tree.get_children()[-1]
                    self.dog_tree.selection_set(last_item); self.dog_tree.see(last_item)

    def apply_changes(self):
        current_tab, lang_dict = self.notebook.index(self.notebook.select()), self.i18n[self.lang]
        if current_tab == 0:
            selection = self.dog_tree.selection()
            if not selection: messagebox.showwarning(lang_dict['warning'], lang_dict['warn_select_dog'], parent=self); return
            self.result = {'action': 'existing', 'dog_id': self.dog_tree.item(selection[0])['values'][0]}
        elif current_tab == 1:
            name = self.name_var.get().strip()
            if not name: messagebox.showwarning(lang_dict['warning'], lang_dict['warn_enter_dog_name'], parent=self); return
            self.result = {'action': 'new', 'name': name, 'breed': self.breed_var.get().strip(), 'owner': self.owner_var.get().strip(), 'notes': self.notes_text.get('1.0', tk.END).strip()}
        self.destroy()

    def remove_link(self):
        if messagebox.askyesno(self.i18n[self.lang]['confirm'], self.i18n[self.lang]['confirm_remove_dog_link'], parent=self):
            self.result = {'action': 'remove'}; self.destroy()

    def cancel(self): self.result = None; self.destroy()

class FaceDBViewer:
    def __init__(self, root):
        self.root = root; self.root.geometry("1500x950")
        self.style = ttk.Style(self.root)
        try: self.style.theme_use('clam')
        except tk.TclError: pass
        self.style.configure('TLabelFrame.Label', font=('Arial', 10, 'bold'))
        self.style.configure('TNotebook.Tab', font=('Arial', 11, 'bold'), padding=[10, 5])
        self.style.configure('Status.TLabel', font=('Arial', 10, 'bold'), padding=5)
        self.style.configure('Idle.Status.TLabel', background='lightblue', foreground='black')
        self.style.configure('Processing.Status.TLabel', background='lightyellow', foreground='black')
        self.style.configure('Complete.Status.TLabel', background='lightgreen', foreground='black')
        self.style.configure('Error.Status.TLabel', background='lightcoral', foreground='black')
        self.style.configure('Accent.TButton', font=('Arial', 10, 'bold'), foreground='navy')
        self.db_path = tk.StringVar(); self.current_image_id = None; self.search_name = tk.StringVar()
        self.search_date_from = tk.StringVar(); self.search_date_to = tk.StringVar()
        self.highlighted_person_detection_id = None; self.highlighted_dog_detection_id = None
        self.has_dogs = False; self.has_ai_descriptions = False
        self.lang = tk.StringVar(value='EN')
        self.previous_selection_iid = None; self.active_tab_frame = None
        self.ai_edit_mode = False; self.ai_original_short = ""; self.ai_original_long = ""
        self.setup_i18n()
        self.create_widgets()
        self.update_ui_language()
        self.update_status("status_select_db", 'idle')

    def setup_i18n(self):
        self.i18n = {
            'EN': {
                'title': f"Face Database Viewer v{VERSION}", 'db_label': "Database:", 'browse_btn': "Browse...", 'open_btn': "📂 Open",
                'search_frame': "Search", 'name_dog_label': "Name/Nickname:", 'name_hint': "Names: & (and), | (or)", 'date_from_label': "Date from:", 'date_to_label': "to:", 'date_format_hint': "Format: YYYY-MM-DD",
                'search_btn': "Search", 'reset_btn': "Reset", 'images_frame': "Images", 'exit_btn': "EXIT", 'col_id': "ID", 'col_file': "File", 'col_date': "Date", 'col_people': "People", 'col_faces': "Faces", 'col_dogs': "Dogs", 'col_ai': "AI",
                'image_frame': "Image", 'tab_general': "General Info", 'tab_people': "Recognized People", 'tab_dogs': "Recognized Dogs", 'tab_ai': "AI Descriptions",
                'file_not_found': "File not found", 'display_error': "Display Error: {}", 'status_select_db': "Select a database file and click 'Open'",
                'status_db_opened': "Database opened: {}", 'status_db_error': "Error opening database", 'status_loading_error': "Error loading images: {}", 'error': "Error",
                'warn_db_exists': "Please select an existing database file.", 'warn_db_structure': "Invalid database structure.", 'info_not_found': "Image information not found.",
                'ai_unsupported': "AI descriptions are not supported by this database.", 'ai_unavailable': "AI descriptions are unavailable for this image.",
                'people_on_photo': "People in Photo:", 'edit_btn': "Edit", 'delete_btn': "Delete", 'save_btn': "Save",
                'col_person_index': "#", 'col_type': "Type", 'col_person_name': "Name", 'col_status': "Status", 'person_type_face': "With Face",
                'person_type_noface': "No Face", 'status_known': "Known", 'status_local': "Local", 'status_unknown': "Unknown", 'dogs_on_photo': "Dogs in Photo:",
                'col_dog_index': "#", 'col_dog_name': "Nickname", 'col_breed': "Breed", 'col_owner': "Owner", 'unsupported_feature': "Not Supported", 'status_known_fem': "Known", 'status_unknown_fem': "Unknown",
                'confirm_delete_title': "Confirm Deletion", 'confirm_delete_msg': "Are you sure you want to permanently delete this detection from the photo?",
                'ai_short_desc': "Short Description:", 'ai_detailed_desc': "Detailed Description:",
                'unsaved_changes_title': "Unsaved Changes", 'unsaved_changes_msg': "You have unsaved changes in AI Descriptions. Do you want to save them?",
                'select_from_db': "Select from DB", 'create_new': "Create New", 'local_id': "Local ID", 'apply_btn': "Apply", 'reset_link_btn': "Reset Link", 'cancel_btn': "Cancel", 'warning': "Warning", 'confirm': "Confirmation",
                'edit_person_dialog_title': "Edit Person Information", 'col_full_name': "Full Name", 'col_short_name': "Short Name", 'col_notes': "Notes", 'local_id_info': "Local identification is saved only for this specific photo.",
                'warn_select_person': "Please select a person from the list.", 'warn_enter_fullname': "Please enter a full name.", 'warn_enter_fullname_local': "Please enter a full name for local identification.", 'confirm_remove_person_link': "Are you sure you want to remove the link to this person?",
                'edit_dog_dialog_title': "Edit Dog Information", 'warn_select_dog': "Please select a dog from the list.", 'warn_enter_dog_name': "Please enter a nickname.", 'confirm_remove_dog_link': "Are you sure you want to remove the link to this dog?",
            },
            'RU': {
                'title': f"Просмотрщик баз данных лиц v{VERSION}", 'db_label': "База данных:", 'browse_btn': "Выбрать...", 'open_btn': "📂 Открыть",
                'search_frame': "Поиск", 'name_dog_label': "Имя/Кличка:", 'name_hint': "Имена: & (и), | (или)", 'date_from_label': "Дата с:", 'date_to_label': "по:", 'date_format_hint': "Формат: YYYY-MM-DD",
                'search_btn': "Искать", 'reset_btn': "Сбросить", 'images_frame': "Изображения", 'exit_btn': "ВЫХОД", 'col_id': "ID", 'col_file': "Файл", 'col_date': "Дата", 'col_people': "Люди", 'col_faces': "Лица", 'col_dogs': "Собаки", 'col_ai': "AI",
                'image_frame': "Изображение", 'tab_general': "Общая информация", 'tab_people': "Распознанные люди", 'tab_dogs': "Распознанные собаки", 'tab_ai': "AI Описания",
                'file_not_found': "Файл не найден", 'display_error': "Ошибка отображения: {}", 'status_select_db': "Выберите базу данных и нажмите 'Открыть'",
                'status_db_opened': "База данных открыта: {}", 'status_db_error': "Ошибка открытия БД", 'status_loading_error': "Ошибка загрузки изображений: {}", 'error': "Ошибка",
                'warn_db_exists': "Выберите существующий файл базы данных.", 'warn_db_structure': "Неверная структура БД.", 'info_not_found': "Информация об изображении не найдена.",
                'ai_unsupported': "AI описания не поддерживаются этой базой данных.", 'ai_unavailable': "AI описания для этого изображения отсутствуют.",
                'people_on_photo': "Люди на фото:", 'edit_btn': "Редактировать", 'delete_btn': "Удалить", 'save_btn': "Сохранить",
                'col_person_index': "#", 'col_type': "Тип", 'col_person_name': "Имя", 'col_status': "Статус", 'person_type_face': "С лицом", 'person_type_noface': "Без лица",
                'status_known': "Известный", 'status_local': "Локальный", 'status_unknown': "Неизвестный", 'dogs_on_photo': "Собаки на фото:",
                'col_dog_index': "#", 'col_dog_name': "Кличка", 'col_breed': "Порода", 'col_owner': "Владелец", 'unsupported_feature': "Не поддерживается", 'status_known_fem': "Известная", 'status_unknown_fem': "Неизвестная",
                'confirm_delete_title': "Подтвердите удаление", 'confirm_delete_msg': "Вы уверены, что хотите навсегда удалить это обнаружение с фотографии?",
                'ai_short_desc': "Краткое описание:", 'ai_detailed_desc': "Детальное описание:",
                'unsaved_changes_title': "Несохраненные изменения", 'unsaved_changes_msg': "В AI описаниях есть несохраненные изменения. Хотите сохранить их?",
                'select_from_db': "Выбрать из БД", 'create_new': "Создать нового", 'local_id': "Локальная идентификация", 'apply_btn': "Применить", 'reset_link_btn': "Сбросить связь", 'cancel_btn': "Отмена", 'warning': "Предупреждение", 'confirm': "Подтверждение",
                'edit_person_dialog_title': "Редактировать информацию о человеке", 'col_full_name': "Полное имя", 'col_short_name': "Короткое имя", 'col_notes': "Примечание", 'local_id_info': "Локальная идентификация сохраняется только для данного фото.",
                'warn_select_person': "Выберите человека из списка.", 'warn_enter_fullname': "Введите полное имя.", 'warn_enter_fullname_local': "Введите полное имя для локальной идентификации.", 'confirm_remove_person_link': "Удалить связь с человеком?",
                'edit_dog_dialog_title': "Редактировать информацию о собаке", 'warn_select_dog': "Выберите собаку из списка.", 'warn_enter_dog_name': "Введите кличку.", 'confirm_remove_dog_link': "Удалить связь с собакой?",
            }
        }

    def update_status(self, message_key, status_type):
        lang = self.lang.get(); message = self.i18n[lang].get(message_key, message_key)
        self.status_bar.config(text=message)
        style_map = {'idle':'Idle.Status.TLabel','processing':'Processing.Status.TLabel','complete':'Complete.Status.TLabel','error':'Error.Status.TLabel'}
        self.status_bar.config(style=style_map.get(status_type, 'Idle.Status.TLabel'))

    def on_lang_change(self, event=None):
        self.update_ui_language()
        if self.db_path.get(): self.refresh_view_after_change()

    def create_widgets(self):
        top_frame = ttk.Frame(self.root, padding="10"); top_frame.pack(side=tk.TOP, fill=tk.X); top_frame.columnconfigure(4, weight=1)
        self.db_label = ttk.Label(top_frame); self.db_label.grid(row=0, column=0, padx=(0, 5), sticky='w')
        self.db_path_entry = ttk.Entry(top_frame, textvariable=self.db_path, width=50); self.db_path_entry.grid(row=0, column=1, sticky='w')
        self.browse_button = ttk.Button(top_frame, command=self.browse_db); self.browse_button.grid(row=0, column=2, padx=5, sticky='w')
        self.open_button = ttk.Button(top_frame, command=self.open_db, style="Accent.TButton"); self.open_button.grid(row=0, column=3, sticky='w')
        ttk.Label(top_frame, text="").grid(row=0, column=4)
        self.lang_label = ttk.Label(top_frame, text="Language:", font=('Arial', 9, 'bold')); self.lang_label.grid(row=0, column=5, sticky='e')
        lang_combo = ttk.Combobox(self.root, textvariable=self.lang, values=['EN', 'RU'], width=4, state="readonly"); lang_combo.grid(row=0, column=6, in_=top_frame, sticky='e')
        lang_combo.bind('<<ComboboxSelected>>', self.on_lang_change)
        self.version_label = ttk.Label(top_frame, text=f"v{VERSION}", font=('Arial', 9)); self.version_label.grid(row=0, column=7, sticky='e', padx=5)
        self.status_bar = ttk.Label(self.root, relief=tk.SUNKEN); self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        bottom_frame = ttk.Frame(self.root, padding=(10, 5)); bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.exit_button = ttk.Button(bottom_frame, command=self.root.destroy); self.exit_button.pack(side=tk.RIGHT)
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL); main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 0))
        left_frame = ttk.Frame(main_paned); main_paned.add(left_frame, weight=2)
        self.create_search_panel(left_frame); self.create_image_list(left_frame)
        right_paned = tk.PanedWindow(main_paned, orient=tk.VERTICAL, sashrelief=tk.RAISED, bg="#dcdcdc"); main_paned.add(right_paned, weight=5)
        self.image_frame = ttk.LabelFrame(right_paned, padding="5"); right_paned.add(self.image_frame, minsize=300)
        self.image_label = ttk.Label(self.image_frame, anchor='center'); self.image_label.pack(fill=tk.BOTH, expand=True)
        self.info_notebook = ttk.Notebook(right_paned); right_paned.add(self.info_notebook, minsize=200)
        self.tab_general_frame = ttk.Frame(self.info_notebook); self.tab_people_frame = ttk.Frame(self.info_notebook)
        self.tab_dogs_frame = ttk.Frame(self.info_notebook); self.tab_ai_frame = ttk.Frame(self.info_notebook)
        self.info_notebook.add(self.tab_general_frame, text=""); self.info_notebook.add(self.tab_people_frame, text="")
        self.info_notebook.add(self.tab_dogs_frame, text=""); self.info_notebook.add(self.tab_ai_frame, text="")
        self.active_tab_frame = self.tab_general_frame
        self.create_general_info(self.tab_general_frame); self.create_people_info(self.tab_people_frame)
        self.create_dogs_info(self.tab_dogs_frame); self.create_ai_descriptions(self.tab_ai_frame)
        self.info_notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)

    def update_ui_language(self):
        lang, ld = self.lang.get(), self.i18n[self.lang.get()]
        self.root.title(ld['title']); self.db_label.config(text=ld['db_label']); self.browse_button.config(text=ld['browse_btn'])
        self.open_button.config(text=ld['open_btn']); self.search_frame.config(text=ld['search_frame'])
        self.name_dog_label.config(text=ld['name_dog_label']); self.name_hint_label.config(text=ld['name_hint'])
        self.date_from_label.config(text=ld['date_from_label']); self.date_to_label.config(text=ld['date_to_label'])
        self.date_format_hint_label.config(text=ld['date_format_hint']); self.search_button.config(text=ld['search_btn'])
        self.reset_button.config(text=ld['reset_btn']); self.image_list_frame.config(text=ld['images_frame'])
        self.image_tree.heading('ID',text=ld['col_id']); self.image_tree.heading('File',text=ld['col_file']); self.image_tree.heading('Date',text=ld['col_date'])
        self.image_tree.heading('People',text=ld['col_people']); self.image_tree.heading('Faces',text=ld['col_faces']); self.image_tree.heading('Dogs',text=ld['col_dogs']); self.image_tree.heading('AI',text=ld['col_ai'])
        self.image_frame.config(text=ld['image_frame']); self.info_notebook.tab(self.tab_general_frame, text=ld['tab_general'])
        self.info_notebook.tab(self.tab_people_frame, text=ld['tab_people']); self.info_notebook.tab(self.tab_dogs_frame, text=ld['tab_dogs'])
        self.info_notebook.tab(self.tab_ai_frame, text=ld['tab_ai']); self.people_header_label.config(text=ld['people_on_photo'])
        self.edit_person_btn.config(text=ld['edit_btn']); self.delete_person_btn.config(text=ld['delete_btn'])
        self.people_tree.heading('#',text=ld['col_person_index']); self.people_tree.heading('Type',text=ld['col_type']); self.people_tree.heading('Name',text=ld['col_person_name'])
        self.people_tree.heading('Status',text=ld['col_status']); self.people_tree.heading('ID',text=ld['col_id']); self.dogs_header_label.config(text=ld['dogs_on_photo'])
        self.edit_dog_btn.config(text=ld['edit_btn']); self.delete_dog_btn.config(text=ld['delete_btn'])
        self.dogs_tree.heading('#',text=ld['col_dog_index']); self.dogs_tree.heading('Name',text=ld['col_dog_name']); self.dogs_tree.heading('Breed',text=ld['col_breed'])
        self.dogs_tree.heading('Owner',text=ld['col_owner']); self.dogs_tree.heading('Status',text=ld['col_status']); self.dogs_tree.heading('ID',text=ld['col_id'])
        self.exit_button.config(text=ld['exit_btn'])
        self.ai_short_desc_label.config(text=ld['ai_short_desc']); self.ai_detailed_desc_label.config(text=ld['ai_detailed_desc'])
        current_ai_btn_text = self.edit_ai_btn.cget('text')
        if current_ai_btn_text == self.i18n['EN']['edit_btn'] or current_ai_btn_text == self.i18n['RU']['edit_btn']: self.edit_ai_btn.config(text=ld['edit_btn'])
        else: self.edit_ai_btn.config(text=ld['save_btn'])

    def create_search_panel(self, parent):
        self.search_frame = ttk.LabelFrame(parent, padding="10"); self.search_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 5)); self.search_frame.columnconfigure(1, weight=1)
        self.name_dog_label = ttk.Label(self.search_frame); self.name_dog_label.grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(self.search_frame, textvariable=self.search_name).grid(row=0, column=1, columnspan=2, sticky=tk.EW, pady=2)
        self.name_hint_label = ttk.Label(self.search_frame, font=('Arial', 8, 'italic')); self.name_hint_label.grid(row=1, column=1, columnspan=2, sticky=tk.W)
        self.date_from_label = ttk.Label(self.search_frame); self.date_from_label.grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(self.search_frame, textvariable=self.search_date_from).grid(row=2, column=1, sticky=tk.EW, pady=2)
        self.date_to_label = ttk.Label(self.search_frame); self.date_to_label.grid(row=2, column=2, sticky=tk.W, padx=5)
        ttk.Entry(self.search_frame, textvariable=self.search_date_to).grid(row=2, column=3, sticky=tk.EW, pady=2)
        self.date_format_hint_label = ttk.Label(self.search_frame, font=('Arial', 8, 'italic')); self.date_format_hint_label.grid(row=3, column=1, columnspan=3, sticky=tk.W)
        button_frame = ttk.Frame(self.search_frame); button_frame.grid(row=4, column=0, columnspan=4, pady=(10, 0))
        self.search_button = ttk.Button(button_frame, command=self.search_images, style="Accent.TButton"); self.search_button.pack(side=tk.LEFT, padx=5)
        self.reset_button = ttk.Button(button_frame, command=self.reset_search); self.reset_button.pack(side=tk.LEFT, padx=5)

    def create_image_list(self, parent):
        self.image_list_frame = ttk.LabelFrame(parent, padding="5"); self.image_list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        columns = ('ID', 'File', 'Date', 'People', 'Faces', 'Dogs', 'AI')
        self.image_tree = ttk.Treeview(self.image_list_frame, columns=columns, show='headings')
        for col in columns: self.image_tree.heading(col, text=col)
        for col, w in [('ID',40),('File',200),('Date',90),('People',40),('Faces',40),('Dogs',50),('AI',30)]: self.image_tree.column(col, width=w, anchor='center')
        self.image_tree.column('File', anchor='w')
        scrollbar = ttk.Scrollbar(self.image_list_frame, orient=tk.VERTICAL, command=self.image_tree.yview); self.image_tree.configure(yscrollcommand=scrollbar.set)
        self.image_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); scrollbar.pack(side=tk.RIGHT, fill=tk.Y); self.image_tree.bind('<<TreeviewSelect>>', self.on_image_select)

    def create_general_info(self, parent): self.info_text = tk.Text(parent, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1, font=('Arial',10), background="#fdfdfd", padx=5, pady=5); self.info_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

    def create_people_info(self, parent):
        header = ttk.Frame(parent); header.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(5,2))
        self.people_header_label = ttk.Label(header, font=('Arial', 10, 'bold')); self.people_header_label.pack(side=tk.LEFT)
        buttons_right_frame = ttk.Frame(header); buttons_right_frame.pack(side=tk.RIGHT)
        self.edit_person_btn = ttk.Button(buttons_right_frame, command=self.edit_person_detection, state=tk.DISABLED); self.edit_person_btn.pack(side=tk.LEFT)
        self.delete_person_btn = ttk.Button(buttons_right_frame, command=self.delete_person_detection, state=tk.DISABLED); self.delete_person_btn.pack(side=tk.LEFT, padx=(5,0))
        content_frame = ttk.Frame(parent); content_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=(0,5))
        cols = ('#', 'Type', 'Name', 'Status', 'ID')
        self.people_tree = ttk.Treeview(content_frame, columns=cols, show='headings')
        for col in cols: self.people_tree.heading(col, text=col)
        for col, w in [('#',30),('Type',80),('Name',200),('Status',120),('ID',50)]: self.people_tree.column(col, width=w, anchor='center')
        self.people_tree.column('Name', anchor='w')
        scroll = ttk.Scrollbar(content_frame, orient=tk.VERTICAL, command=self.people_tree.yview); self.people_tree.configure(yscrollcommand=scroll.set)
        self.people_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); scroll.pack(side=tk.RIGHT, fill=tk.Y); self.people_tree.bind('<<TreeviewSelect>>', self.on_person_select)

    def create_dogs_info(self, parent):
        header = ttk.Frame(parent); header.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(5,2))
        self.dogs_header_label = ttk.Label(header, font=('Arial', 10, 'bold')); self.dogs_header_label.pack(side=tk.LEFT)
        buttons_right_frame = ttk.Frame(header); buttons_right_frame.pack(side=tk.RIGHT)
        self.edit_dog_btn = ttk.Button(buttons_right_frame, command=self.edit_dog_detection, state=tk.DISABLED); self.edit_dog_btn.pack(side=tk.LEFT)
        self.delete_dog_btn = ttk.Button(buttons_right_frame, command=self.delete_dog_detection, state=tk.DISABLED); self.delete_dog_btn.pack(side=tk.LEFT, padx=(5,0))
        content_frame = ttk.Frame(parent); content_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=(0,5))
        cols = ('#', 'Name', 'Breed', 'Owner', 'Status', 'ID')
        self.dogs_tree = ttk.Treeview(content_frame, columns=cols, show='headings')
        for col in cols: self.dogs_tree.heading(col, text=col)
        for col, w in [('#',30),('Name',120),('Breed',120),('Owner',120),('Status',100),('ID',50)]: self.dogs_tree.column(col, width=w, anchor='center')
        for col in ['Name', 'Breed', 'Owner']: self.dogs_tree.column(col, anchor='w')
        scroll = ttk.Scrollbar(content_frame, orient=tk.VERTICAL, command=self.dogs_tree.yview); self.dogs_tree.configure(yscrollcommand=scroll.set)
        self.dogs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); scroll.pack(side=tk.RIGHT, fill=tk.Y); self.dogs_tree.bind('<<TreeviewSelect>>', self.on_dog_select)

    def create_ai_descriptions(self, parent):
        header = ttk.Frame(parent); header.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(5,2))
        self.edit_ai_btn = ttk.Button(header, text="Edit", command=self.toggle_ai_edit_mode, state=tk.DISABLED)
        self.edit_ai_btn.pack(side=tk.RIGHT)
        self.ai_short_desc_label = ttk.Label(parent, font=('Arial', 10, 'bold')); self.ai_short_desc_label.pack(fill=tk.X, padx=10, pady=(5,0))
        self.ai_short_text = tk.Text(parent, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1, height=3, state=tk.DISABLED, padx=5, pady=5)
        self.ai_short_text.pack(fill=tk.X, expand=False, padx=10, pady=5)
        self.ai_detailed_desc_label = ttk.Label(parent, font=('Arial', 10, 'bold')); self.ai_detailed_desc_label.pack(fill=tk.X, padx=10, pady=(5,0))
        self.ai_long_text = tk.Text(parent, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1, state=tk.DISABLED, padx=5, pady=5)
        self.ai_long_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    def browse_db(self):
        ld = self.i18n[self.lang.get()]; filename = filedialog.askopenfilename(title=ld['db_label'], filetypes=[("SQLite DB", "*.db"), (ld['col_file'], "*.*")])
        if filename: self.db_path.set(filename)

    def open_db(self):
        db_path, ld = self.db_path.get(), self.i18n[self.lang.get()]
        if not db_path or not os.path.exists(db_path): messagebox.showerror(ld['error'], ld['warn_db_exists']); return
        try:
            with sqlite3.connect(db_path) as conn:
                c = conn.cursor(); c.execute("SELECT name FROM sqlite_master WHERE type='table'"); tables = [r[0] for r in c.fetchall()]
                if 'images' not in tables or 'person_detections' not in tables: raise sqlite3.DatabaseError(ld['warn_db_structure'])
                self.has_dogs = 'dogs' in tables and 'dog_detections' in tables
                c.execute("PRAGMA table_info(images)"); self.has_ai_descriptions = 'ai_short_description' in [col[1] for col in c.fetchall()]
            self.load_images(); self.update_status(ld['status_db_opened'].format(os.path.basename(db_path)), 'complete')
        except Exception as e: messagebox.showerror(ld['error'], f"{ld['status_db_error']}: {e}"); self.update_status(f"{ld['status_db_error']}", 'error')

    def load_images(self, **kwargs):
        for item in self.image_tree.get_children(): self.image_tree.delete(item)
        if not self.db_path.get(): return
        try:
            with sqlite3.connect(self.db_path.get()) as conn:
                base = "SELECT i.id, i.filename, i.created_date, i.num_bodies, i.num_faces, i.filepath"; parts, params = [base], []
                if self.has_dogs: parts.append(", i.num_dogs")
                else: parts.append(", 0 as num_dogs")
                if self.has_ai_descriptions: parts.append(", i.ai_short_description")
                else: parts.append(", NULL as ai_short_description")
                parts.append("FROM images i"); conds, pattern = [], self.search_name.get().strip()
                if pattern:
                    parts.append("LEFT JOIN person_detections pd ON i.id=pd.image_id LEFT JOIN persons p ON pd.person_id=p.id")
                    if self.has_dogs: parts.append("LEFT JOIN dog_detections dd ON i.id=dd.image_id LEFT JOIN dogs d ON dd.dog_id=d.id")
                    if '&' in pattern:
                        names = [n.strip() for n in pattern.split('&') if n.strip()]
                        for name in names:
                            like = f"%{name}%"; sub = "(p.full_name LIKE ? OR p.short_name LIKE ? OR pd.local_full_name LIKE ? OR pd.local_short_name LIKE ?)"
                            if self.has_dogs: sub=f"({sub} OR d.name LIKE ?)"; params.extend([like]*5)
                            else: params.extend([like]*4)
                            conds.append(f"i.id IN (SELECT image_id FROM person_detections pd LEFT JOIN persons p ON pd.person_id=p.id {'LEFT JOIN dog_detections dd ON pd.image_id=dd.image_id LEFT JOIN dogs d ON dd.dog_id=d.id' if self.has_dogs else ''} WHERE {sub})")
                    else:
                        names = [n.strip() for n in pattern.split('|') if n.strip()]
                        if not names: names = [pattern]
                        clauses = []
                        for name in names:
                            like=f"%{name}%"; c="(p.full_name LIKE ? OR p.short_name LIKE ? OR pd.local_full_name LIKE ? OR pd.local_short_name LIKE ?)"
                            if self.has_dogs: c=f"({c} OR d.name LIKE ?)"; params.extend([like]*5)
                            else: params.extend([like]*4)
                            clauses.append(c)
                        conds.append(f"({' OR '.join(clauses)})")
                if self.search_date_from.get(): conds.append("date(i.created_date) >= ?"); params.append(self.search_date_from.get())
                if self.search_date_to.get(): conds.append("date(i.created_date) <= ?"); params.append(self.search_date_to.get())
                if conds: parts.append("WHERE " + " AND ".join(conds))
                parts.append("GROUP BY i.id ORDER BY i.created_date DESC")
                for r in conn.execute(" ".join(parts), params):
                    date = datetime.fromisoformat(r[2]).strftime("%Y-%m-%d") if r[2] else ""
                    self.image_tree.insert('', tk.END, values=(r[0],r[1],date,r[3],r[4],r[6] if self.has_dogs else '-',"✓" if r[7] else ""), tags=(r[5],))
        except Exception as e: messagebox.showerror(self.i18n[self.lang.get()]['error'], self.i18n[self.lang.get()]['status_loading_error'].format(e))

    def search_images(self): self.load_images()
    def reset_search(self): self.search_name.set(""); self.search_date_from.set(""); self.search_date_to.set(""); self.load_images()

    def on_image_select(self, event=None):
        selection = self.image_tree.selection()
        new_iid = selection[0] if selection else None
        if new_iid == self.previous_selection_iid: return
        if not self.handle_ai_unsaved_changes():
            if self.previous_selection_iid: self.image_tree.selection_set(self.previous_selection_iid)
            return
        if not selection: self.previous_selection_iid = None; return
        item = self.image_tree.item(new_iid); self.current_image_id = item['values'][0]; filepath = item['tags'][0] if item['tags'] else None
        self.highlighted_person_detection_id = None; self.highlighted_dog_detection_id = None
        for btn in [self.edit_person_btn, self.delete_person_btn, self.edit_dog_btn, self.delete_dog_btn, self.edit_ai_btn]: btn.config(state=tk.DISABLED)
        self.display_image(filepath); self.on_tab_changed(); self.previous_selection_iid = new_iid

    def on_tab_changed(self, event=None):
        if not self.current_image_id: return
        new_tab = self.info_notebook.nametowidget(self.info_notebook.select())
        if self.active_tab_frame == self.tab_ai_frame and new_tab != self.tab_ai_frame:
            if not self.handle_ai_unsaved_changes():
                self.info_notebook.select(self.tab_ai_frame); return
        self.active_tab_frame = new_tab
        if new_tab==self.tab_general_frame: self.show_image_info()
        elif new_tab==self.tab_people_frame: self.show_people_info()
        elif new_tab==self.tab_dogs_frame: self.show_dogs_info()
        elif new_tab==self.tab_ai_frame: self.show_ai_descriptions()
        if new_tab not in [self.tab_people_frame, self.tab_dogs_frame] and (self.highlighted_person_detection_id or self.highlighted_dog_detection_id):
            self.highlighted_person_detection_id=None; self.highlighted_dog_detection_id=None
            if self.image_tree.selection(): self.display_image(self.image_tree.item(self.image_tree.selection()[0])['tags'][0])

    def display_image(self, filepath):
        ld = self.i18n[self.lang.get()]
        if not filepath or not os.path.exists(filepath): self.image_label.config(image='', text=ld['file_not_found']); return
        try:
            image = Image.open(filepath); image = correct_image_orientation(image); draw = ImageDraw.Draw(image, 'RGBA')
            try: font, h_font = ImageFont.truetype("arial.ttf", 20), ImageFont.truetype("arial.ttf", 24)
            except IOError: font = h_font = ImageFont.load_default()
            with sqlite3.connect(self.db_path.get()) as conn:
                q_p = "SELECT pd.id, pd.bbox, pd.has_face, p.is_known, COALESCE(p.short_name, pd.local_short_name, ?), pd.person_index FROM person_detections pd LEFT JOIN persons p ON pd.person_id=p.id WHERE pd.image_id=?"
                for det_id, bbox_js, has_face, is_known, name, index in conn.execute(q_p, (ld['status_unknown'], self.current_image_id)):
                    is_hl, t_face, t_noface = (self.highlighted_person_detection_id == det_id), ld['person_type_face'], ld['person_type_noface']
                    color, text = ("purple",f"#{index}: {name}") if is_known else (("green",f"#{index}: {t_face}") if has_face else ("yellow",f"#{index}: {t_noface}"))
                    self._draw_box_and_text(draw, json.loads(bbox_js), text, color, is_hl, font, h_font)
                if self.has_dogs:
                    q_d = "SELECT dd.id, dd.bbox, d.is_known, d.name, dd.dog_index FROM dog_detections dd LEFT JOIN dogs d ON dd.dog_id=d.id WHERE dd.image_id=?"
                    for det_id, bbox_js, is_known, name, index in conn.execute(q_d, (self.current_image_id,)):
                        is_hl, t_dog = (self.highlighted_dog_detection_id == det_id), ld['col_dogs'][:-1] if ld['col_dogs'].endswith('s') else ld['col_dogs']
                        color, text = ("#800080",f"{t_dog} #{index}: {name}") if is_known else ("orange",f"{t_dog} #{index}")
                        self._draw_box_and_text(draw, json.loads(bbox_js), text, color, is_hl, font, h_font)
            self.image_label.update_idletasks()
            w, h = self.image_label.winfo_width(), self.image_label.winfo_height()
            if w > 10 and h > 10: image.thumbnail((w-20, h-20), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image); self.image_label.config(image=photo, text=''); self.image_label.image = photo
        except Exception as e: self.image_label.config(image='', text=ld['display_error'].format(e))

    def _draw_box_and_text(self, draw, bbox, text, color, is_highlighted, font, highlight_font):
        x1, y1, x2, y2 = bbox; width, current_font = (6, highlight_font) if is_highlighted else (3, font)
        draw.rectangle([x1, y1, x2, y2], outline=color, width=width)
        try:
             bbox = draw.textbbox((0,0), text, font=current_font); h=bbox[3]-bbox[1]; pos=(x1, y1-h-7)
        except AttributeError: pos=(x1, y1-25); h=15
        w = draw.textlength(text,font=current_font) if hasattr(draw,'textlength') else 100
        bbox_final = (pos[0], pos[1], pos[0]+w, pos[1]+h+5)
        draw.rectangle([bbox_final[0]-3, bbox_final[1]-3, bbox_final[2]+3, bbox_final[3]+3], fill=(255,255,255,200))
        draw.text(pos, text, fill=color, font=current_font)

    def _execute_info_query(self, query, formatter, default_text):
        if not self.current_image_id: return default_text
        with sqlite3.connect(self.db_path.get()) as conn:
            row = conn.execute(query, (self.current_image_id,)).fetchone()
            return formatter(row, self.i18n[self.lang.get()]) if row else default_text

    def show_image_info(self):
        def formatter(r,ld): return (f"{ld['col_file']}: {r[0]}\nPath: {r[1]}\nSize: {r[2]:,} bytes\nCreation Date: {r[3]}\n"
                                     f"Processed Date: {r[4]}\n\n{ld['col_people']}: {r[5]}\n{ld['col_faces']}: {r[6]}\n"
                                     f"{ld['col_dogs']}: {r[7] if len(r)>7 and r[7] is not None else 'N/A'}")
        info = self._execute_info_query("SELECT filename, filepath, file_size, created_date, processed_date, num_bodies, num_faces, num_dogs FROM images WHERE id=?", formatter, self.i18n[self.lang.get()]['info_not_found'])
        self.info_text.delete('1.0', tk.END); self.info_text.insert('1.0', info)

    def show_ai_descriptions(self):
        ld = self.i18n[self.lang.get()]
        self.ai_short_text.config(state=tk.NORMAL); self.ai_long_text.config(state=tk.NORMAL)
        self.ai_short_text.delete('1.0', tk.END); self.ai_long_text.delete('1.0', tk.END)
        self.edit_ai_btn.config(state=tk.DISABLED)
        if self.has_ai_descriptions:
            res = self._execute_info_query("SELECT ai_short_description, ai_long_description FROM images WHERE id = ?", lambda r,ld: (r[0] or "", r[1] or ""), (ld['ai_unavailable'],""))
            if res:
                self.ai_short_text.insert('1.0', res[0]); self.ai_long_text.insert('1.0', res[1])
                self.edit_ai_btn.config(state=tk.NORMAL)
        else: self.ai_short_text.insert('1.0', ld['ai_unsupported'])
        self.ai_short_text.config(state=tk.DISABLED); self.ai_long_text.config(state=tk.DISABLED)

    def leave_ai_edit_mode(self):
        self.ai_edit_mode = False
        self.edit_ai_btn.config(text=self.i18n[self.lang.get()]['edit_btn'])
        self.ai_short_text.config(state=tk.DISABLED); self.ai_long_text.config(state=tk.DISABLED)
        self.ai_original_short = ""; self.ai_original_long = ""

    def handle_ai_unsaved_changes(self):
        if not self.ai_edit_mode: return True
        current_short = self.ai_short_text.get('1.0', tk.END).strip()
        current_long = self.ai_long_text.get('1.0', tk.END).strip()
        if current_short == self.ai_original_short and current_long == self.ai_original_long:
            self.leave_ai_edit_mode(); return True
        ld = self.i18n[self.lang.get()]
        msg = ld['unsaved_changes_msg']; title = ld['unsaved_changes_title']
        response = messagebox.askyesnocancel(title, msg)
        if response is True: # Yes
            self.save_ai_descriptions(); self.leave_ai_edit_mode(); return True
        elif response is False: # No
            self.leave_ai_edit_mode(); return True
        else: # Cancel
            return False

    def toggle_ai_edit_mode(self):
        ld = self.i18n[self.lang.get()]
        if not self.ai_edit_mode:
            self.ai_edit_mode = True; self.edit_ai_btn.config(text=ld['save_btn'])
            self.ai_short_text.config(state=tk.NORMAL); self.ai_long_text.config(state=tk.NORMAL)
            self.ai_original_short = self.ai_short_text.get('1.0', tk.END).strip()
            self.ai_original_long = self.ai_long_text.get('1.0', tk.END).strip()
            self.ai_short_text.focus()
        else:
            self.save_ai_descriptions(); self.leave_ai_edit_mode()

    def save_ai_descriptions(self):
        if not self.current_image_id: return
        short, long = self.ai_short_text.get('1.0', tk.END).strip(), self.ai_long_text.get('1.0', tk.END).strip()
        with sqlite3.connect(self.db_path.get()) as conn:
            conn.execute("UPDATE images SET ai_short_description=?, ai_long_description=? WHERE id=?", (short, long, self.current_image_id)); conn.commit()

    def _update_detection_tree(self, tree, query):
        for item in tree.get_children(): tree.delete(item)
        if not self.current_image_id: return
        with sqlite3.connect(self.db_path.get()) as conn:
            for row in conn.execute(query, (self.current_image_id,)): tree.insert('', tk.END, values=row[:-1], tags=(row[-1],))

    def show_people_info(self):
        ld=self.i18n[self.lang.get()]; query=f"SELECT pd.person_index, CASE WHEN pd.has_face THEN '{ld['person_type_face']}' ELSE '{ld['person_type_noface']}' END, COALESCE(p.full_name, pd.local_full_name, '{ld['status_unknown']}'), CASE WHEN p.is_known THEN '{ld['status_known']}' WHEN pd.is_locally_identified THEN '{ld['status_local']}' ELSE '{ld['status_unknown']}' END, p.id, pd.id FROM person_detections pd LEFT JOIN persons p ON pd.person_id = p.id WHERE pd.image_id = ? ORDER BY pd.person_index"
        self._update_detection_tree(self.people_tree, query)

    def show_dogs_info(self):
        ld = self.i18n[self.lang.get()]; self.dogs_tree.delete(*self.dogs_tree.get_children())
        if not self.has_dogs: self.dogs_tree.insert('', tk.END, values=('', ld['unsupported_feature'], '')); return
        query = f"SELECT dd.dog_index, d.name, d.breed, d.owner, CASE WHEN d.is_known THEN '{ld['status_known_fem']}' ELSE '{ld['status_unknown_fem']}' END, d.id, dd.id FROM dog_detections dd LEFT JOIN dogs d ON dd.dog_id = d.id WHERE dd.image_id = ? ORDER BY dd.dog_index"
        self._update_detection_tree(self.dogs_tree, query)

    def _on_detection_select(self, type):
        is_person = (type == 'people'); tree = self.people_tree if is_person else self.dogs_tree
        edit_btn, del_btn = (self.edit_person_btn, self.delete_person_btn) if is_person else (self.edit_dog_btn, self.delete_dog_btn)
        selection = tree.selection()
        if not selection: edit_btn.config(state=tk.DISABLED); del_btn.config(state=tk.DISABLED); return
        edit_btn.config(state=tk.NORMAL); del_btn.config(state=tk.NORMAL)
        detection_id = tree.item(selection[0])['tags'][0]
        setattr(self, f'highlighted_{"person" if is_person else "dog"}_detection_id', detection_id)
        if is_person: self.highlighted_dog_detection_id = None
        else: self.highlighted_person_detection_id = None
        self.display_image(self.image_tree.item(self.image_tree.selection()[0])['tags'][0])

    def on_person_select(self, event): self._on_detection_select('people')
    def on_dog_select(self, event): self._on_detection_select('dogs')
    def edit_person_detection(self): self._edit_detection('people')
    def edit_dog_detection(self): self._edit_detection('dogs')
    def delete_person_detection(self): self._delete_detection('people')
    def delete_dog_detection(self): self._delete_detection('dogs')

    def refresh_view_after_change(self):
        if not self.db_path.get(): return
        sel_id = self.image_tree.item(self.image_tree.selection()[0])['values'][0] if self.image_tree.selection() else None
        self.load_images()
        if sel_id is not None:
            for iid in self.image_tree.get_children():
                if self.image_tree.item(iid)['values'][0] == sel_id:
                    self.image_tree.selection_set(iid); self.image_tree.focus(iid); self.image_tree.see(iid)
                    self.on_image_select(None); break

    def _edit_detection(self, type):
        tree = self.people_tree if type == 'people' else self.dogs_tree
        if not tree.selection(): return
        detection_id = tree.item(tree.selection()[0])['tags'][0]
        with sqlite3.connect(self.db_path.get()) as conn:
            id_field, table = ("person_id", "person_detections") if type == 'people' else ("dog_id", "dog_detections")
            current_id = conn.execute(f'SELECT {id_field} FROM {table} WHERE id = ?', (detection_id,)).fetchone()
        dialog = (EditPersonDialog if type=='people' else EditDogDialog)(self.root, self, detection_id, current_id[0] if current_id else None)
        self.root.wait_window(dialog)
        if dialog.result: self._apply_changes(type, detection_id, dialog.result); self.refresh_view_after_change()

    def _delete_detection(self, type):
        is_person = (type == 'people'); tree = self.people_tree if is_person else self.dogs_tree
        if not tree.selection(): return
        ld = self.i18n[self.lang.get()]
        if not messagebox.askyesno(ld['confirm_delete_title'], ld['confirm_delete_msg']): return
        detection_id = tree.item(tree.selection()[0])['tags'][0]; table = "person_detections" if is_person else "dog_detections"
        with sqlite3.connect(self.db_path.get()) as conn:
            cursor = conn.cursor()
            if is_person:
                res = cursor.execute("SELECT image_id, has_face FROM person_detections WHERE id = ?", (detection_id,)).fetchone()
                if not res: return
                image_id, has_face = res
            else:
                res = cursor.execute("SELECT image_id FROM dog_detections WHERE id = ?", (detection_id,)).fetchone()
                if not res: return
                image_id = res[0]
            cursor.execute(f"DELETE FROM {table} WHERE id = ?", (detection_id,))
            if is_person: cursor.execute("UPDATE images SET num_bodies=num_bodies-1, num_faces=num_faces-? WHERE id=?", (1 if has_face else 0, image_id))
            else: cursor.execute("UPDATE images SET num_dogs=num_dogs-1 WHERE id=?", (image_id,))
            conn.commit()
        self.refresh_view_after_change()

    def _apply_changes(self, type, detection_id, result):
        action = result.get('action')
        with sqlite3.connect(self.db_path.get()) as conn:
            cursor = conn.cursor()
            if type == 'people':
                if action == 'existing': cursor.execute('UPDATE person_detections SET person_id=?, is_locally_identified=0, local_full_name=NULL, local_short_name=NULL, local_notes=NULL WHERE id=?', (result['person_id'], detection_id))
                elif action == 'new':
                    cursor.execute('INSERT INTO persons (is_known, full_name, short_name, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?)', (result['full_name'], result['short_name'], result['notes'], datetime.now().isoformat(), datetime.now().isoformat()))
                    cursor.execute('UPDATE person_detections SET person_id=?, is_locally_identified=0, local_full_name=NULL, local_short_name=NULL, local_notes=NULL WHERE id=?', (cursor.lastrowid, detection_id))
                elif action == 'local': cursor.execute('UPDATE person_detections SET person_id=NULL, is_locally_identified=1, local_full_name=?, local_short_name=?, local_notes=? WHERE id=?', (result['local_full_name'], result['local_short_name'], result['local_notes'], detection_id))
                elif action == 'remove': cursor.execute('UPDATE person_detections SET person_id=NULL, is_locally_identified=0, local_full_name=NULL, local_short_name=NULL, local_notes=NULL WHERE id=?', (detection_id,))
            else:
                if action == 'existing': cursor.execute('UPDATE dog_detections SET dog_id=? WHERE id=?', (result['dog_id'], detection_id))
                elif action == 'new':
                    cursor.execute('INSERT INTO dogs (is_known, name, breed, owner, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?, ?)', (result['name'], result['breed'], result['owner'], result['notes'], datetime.now().isoformat(), datetime.now().isoformat()))
                    cursor.execute('UPDATE dog_detections SET dog_id=? WHERE id=?', (cursor.lastrowid, detection_id))
                elif action == 'remove': cursor.execute('UPDATE dog_detections SET dog_id=NULL WHERE id=?', (detection_id,))
            conn.commit()

def main():
    root = tk.Tk()
    app = FaceDBViewer(root)
    root.mainloop()

if __name__ == "__main__":
    main()