#
# Face Database Cleaner GUI v2.3
# A graphical application for finding and merging duplicates in a face database,
# including searching for people by face vector similarity.
#
# Version: 2.3
# - Added Exit button in the bottom right-hand corner of the window.
# - Updated version number.
#
# Version: 2.3
# - Added Exit button in the bottom right-hand corner of the window.
# - Updated version number.
#
# Version: 2.1
# - The language selection label is now always in English ("Language:").
# - The positions of the "Copy Log" and "Exit" buttons have been swapped.
# - Updated version number.
#
# Version: 2.0.0
# - Added multilingual support (Russian, English, Italian) with a language switcher.
# - The entire UI and all messages are now translated based on the selected language.
# - All code comments have been translated to English for better maintainability.
# - Centralized all translatable strings into a single dictionary.
#
# Version: 1.7.0
# - Fixed a nested 'FOREIGN KEY constraint failed' error by correcting the deletion order.
# - Added a version number display in the top-right corner.
# - Added an "Exit" button for convenience.
#
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
    messagebox.showerror("Library Missing", "The 'ImageHash' library is required.\nPlease install it: pip install ImageHash")
    exit()
try:
    import numpy as np
except ImportError:
    messagebox.showerror("Library Missing", "The 'numpy' library is required.\nPlease install it: pip install numpy")
    exit()

VERSION = "2.3"

# --- TRANSLATIONS ---
# Central dictionary for all UI strings and messages
TRANSLATIONS = {
    "ru": {
        "app_title": "FaceDB Cleaner GUI",
        "language": "Язык:",
        "db_frame_title": "База данных",
        "browse_button": "Выбрать...",
        "options_frame_title": "Опции очистки",
        "merge_people_check": "Объединить дубликаты людей (по точному совпадению имен)",
        "merge_dogs_check": "Объединить дубликаты собак (по точным данным)",
        "find_photos_check": "Найти и удалить дубликаты фото",
        "photo_threshold_label": "Порог схожести (0=точно, 10=свободно):",
        "find_faces_check": "Найти людей со схожими лицами (но разными именами)",
        "face_threshold_label": "Порог схожести (меньше = строже):",
        "log_frame_title": "Лог выполнения",
        "start_button": "🚀 Начать очистку",
        "copy_log_button": "📋",
        "exit_button": "Выход",
        "status_initial": "Выберите файл и опции для начала работы.",
        "status_db_selected": "Выбрана база данных: {filename}",
        "status_log_copied": "Лог скопирован в буфер обмена.",
        "status_running": "Выполнение...",
        "status_complete": "Очистка успешно завершена!",
        "status_complete_no_changes": "Очистка завершена. Изменения не требовались.",
        "status_error": "Ошибка! Изменения отменены.",
        "error_title": "Ошибка",
        "warning_title": "Предупреждение",
        "info_title": "Информация",
        "db_path_error": "Путь к базе данных не указан или файл не существует.",
        "no_options_error": "Выберите хотя бы одну опцию для очистки.",
        "log_connecting": "Подключение к БД: {db_path}",
        "log_all_changes_saved": "✅ Все изменения успешно сохранены.",
        "log_merged_people": "   - Объединено людей по именам: {count}",
        "log_merged_dogs": "   - Объединено собак по данным: {count}",
        "log_deleted_photos": "   - Удалено дубликатов фото: {count}",
        "log_merged_similar_people": "   - Объединено людей по лицам: {count}",
        "log_no_changes_needed": "База данных не требовала изменений.",
        "log_error_occurred": "❌ ПРОИЗОШЛА ОШИБКА: {e}",
        # Duplicate Photos
        "dup_photos_title": "Найденные дубликаты фотографий",
        "dup_photos_delete_disk": "Физически удалить файлы с диска (НЕОБРАТИМО!)",
        "dup_photos_confirm_button": "Подтвердить удаление",
        "dup_photos_cancel_button": "Отмена",
        "dup_photos_group_title": "Группа {i}",
        "dup_photos_delete_checkbox": "Удалить",
        "dup_photos_load_error": "Ошибка\nзагрузки",
        "dup_photos_no_selection_title": "Нет выбора",
        "dup_photos_no_selection_msg": "Не выбрано ни одного фото для удаления.",
        "dup_photos_confirm_delete_title": "Подтверждение",
        "dup_photos_confirm_delete_msg": "Вы уверены, что хотите НАВСЕГДА удалить файлы с диска?",
        "log_photo_search_start": "\n--- Поиск дубликатов фотографий (может занять время) ---",
        "log_hashing_images": "Хеширование {count} изображений...",
        "log_file_not_found": "  ! Файл не найден, пропуск: {filepath}",
        "log_file_read_error": "  ! Ошибка чтения файла {filepath}: {e}",
        "status_hashing": "Хеширование... {i}/{count}",
        "log_finding_similar": "Поиск схожих изображений...",
        "log_found_photo_groups": "Найдено {count} групп дубликатов. Открытие окна выбора...",
        "log_no_photo_duplicates": "Дубликаты фотографий не найдены.",
        "log_photo_delete_cancelled": "Удаление фотографий отменено пользователем.",
        "log_deleting_photos_from_db": "\nУдаление {count} выбранных фотографий из БД...",
        "log_deleting_dependencies": "  - Удаление зависимых записей...",
        "log_deleted_from_table": "    - Удалено из '{table}': {count}",
        "log_deleting_main_records": "  - Удаление основных записей из 'images'...",
        "log_deleted_main_from_images": "  - Удалено {count} записей из 'images'.",
        "log_deleting_physically": "Физическое удаление файлов с диска...",
        "log_physical_delete_error": "  - Ошибка удаления файла {fpath}: {e}",
        "log_physical_deleted_count": "  - Физически удалено {count} файлов.",
        # Exact Duplicates
        "log_merge_people_start": "\n--- Объединение дубликатов людей (по именам) ---",
        "log_merge_dogs_start": "\n--- Объединение дубликатов собак ---",
        "log_no_duplicates_in_table": "Дубликаты в '{table_name}' не найдены.",
        "log_found_duplicates_in_table": "Найдено {count} групп дубликатов в '{table_name}'.",
        "log_merging_for": "  - Слияние дубликатов для '{name}' (ID: {id_keep}) <- {ids_delete}",
        # Similar Faces
        "merge_similar_title": "Объединение людей со схожими лицами",
        "merge_similar_pair_info": "Пара {current} из {total}. Решите, что делать с этими людьми.",
        "person_1_frame": "Человек 1",
        "person_2_frame": "Человек 2",
        "use_this_data_button_1": "Использовать эти данные ->",
        "use_this_data_button_2": "<- Использовать эти данные",
        "final_data_frame": "Итоговые данные (после слияния)",
        "full_name_label": "Полное имя:",
        "short_name_label": "Короткое имя:",
        "notes_label": "Примечание:",
        "merge_button": "Объединить",
        "skip_button": "Пропустить",
        "finish_button": "Завершить и сохранить",
        "face_examples_label": "Примеры лиц:",
        "name_needed_warning": "Полное имя не может быть пустым.",
        "log_similar_faces_start": "\n--- Поиск людей со схожими лицами ---",
        "status_loading_faces": "Загрузка данных о людях и их лицах...",
        "log_no_known_people": "В базе данных нет известных людей с лицами для анализа.",
        "log_found_known_people": "Найдено {count} известных людей с лицами для анализа.",
        "log_not_enough_people": "Для сравнения необходимо как минимум 2 человека. Анализ пропущен.",
        "status_comparing_faces": "Сравнение лиц...",
        "log_no_potential_pairs": "Потенциально одинаковых людей с разными именами не найдено.",
        "log_found_potential_pairs": "Найдено {count} потенциальных пар. Открытие окна для объединения...",
        "log_merge_cancelled": "Объединение людей отменено или пропущено.",
        "log_performing_merges": "\nВыполнение {count} слияний...",
        "log_merging_ids": "  - Объединение ID {id_d} -> ID {id_k} с именем '{name}'",
    },
    "en": {
        "app_title": "FaceDB Cleaner GUI",
        "language": "Language:",
        "db_frame_title": "Database",
        "browse_button": "Browse...",
        "options_frame_title": "Cleaning Options",
        "merge_people_check": "Merge duplicate people (by exact name match)",
        "merge_dogs_check": "Merge duplicate dogs (by exact data match)",
        "find_photos_check": "Find and delete duplicate photos",
        "photo_threshold_label": "Similarity threshold (0=exact, 10=loose):",
        "find_faces_check": "Find people with similar faces (but different names)",
        "face_threshold_label": "Similarity threshold (lower = stricter):",
        "log_frame_title": "Execution Log",
        "start_button": "🚀 Start Cleaning",
        "copy_log_button": "📋",
        "exit_button": "Exit",
        "status_initial": "Select a file and options to start.",
        "status_db_selected": "Database selected: {filename}",
        "status_log_copied": "Log copied to clipboard.",
        "status_running": "Processing...",
        "status_complete": "Cleaning completed successfully!",
        "status_complete_no_changes": "Cleaning finished. No changes were required.",
        "status_error": "Error! Changes have been rolled back.",
        "error_title": "Error",
        "warning_title": "Warning",
        "info_title": "Information",
        "db_path_error": "Database path is not specified or the file does not exist.",
        "no_options_error": "Select at least one cleaning option.",
        "log_connecting": "Connecting to DB: {db_path}",
        "log_all_changes_saved": "✅ All changes have been saved successfully.",
        "log_merged_people": "   - Merged people by name: {count}",
        "log_merged_dogs": "   - Merged dogs by data: {count}",
        "log_deleted_photos": "   - Deleted duplicate photos: {count}",
        "log_merged_similar_people": "   - Merged people by faces: {count}",
        "log_no_changes_needed": "The database did not require any changes.",
        "log_error_occurred": "❌ AN ERROR OCCURRED: {e}",
        # Duplicate Photos
        "dup_photos_title": "Found Duplicate Photos",
        "dup_photos_delete_disk": "Permanently delete files from disk (IRREVERSIBLE!)",
        "dup_photos_confirm_button": "Confirm Deletion",
        "dup_photos_cancel_button": "Cancel",
        "dup_photos_group_title": "Group {i}",
        "dup_photos_delete_checkbox": "Delete",
        "dup_photos_load_error": "Load\nError",
        "dup_photos_no_selection_title": "No Selection",
        "dup_photos_no_selection_msg": "No photos were selected for deletion.",
        "dup_photos_confirm_delete_title": "Confirmation",
        "dup_photos_confirm_delete_msg": "Are you sure you want to PERMANENTLY delete the files from disk?",
        "log_photo_search_start": "\n--- Searching for duplicate photos (may take a while) ---",
        "log_hashing_images": "Hashing {count} images...",
        "log_file_not_found": "  ! File not found, skipping: {filepath}",
        "log_file_read_error": "  ! Error reading file {filepath}: {e}",
        "status_hashing": "Hashing... {i}/{count}",
        "log_finding_similar": "Finding similar images...",
        "log_found_photo_groups": "Found {count} duplicate groups. Opening selection window...",
        "log_no_photo_duplicates": "No duplicate photos found.",
        "log_photo_delete_cancelled": "Photo deletion was cancelled by the user.",
        "log_deleting_photos_from_db": "\nDeleting {count} selected photos from the DB...",
        "log_deleting_dependencies": "  - Deleting dependent records...",
        "log_deleted_from_table": "    - Deleted from '{table}': {count}",
        "log_deleting_main_records": "  - Deleting main records from 'images'...",
        "log_deleted_main_from_images": "  - Deleted {count} records from 'images'.",
        "log_deleting_physically": "Deleting files from disk...",
        "log_physical_delete_error": "  - Error deleting file {fpath}: {e}",
        "log_physical_deleted_count": "  - Physically deleted {count} files.",
        # Exact Duplicates
        "log_merge_people_start": "\n--- Merging duplicate people (by name) ---",
        "log_merge_dogs_start": "\n--- Merging duplicate dogs ---",
        "log_no_duplicates_in_table": "No duplicates found in '{table_name}'.",
        "log_found_duplicates_in_table": "Found {count} duplicate groups in '{table_name}'.",
        "log_merging_for": "  - Merging duplicates for '{name}' (ID: {id_keep}) <- {ids_delete}",
        # Similar Faces
        "merge_similar_title": "Merge People with Similar Faces",
        "merge_similar_pair_info": "Pair {current} of {total}. Decide what to do with these people.",
        "person_1_frame": "Person 1",
        "person_2_frame": "Person 2",
        "use_this_data_button_1": "Use this data ->",
        "use_this_data_button_2": "<- Use this data",
        "final_data_frame": "Final Data (after merge)",
        "full_name_label": "Full Name:",
        "short_name_label": "Short Name:",
        "notes_label": "Notes:",
        "merge_button": "Merge",
        "skip_button": "Skip",
        "finish_button": "Finish & Save",
        "face_examples_label": "Face samples:",
        "name_needed_warning": "Full name cannot be empty.",
        "log_similar_faces_start": "\n--- Finding people with similar faces ---",
        "status_loading_faces": "Loading data about people and their faces...",
        "log_no_known_people": "No known people with faces found in the database for analysis.",
        "log_found_known_people": "Found {count} known people with faces to analyze.",
        "log_not_enough_people": "At least 2 people are required for comparison. Analysis skipped.",
        "status_comparing_faces": "Comparing faces...",
        "log_no_potential_pairs": "No potential matches with different names found.",
        "log_found_potential_pairs": "Found {count} potential pairs. Opening merge window...",
        "log_merge_cancelled": "Merging people was cancelled or skipped.",
        "log_performing_merges": "\nPerforming {count} merges...",
        "log_merging_ids": "  - Merging ID {id_d} -> ID {id_k} with name '{name}'",
    },
    "it": {
        "app_title": "FaceDB Cleaner GUI",
        "language": "Lingua:",
        "db_frame_title": "Database",
        "browse_button": "Sfoglia...",
        "options_frame_title": "Opzioni di Pulizia",
        "merge_people_check": "Unisci persone duplicate (per corrispondenza esatta del nome)",
        "merge_dogs_check": "Unisci cani duplicati (per corrispondenza esatta dei dati)",
        "find_photos_check": "Trova ed elimina foto duplicate",
        "photo_threshold_label": "Soglia di similarità (0=esatta, 10=approssimativa):",
        "find_faces_check": "Trova persone con volti simili (ma nomi diversi)",
        "face_threshold_label": "Soglia di similarità (più basso = più severo):",
        "log_frame_title": "Log di Esecuzione",
        "start_button": "🚀 Avvia Pulizia",
        "copy_log_button": "📋",
        "exit_button": "Esci",
        "status_initial": "Seleziona un file e le opzioni per iniziare.",
        "status_db_selected": "Database selezionato: {filename}",
        "status_log_copied": "Log copiato negli appunti.",
        "status_running": "Elaborazione...",
        "status_complete": "Pulizia completata con successo!",
        "status_complete_no_changes": "Pulizia terminata. Non sono state necessarie modifiche.",
        "status_error": "Errore! Le modifiche sono state annullate.",
        "error_title": "Errore",
        "warning_title": "Avviso",
        "info_title": "Informazione",
        "db_path_error": "Il percorso del database non è specificato o il file non esiste.",
        "no_options_error": "Seleziona almeno un'opzione di pulizia.",
        "log_connecting": "Connessione al DB: {db_path}",
        "log_all_changes_saved": "✅ Tutte le modifiche sono state salvate con successo.",
        "log_merged_people": "   - Persone unite per nome: {count}",
        "log_merged_dogs": "   - Cani uniti per dati: {count}",
        "log_deleted_photos": "   - Foto duplicate eliminate: {count}",
        "log_merged_similar_people": "   - Persone unite per volti: {count}",
        "log_no_changes_needed": "Il database non ha richiesto modifiche.",
        "log_error_occurred": "❌ SI È VERIFICATO UN ERRORE: {e}",
        # Duplicate Photos
        "dup_photos_title": "Trovate Foto Duplicate",
        "dup_photos_delete_disk": "Elimina permanentemente i file dal disco (IRREVERSIBILE!)",
        "dup_photos_confirm_button": "Conferma Eliminazione",
        "dup_photos_cancel_button": "Annulla",
        "dup_photos_group_title": "Gruppo {i}",
        "dup_photos_delete_checkbox": "Elimina",
        "dup_photos_load_error": "Errore\ndi caricamento",
        "dup_photos_no_selection_title": "Nessuna Selezione",
        "dup_photos_no_selection_msg": "Nessuna foto selezionata per l'eliminazione.",
        "dup_photos_confirm_delete_title": "Conferma",
        "dup_photos_confirm_delete_msg": "Sei sicuro di voler eliminare PERMANENTEMENTE i file dal disco?",
        "log_photo_search_start": "\n--- Ricerca di foto duplicate (potrebbe richiedere tempo) ---",
        "log_hashing_images": "Hashing di {count} immagini...",
        "log_file_not_found": "  ! File non trovato, saltato: {filepath}",
        "log_file_read_error": "  ! Errore durante la lettura del file {filepath}: {e}",
        "status_hashing": "Hashing... {i}/{count}",
        "log_finding_similar": "Ricerca di immagini simili...",
        "log_found_photo_groups": "Trovati {count} gruppi di duplicati. Apertura finestra di selezione...",
        "log_no_photo_duplicates": "Nessuna foto duplicata trovata.",
        "log_photo_delete_cancelled": "Eliminazione foto annullata dall'utente.",
        "log_deleting_photos_from_db": "\nEliminazione di {count} foto selezionate dal DB...",
        "log_deleting_dependencies": "  - Eliminazione dei record dipendenti...",
        "log_deleted_from_table": "    - Eliminati da '{table}': {count}",
        "log_deleting_main_records": "  - Eliminazione dei record principali da 'images'...",
        "log_deleted_main_from_images": "  - Eliminati {count} record da 'images'.",
        "log_deleting_physically": "Eliminazione fisica dei file dal disco...",
        "log_physical_delete_error": "  - Errore nell'eliminazione del file {fpath}: {e}",
        "log_physical_deleted_count": "  - Eliminati fisicamente {count} file.",
        # Exact Duplicates
        "log_merge_people_start": "\n--- Unione di persone duplicate (per nome) ---",
        "log_merge_dogs_start": "\n--- Unione di cani duplicati ---",
        "log_no_duplicates_in_table": "Nessun duplicato trovato in '{table_name}'.",
        "log_found_duplicates_in_table": "Trovati {count} gruppi di duplicati in '{table_name}'.",
        "log_merging_for": "  - Unione duplicati per '{name}' (ID: {id_keep}) <- {ids_delete}",
        # Similar Faces
        "merge_similar_title": "Unisci Persone con Volti Simili",
        "merge_similar_pair_info": "Coppia {current} di {total}. Decidi cosa fare con queste persone.",
        "person_1_frame": "Persona 1",
        "person_2_frame": "Persona 2",
        "use_this_data_button_1": "Usa questi dati ->",
        "use_this_data_button_2": "<- Usa questi dati",
        "final_data_frame": "Dati Finali (dopo unione)",
        "full_name_label": "Nome Completo:",
        "short_name_label": "Nome Breve:",
        "notes_label": "Note:",
        "merge_button": "Unisci",
        "skip_button": "Salta",
        "finish_button": "Fine e Salva",
        "face_examples_label": "Esempi di volti:",
        "name_needed_warning": "Il nome completo non può essere vuoto.",
        "log_similar_faces_start": "\n--- Ricerca di persone con volti simili ---",
        "status_loading_faces": "Caricamento dati su persone e loro volti...",
        "log_no_known_people": "Nessuna persona nota con volti trovata nel database per l'analisi.",
        "log_found_known_people": "Trovate {count} persone note con volti da analizzare.",
        "log_not_enough_people": "Sono necessarie almeno 2 persone per il confronto. Analisi saltata.",
        "status_comparing_faces": "Confronto volti...",
        "log_no_potential_pairs": "Nessuna potenziale corrispondenza con nomi diversi trovata.",
        "log_found_potential_pairs": "Trovate {count} potenziali coppie. Apertura finestra di unione...",
        "log_merge_cancelled": "Unione persone annullata o saltata.",
        "log_performing_merges": "\nEsecuzione di {count} unioni...",
        "log_merging_ids": "  - Unione ID {id_d} -> ID {id_k} con nome '{name}'",
    }
}


# --- DIALOG WINDOWS ---

class DuplicatePhotosDialog(tk.Toplevel):
    def __init__(self, parent, duplicate_groups, lang):
        super().__init__(parent)
        self.duplicate_groups = duplicate_groups
        self.lang = lang
        self.result = {'delete_ids': [], 'delete_files': False}
        self.checkbox_vars = {}
        self.title(self.lang["dup_photos_title"])
        self.geometry("1000x750")

        top_panel = ttk.Frame(self, padding=10)
        top_panel.pack(fill=tk.X, side=tk.TOP)

        self.delete_files_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top_panel, text=self.lang["dup_photos_delete_disk"], variable=self.delete_files_var).pack(side=tk.LEFT)

        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_frame, text=self.lang["dup_photos_confirm_button"], command=self.confirm).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(btn_frame, text=self.lang["dup_photos_cancel_button"], command=self.cancel).pack(side=tk.RIGHT, expand=True, fill=tk.X)

        canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, padding=5)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.populate_duplicates(scrollable_frame)
        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def populate_duplicates(self, parent_frame):
        thumb_size = (150, 150)
        for i, group in enumerate(self.duplicate_groups):
            group_frame = ttk.LabelFrame(parent_frame, text=self.lang["dup_photos_group_title"].format(i=i+1), padding=10)
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
                    ttk.Checkbutton(item_frame, text=self.lang["dup_photos_delete_checkbox"], variable=cb_var).pack()
                    self.checkbox_vars[image_id] = (cb_var, filepath)
                except Exception:
                    error_frame = ttk.Frame(item_frame, width=thumb_size[0], height=thumb_size[1], borderwidth=1, relief="solid")
                    error_frame.pack_propagate(False)
                    error_frame.pack()
                    ttk.Label(error_frame, text=self.lang["dup_photos_load_error"], wraplength=140).pack(expand=True)
                    ttk.Label(item_frame, text=f"{os.path.basename(filepath)}", justify=tk.CENTER).pack()

    def confirm(self):
        self.result['delete_ids'] = [img_id for img_id, (var, _) in self.checkbox_vars.items() if var.get()]
        if not self.result['delete_ids']:
            messagebox.showinfo(self.lang["dup_photos_no_selection_title"], self.lang["dup_photos_no_selection_msg"], parent=self)
            return
        self.result['delete_files'] = self.delete_files_var.get()
        if self.result['delete_files']:
            if not messagebox.askyesno(self.lang["dup_photos_confirm_delete_title"], self.lang["dup_photos_confirm_delete_msg"], icon='warning', parent=self):
                return
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()

class MergeSimilarPeopleDialog(tk.Toplevel):
    def __init__(self, parent, pairs_to_review, person_data, lang):
        super().__init__(parent)
        self.parent = parent
        self.pairs = pairs_to_review
        self.person_data = person_data
        self.lang = lang
        self.current_pair_index = 0
        self.merge_actions = []

        self.title(self.lang["merge_similar_title"])
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
        ttk.Button(btn_frame, text=self.lang["merge_button"], command=self.merge, style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text=self.lang["skip_button"], command=self.skip).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text=self.lang["finish_button"], command=self.finish).pack(side=tk.RIGHT, padx=5)

        self.load_pair()
        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def load_pair(self):
        for widget in self.comparison_frame.winfo_children():
            widget.destroy()

        if self.current_pair_index >= len(self.pairs):
            self.finish()
            return

        self.info_label.config(text=self.lang["merge_similar_pair_info"].format(current=self.current_pair_index + 1, total=len(self.pairs)))
        id1, id2 = self.pairs[self.current_pair_index]
        self.person1_id, self.person2_id = id1, id2

        # --- IMPROVED LAYOUT: 3 COLUMNS ---
        frame1 = self.create_person_frame(self.comparison_frame, self.lang["person_1_frame"], self.person_data[id1])
        frame1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        ttk.Button(frame1, text=self.lang["use_this_data_button_1"], command=lambda: self.populate_form(self.person_data[id1]['info'])).pack(pady=10)

        form_frame = self.create_merge_form(self.comparison_frame)
        form_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        frame2 = self.create_person_frame(self.comparison_frame, self.lang["person_2_frame"], self.person_data[id2])
        frame2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        ttk.Button(frame2, text=self.lang["use_this_data_button_2"], command=lambda: self.populate_form(self.person_data[id2]['info'])).pack(pady=10)

        self.populate_form(self.person_data[id1]['info'])

    def create_person_frame(self, parent, title, data):
        p_frame = ttk.LabelFrame(parent, text=title, padding=10)
        faces_frame = ttk.Frame(p_frame)
        faces_frame.pack(pady=5, fill=tk.X)
        ttk.Label(faces_frame, text=self.lang["face_examples_label"]).pack()
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
        form_frame = ttk.LabelFrame(parent, text=self.lang["final_data_frame"], padding=10)
        ttk.Label(form_frame, text=self.lang["full_name_label"]).grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(form_frame, textvariable=self.full_name_var, width=40).grid(row=0, column=1, sticky=tk.EW, pady=2)
        ttk.Label(form_frame, text=self.lang["short_name_label"]).grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(form_frame, textvariable=self.short_name_var, width=40).grid(row=1, column=1, sticky=tk.EW, pady=2)
        ttk.Label(form_frame, text=self.lang["notes_label"]).grid(row=2, column=0, sticky=tk.NW, pady=2)
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
            messagebox.showwarning(self.lang["warning_title"], self.lang["name_needed_warning"], parent=self)
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

# --- MAIN APPLICATION CLASS ---

class FaceDBCleanerGUI:
    def __init__(self, root):
        self.root = root
        self.root.geometry("800x680")
        self.root.minsize(700, 600)

        # --- UI/UX Improvements: Styles and Theme ---
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            pass  # Use default theme if 'clam' is not available
        self.style.configure('TLabelFrame.Label', font=('Arial', 10, 'bold'))
        self.style.configure('Status.TLabel', font=('Arial', 10, 'bold'), padding=5)
        self.style.configure('Idle.Status.TLabel', background='lightblue', foreground='black')
        self.style.configure('Processing.Status.TLabel', background='lightyellow', foreground='black')
        self.style.configure('Complete.Status.TLabel', background='lightgreen', foreground='black')
        self.style.configure('Error.Status.TLabel', background='lightcoral', foreground='black')
        self.style.configure('Accent.TButton', font=('Arial', 10, 'bold'), foreground='navy')

        # --- Language and State Variables ---
        self.db_path = tk.StringVar()
        self.is_running = False
        self.current_language = tk.StringVar(value="en")
        self.lang = TRANSLATIONS[self.current_language.get()]
        self.current_language.trace_add('write', self.change_language)

        # --- Option Variables ---
        self.clean_people_var = tk.BooleanVar(value=True)
        self.clean_dogs_var = tk.BooleanVar(value=True)
        self.clean_photos_var = tk.BooleanVar(value=False)
        self.clean_similar_faces_var = tk.BooleanVar(value=False)
        self.photo_hash_threshold = tk.IntVar(value=5)
        self.face_similarity_threshold = tk.DoubleVar(value=0.5)

        self.create_widgets()
        self.retranslate_ui() # Apply initial translation
        self.update_status("status_initial")

    def create_widgets(self):
        self.main_pane = ttk.Frame(self.root, padding=10)
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        # --- Top panel: Language and Version ---
        self.header_frame = ttk.Frame(self.main_pane)
        self.header_frame.pack(side=tk.TOP, fill=tk.X, anchor=tk.N, pady=(0, 5))
        
        # Version label on the right
        self.version_label = ttk.Label(self.header_frame, text=f"v{VERSION}", font=('Arial', 8, 'italic'))
        self.version_label.pack(side=tk.RIGHT)
        
        # Language selector to the left of version
        self.lang_frame = ttk.Frame(self.header_frame)
        self.lang_frame.pack(side=tk.RIGHT, padx=(0, 10))
        self.lang_label = ttk.Label(self.lang_frame, text="Language:")
        self.lang_label.pack(side=tk.LEFT, padx=(0, 5))
        self.lang_combo = ttk.Combobox(self.lang_frame, textvariable=self.current_language, values=["ru", "en", "it"], width=5, state="readonly")
        self.lang_combo.pack(side=tk.LEFT)

        # --- DB selection panel ---
        self.db_frame = ttk.LabelFrame(self.main_pane, padding=10)
        self.db_frame.pack(side=tk.TOP, fill=tk.X)
        self.db_frame.columnconfigure(0, weight=1)
        self.db_entry = ttk.Entry(self.db_frame, textvariable=self.db_path, width=70)
        self.db_entry.grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))
        self.browse_btn = ttk.Button(self.db_frame, command=self.browse_db)
        self.browse_btn.grid(row=0, column=1)

        # --- Options panel ---
        self.options_frame = ttk.LabelFrame(self.main_pane, padding=10)
        self.options_frame.pack(fill=tk.X, pady=10)

        self.merge_people_check = ttk.Checkbutton(self.options_frame, variable=self.clean_people_var)
        self.merge_people_check.pack(anchor=tk.W, pady=2)
        self.merge_dogs_check = ttk.Checkbutton(self.options_frame, variable=self.clean_dogs_var)
        self.merge_dogs_check.pack(anchor=tk.W, pady=2)

        # --- Duplicate photos options ---
        photo_frame = ttk.Frame(self.options_frame)
        photo_frame.pack(fill=tk.X, anchor=tk.W, pady=(8,0))
        self.find_photos_check = ttk.Checkbutton(photo_frame, variable=self.clean_photos_var)
        self.find_photos_check.pack(side=tk.LEFT)
        self.photo_thresh_lbl = ttk.Label(photo_frame)
        self.photo_thresh_lbl.pack(side=tk.LEFT, padx=(20, 5))
        ttk.Scale(photo_frame, from_=0, to=10, variable=self.photo_hash_threshold, orient=tk.HORIZONTAL, length=150, command=lambda v: self.photo_hash_threshold.set(int(float(v)))).pack(side=tk.LEFT)
        ttk.Label(photo_frame, textvariable=self.photo_hash_threshold, font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=5)

        # --- Similar faces options ---
        face_sim_frame = ttk.Frame(self.options_frame)
        face_sim_frame.pack(fill=tk.X, anchor=tk.W, pady=(5,0))
        self.find_faces_check = ttk.Checkbutton(face_sim_frame, variable=self.clean_similar_faces_var)
        self.find_faces_check.pack(side=tk.LEFT)
        self.face_thresh_lbl = ttk.Label(face_sim_frame)
        self.face_thresh_lbl.pack(side=tk.LEFT, padx=(20, 5))
        ttk.Scale(face_sim_frame, from_=0.3, to=0.7, variable=self.face_similarity_threshold, orient=tk.HORIZONTAL, length=150).pack(side=tk.LEFT)
        face_thr_label = ttk.Label(face_sim_frame, text=f"{self.face_similarity_threshold.get():.2f}", font=('Arial', 10, 'bold'))
        face_thr_label.pack(side=tk.LEFT, padx=5)
        self.face_similarity_threshold.trace_add('write', lambda *args: face_thr_label.config(text=f"{self.face_similarity_threshold.get():.2f}"))

        # --- Log and control panel ---
        self.log_frame = ttk.LabelFrame(self.main_pane, padding=10)
        self.log_frame.pack(fill=tk.BOTH, expand=True)

        control_frame = ttk.Frame(self.log_frame)
        control_frame.pack(fill=tk.X, pady=(0, 5))
        self.start_btn = ttk.Button(control_frame, command=self.start_cleaning, style="Accent.TButton")
        self.start_btn.pack(side=tk.LEFT)
        
        self.copy_btn = ttk.Button(control_frame, text="📋", command=self.copy_log_to_clipboard)
        self.copy_btn.pack(side=tk.RIGHT)

        self.log_text = scrolledtext.ScrolledText(self.log_frame, wrap=tk.WORD, state=tk.DISABLED, relief=tk.SOLID, borderwidth=1)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Bottom frame for status bar and exit button
        self.bottom_frame = ttk.Frame(self.root)
        self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_label = ttk.Label(self.bottom_frame, text="", relief=tk.SUNKEN, anchor=tk.W, style="Idle.Status.TLabel")
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.exit_btn = ttk.Button(self.bottom_frame, command=self.root.destroy)
        self.exit_btn.pack(side=tk.RIGHT, padx=5, pady=2)
    
    def change_language(self, *args):
        """Called when the language is changed via the combobox."""
        new_lang_code = self.current_language.get()
        self.lang = TRANSLATIONS[new_lang_code]
        self.retranslate_ui()

    def retranslate_ui(self):
        """Update all UI text elements with the current language."""
        self.root.title(self.lang["app_title"])
        # self.lang_label is now static, no translation needed.
        self.db_frame.config(text=self.lang["db_frame_title"])
        self.browse_btn.config(text=self.lang["browse_button"])
        self.options_frame.config(text=self.lang["options_frame_title"])
        self.merge_people_check.config(text=self.lang["merge_people_check"])
        self.merge_dogs_check.config(text=self.lang["merge_dogs_check"])
        self.find_photos_check.config(text=self.lang["find_photos_check"])
        self.photo_thresh_lbl.config(text=self.lang["photo_threshold_label"])
        self.find_faces_check.config(text=self.lang["find_faces_check"])
        self.face_thresh_lbl.config(text=self.lang["face_threshold_label"])
        self.log_frame.config(text=self.lang["log_frame_title"])
        self.start_btn.config(text=self.lang["start_button"])
        self.exit_btn.config(text=self.lang["exit_button"])
        # Retranslate the status bar if it's in its initial state
        if self.status_label.cget("text") == TRANSLATIONS["ru"]["status_initial"] or \
           self.status_label.cget("text") == TRANSLATIONS["en"]["status_initial"] or \
           self.status_label.cget("text") == TRANSLATIONS["it"]["status_initial"]:
           self.update_status("status_initial")

    def update_status(self, key, **kwargs):
        message = self.lang[key].format(**kwargs)
        self.status_label.config(text=message)
        
        style_type = 'idle'
        if key.startswith("status_running") or key.startswith("status_hashing") or key.startswith("status_loading") or key.startswith("status_comparing"):
            style_type = 'processing'
        elif key.startswith("status_complete"):
            style_type = 'complete'
        elif key.startswith("status_error"):
            style_type = 'error'

        style_map = {'idle': 'Idle.Status.TLabel', 'processing': 'Processing.Status.TLabel',
                     'complete': 'Complete.Status.TLabel', 'error': 'Error.Status.TLabel'}
        self.status_label.config(style=style_map.get(style_type, 'Idle.Status.TLabel'))

    def copy_log_to_clipboard(self):
        content = self.log_text.get('1.0', tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.update_status("status_log_copied")

    def browse_db(self):
        if self.is_running: return
        filename = filedialog.askopenfilename(title=self.lang["db_frame_title"], filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")])
        if filename:
            self.db_path.set(filename)
            self.update_status("status_db_selected", filename=os.path.basename(filename))

    def log(self, key, prefix="", suffix="", **kwargs):
        message = self.lang[key].format(**kwargs)
        full_message = prefix + message + suffix
        self.root.after(0, self._log_threadsafe, full_message)

    def _log_threadsafe(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def start_cleaning(self):
        if self.is_running: return
        db_path_val = self.db_path.get()
        if not db_path_val or not os.path.exists(db_path_val):
            messagebox.showerror(self.lang["error_title"], self.lang["db_path_error"])
            return
        if not any([self.clean_people_var.get(), self.clean_dogs_var.get(), self.clean_photos_var.get(), self.clean_similar_faces_var.get()]):
            messagebox.showwarning(self.lang["warning_title"], self.lang["no_options_error"])
            return

        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete('1.0', tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.update_status("status_running")

        thread = threading.Thread(target=self.cleaning_thread, args=(db_path_val,), daemon=True)
        thread.start()

    def cleaning_thread(self, db_path_val):
        conn = None
        try:
            self.log("log_connecting", db_path=db_path_val)
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
                self.log("log_all_changes_saved", prefix="\n------------------------------------\n")
                if results['exact_persons'] > 0: self.log("log_merged_people", count=results['exact_persons'])
                if results['dogs'] > 0: self.log("log_merged_dogs", count=results['dogs'])
                if results['photos'] > 0: self.log("log_deleted_photos", count=results['photos'])
                if results['similar_persons'] > 0: self.log("log_merged_similar_people", count=results['similar_persons'])
                self.log("log_all_changes_saved", prefix="------------------------------------") # Just for the line
                self.update_status("status_complete")
            else:
                self.log("log_no_changes_needed", prefix="\n------------------------------------\n", suffix="\n------------------------------------")
                self.update_status("status_complete_no_changes")

        except Exception as e:
            self.log("log_error_occurred", e=e, prefix="\n")
            self.root.after(0, lambda: self.log_text.insert(tk.END, traceback.format_exc()))
            if conn:
                conn.rollback()
                self.update_status("status_error")
        finally:
            if conn:
                conn.close()
            self.is_running = False
            self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL))

    def process_photo_duplicates(self, cursor):
        self.log("log_photo_search_start")
        cursor.execute("SELECT id, filepath, 0, 0, file_size FROM images")
        all_images = cursor.fetchall()
        hashes = {}
        self.log("log_hashing_images", count=len(all_images))

        for i, (img_id, filepath, _, _, _) in enumerate(all_images):
            if not os.path.exists(filepath):
                self.log("log_file_not_found", filepath=filepath)
                continue
            try:
                with Image.open(filepath) as img:
                    img_hash = imagehash.phash(img)
                if img_hash not in hashes:
                    hashes[img_hash] = []
                hashes[img_hash].append(img_id)
            except Exception as e:
                self.log("log_file_read_error", filepath=filepath, e=e)
                continue
            if (i + 1) % 50 == 0:
                self.update_status("status_hashing", i=i+1, count=len(all_images))

        self.log("log_finding_similar")
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

            if len(current_group_hashes) > 1 or any(len(hashes[h]) > 1 for h in current_group_hashes):
                image_ids_in_group = [img_id for h in current_group_hashes for img_id in hashes[h]]
                processed_hashes.update(current_group_hashes)
                placeholders = ','.join('?' * len(image_ids_in_group))
                cursor.execute(f"SELECT id, filepath, 0, 0, file_size FROM images WHERE id IN ({placeholders})", image_ids_in_group)
                groups.append(cursor.fetchall())

        if not groups:
            self.log("log_no_photo_duplicates")
            return 0

        self.log("log_found_photo_groups", count=len(groups))
        dialog_result = None
        event = threading.Event()

        def run_dialog():
            nonlocal dialog_result
            dialog = DuplicatePhotosDialog(self.root, groups, self.lang)
            self.root.wait_window(dialog)
            dialog_result = dialog.result
            event.set()

        self.root.after(0, run_dialog)
        event.wait()

        if not dialog_result or not dialog_result['delete_ids']:
            self.log("log_photo_delete_cancelled")
            return 0

        ids_to_delete = dialog_result['delete_ids']
        self.log("log_deleting_photos_from_db", count=len(ids_to_delete))
        placeholders = ','.join('?' * len(ids_to_delete))

        paths_to_delete_physically = []
        if dialog_result['delete_files']:
            cursor.execute(f"SELECT filepath FROM images WHERE id IN ({placeholders})", ids_to_delete)
            paths_to_delete_physically = [row[0] for row in cursor.fetchall()]

        self.log("log_deleting_dependencies")
        
        cursor.execute(f"DELETE FROM person_detections WHERE image_id IN ({placeholders})", ids_to_delete)
        self.log("log_deleted_from_table", table="person_detections", count=cursor.rowcount)

        cursor.execute(f"DELETE FROM face_encodings WHERE image_id IN ({placeholders})", ids_to_delete)
        self.log("log_deleted_from_table", table="face_encodings", count=cursor.rowcount)

        cursor.execute(f"DELETE FROM dog_detections WHERE image_id IN ({placeholders})", ids_to_delete)
        self.log("log_deleted_from_table", table="dog_detections", count=cursor.rowcount)

        self.log("log_deleting_main_records")
        cursor.execute(f"DELETE FROM images WHERE id IN ({placeholders})", ids_to_delete)
        self.log("log_deleted_main_from_images", count=cursor.rowcount)

        if paths_to_delete_physically:
            self.log("log_deleting_physically")
            deleted_count = 0
            for fpath in paths_to_delete_physically:
                try:
                    if os.path.exists(fpath):
                        os.remove(fpath)
                        deleted_count += 1
                except OSError as e:
                    self.log("log_physical_delete_error", fpath=fpath, e=e)
            self.log("log_physical_deleted_count", count=deleted_count)
        return len(ids_to_delete)

    def merge_exact_duplicates(self, cursor, table_name='persons'):
        if table_name == 'persons':
            self.log("log_merge_people_start")
            group_by_fields, id_field, name_field = ["full_name", "short_name"], "person_id", "full_name"
            update_tables = ["person_detections", "face_encodings"]
        elif table_name == 'dogs':
            self.log("log_merge_dogs_start")
            group_by_fields, id_field, name_field = ["name", "breed", "owner"], "dog_id", "name"
            update_tables = ["dog_detections"]
        else: return 0

        group_by_sql = ", ".join([f"lower(trim(COALESCE({field},'')))" for field in group_by_fields])
        cursor.execute(f"SELECT group_concat(id) FROM {table_name} WHERE is_known = 1 AND {name_field} IS NOT NULL AND trim({name_field}) != '' GROUP BY {group_by_sql} HAVING count(*) > 1")
        duplicates = cursor.fetchall()

        if not duplicates:
            self.log("log_no_duplicates_in_table", table_name=table_name)
            return 0

        total_merged_count = 0
        self.log("log_found_duplicates_in_table", count=len(duplicates), table_name=table_name)

        for (ids_str,) in duplicates:
            ids = sorted([int(id_val) for id_val in ids_str.split(',')])
            id_to_keep, ids_to_delete = ids[0], ids[1:]
            cursor.execute(f"SELECT {name_field} FROM {table_name} WHERE id = ?", (id_to_keep,))
            name = cursor.fetchone()[0]
            self.log("log_merging_for", name=name, id_keep=id_to_keep, ids_delete=ids_to_delete)
            placeholders = ','.join('?' * len(ids_to_delete))

            for update_table in update_tables:
                cursor.execute(f"UPDATE {update_table} SET {id_field} = ? WHERE {id_field} IN ({placeholders})", [id_to_keep] + ids_to_delete)
            cursor.execute(f"DELETE FROM {table_name} WHERE id IN ({placeholders})", ids_to_delete)
            total_merged_count += len(ids_to_delete)
        return total_merged_count

    def process_similar_faces(self, cursor):
        self.log("log_similar_faces_start")
        self.update_status("status_loading_faces")

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
            self.log("log_no_known_people")
            return 0

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

        self.log("log_found_known_people", count=len(person_data))
        if len(person_data) < 2:
            self.log("log_not_enough_people")
            return 0

        avg_encodings = {pid: np.mean([f['encoding'] for f in data['faces']], axis=0) for pid, data in person_data.items() if data['faces']}

        self.update_status("status_comparing_faces")
        person_ids = list(avg_encodings.keys())
        pairs_to_review = []
        threshold = self.face_similarity_threshold.get()

        for i in range(len(person_ids)):
            for j in range(i + 1, len(person_ids)):
                id1, id2 = person_ids[i], person_ids[j]
                if np.linalg.norm(avg_encodings[id1] - avg_encodings[id2]) < threshold:
                    pairs_to_review.append((id1, id2))

        if not pairs_to_review:
            self.log("log_no_potential_pairs")
            return 0

        self.log("log_found_potential_pairs", count=len(pairs_to_review))
        dialog = None
        event = threading.Event()
        def run_dialog():
            nonlocal dialog
            dialog = MergeSimilarPeopleDialog(self.root, pairs_to_review, person_data, self.lang)
            self.root.wait_window(dialog)
            event.set()
        self.root.after(0, run_dialog)
        event.wait()

        if not dialog or not dialog.merge_actions:
            self.log("log_merge_cancelled")
            return 0

        self.log("log_performing_merges", count=len(dialog.merge_actions))
        merged_count = 0
        for action in dialog.merge_actions:
            id_k, id_d = action['id_to_keep'], action['id_to_delete']
            self.log("log_merging_ids", id_d=id_d, id_k=id_k, name=action['full_name'])
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