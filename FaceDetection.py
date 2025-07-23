"""
Face Detection v3.10
A program to recognize and catalog people and dogs in photographs.

Version: 3.10
- Added multilingual support for the user interface.
  - Users can now switch between English (EN), Russian (RU), and Italian (IT).
  - All UI elements, including labels, buttons, window titles, and dialogs,
    are dynamically translated.
- All code comments have been reviewed and standardized in English.
- The program version has been updated to 3.10.

Version: 3.9.1en
- Full translation of the entire user interface, comments, and log messages
  from Russian to English.

Version: 3.9
- Integrated the dog recognition system from DogRecognizerCPU (based on Torchvision).
  - Dog detection is now performed by a Faster R-CNN model, and breed
    classification by DenseNet-121, significantly improving accuracy.
- The "Breed" field in the dog identification dialog is now auto-filled
  based on the classifier's results.
- Added feedback for model downloads on first launch:
  - A percentage progress bar is shown in the log for Torchvision models.
  - A warning message is displayed for YOLO model downloads.
- YOLO is now used exclusively for detecting people.
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
import sys

# Imports for dog recognition
import torch
from torchvision import transforms
from torchvision.models import detection as tv_det, densenet as tv_cls

# Program Version
VERSION = "3.10"

# --- Localization ---
# All user-facing strings are stored here, organized by language.
localization = {
    'EN': {
        # Main Window
        'window_title': f"Face Detection v{VERSION} - Person and Dog Recognition",
        'scan_tab': "Scanning",
        'people_db_tab': "People Database",
        'dogs_db_tab': "Dogs Database",
        'scan_settings_frame': "Scan Settings",
        'photo_dir_label': "Photo Directory:",
        'include_subdirs_check': "Include subdirectories",
        'active_db_label': "Active DB:",
        'ref_db_label': "Reference DB (vectors):",
        'browse_button': "Browse...",
        'create_new_button': "Create New...",
        'clear_button': "Clear",
        'face_model_label': "Face Recognition Model:",
        'face_model_fast': "HOG (fast)",
        'face_model_accurate': "CNN (accurate)",
        'face_threshold_label': "Face Similarity Threshold:",
        'threshold_note': "(lower = stricter comparison)",
        'yolo_model_label': "YOLO Model (for people):",
        'yolo_nano': "Nano (fastest)", 'yolo_small': "Small (balanced)", 'yolo_medium': "Medium (accurate)", 'yolo_large': "Large (very accurate)", 'yolo_extra': "Extra (max accuracy)",
        'yolo_confidence_label': "YOLO Confidence (People):",
        'confidence_note': "(higher = stricter detection)",
        'dog_threshold_label': "Dog Detection Threshold (Torch):",
        'dog_threshold_note': "(probability that object is a dog)",
        'reprocessing_frame': "Re-processing Behavior",
        'reprocess_skip': "Do not process (skip)",
        'reprocess_process': "Process again",
        'reprocess_ask': "Ask for each image",
        'start_scan_button': "🚀 Start Scan",
        'stop_button': "🛑 Stop",
        'exit_button': "Exit",
        'status_ready': "Ready. Please select or create a DB.",
        'status_ready_db': "DB loaded. Ready to scan.",
        'status_ready_torch': f"Ready. Torch device: {{device}}",
        'status_new_db': "New DB created. Ready to scan.",
        'status_processing': "Processing {current}/{total}: {filename}",
        'status_stopping': "Stopping...",
        'status_complete': "Processing complete",
        'status_error': "Error!",
        'status_initializing': "Initializing...",
        'status_loading_yolo': "Downloading YOLO: {model}...",
        'status_loading_dog_models': "Loading dog recognition models...",
        'current_image_frame': "Current Image",
        'log_frame': "Processing Log",
        'language_label': "Language:",
        # People/Dogs DB Tabs
        'refresh_button': "Refresh",
        'edit_button': "Edit",
        'delete_button': "Delete",
        # People Tree
        'people_col_id': 'ID', 'people_col_status': 'Status', 'people_col_fullname': 'Full Name', 'people_col_shortname': 'Short Name', 'people_col_photos': 'Photos', 'people_col_notes': 'Notes',
        # Dogs Tree
        'dogs_col_id': 'ID', 'dogs_col_status': 'Status', 'dogs_col_name': 'Name', 'dogs_col_breed': 'Breed', 'dogs_col_owner': 'Owner', 'dogs_col_photos': 'Photos', 'dogs_col_notes': 'Notes',
        # Dialogs
        'person_dialog_title': "Person Identification",
        'dog_dialog_title': "Dog Identification",
        'body_dialog_title': "Person without a Recognizable Face",
        'confirm_dialog_title': "Match Found in Reference DB",
        'processed_dialog_title': "Image Already Processed",
        # Person Dialog
        'new_person_detected': "New person detected", 'new_person_tab': "New Person", 'select_from_db_tab': "Select from DB", 'select_from_ref_db_tab': "Select from Ref DB",
        'full_name_label': "Full Name:", 'short_name_label': "Short Name:", 'notes_label': "Notes:", 'save_known_button': "Save as Known", 'leave_unknown_button': "Leave as Unknown", 'cancel_button': "Cancel",
        # Dog Dialog
        'new_dog_detected': "Dog detected", 'new_dog_tab': "New Dog", 'dog_name_label': "Name:", 'dog_breed_label': "Breed:", 'dog_owner_label': "Owner:",
        # Body Dialog
        'body_detected': "Person without a recognizable face", 'enter_data_tab': "Enter Data (Locally)", 'save_info_button': "Save Information", 'skip_button': "Skip (Unknown)",
        # Confirm Dialog
        'match_found': "A possible match was found!", 'ref_db_info': "Information from Reference DB", 'is_same_person': "Is this the same person?", 'confirm_match_button': "Yes, it's a match", 'reject_match_button': "No, different person",
        # Processed Dialog
        'image_processed_before': "The image '{filename}' has been processed before.\nProcess it again?", 'apply_to_all_check': "Apply this decision to all subsequent images", 'yes_process_button': "Yes, Process", 'no_skip_button': "No, Skip",
        # Messages
        'select_db_title': "Select Active Database", 'create_db_title': "Create New Database", 'select_ref_db_title': "Select Reference Database", 'select_photo_dir_title': "Select Photo Directory",
        'error_title': "Error", 'warning_title': "Warning", 'success_title': "Success", 'info_title': "Not Implemented",
        'db_create_error': "Could not create or update the database: {e}", 'db_structure_error': "The database structure is incorrect, even after an update attempt.",
        'db_load_error': "The selected database file has an invalid structure.",
        'select_db_prompt': "Please select or create a database file.", 'select_dir_prompt': "Please specify a directory with photos.",
        'enter_full_name_prompt': "Please enter a full name.", 'select_person_prompt': "Please select a person from the list.",
        'person_exists_prompt': "A person with these names already exists in the database:\n\nFull Name: {full_name}\nShort Name: {short_name}\n\nIf this is a different person, change the name. If it's the same person, select them from the appropriate tab.",
        'enter_dog_name_prompt': "Please enter the dog's name.", 'select_dog_prompt': "Please select a dog from the list.",
        'dog_exists_prompt': "A dog with this information already exists in the DB:\nName: {name}\nBreed: {breed}\nOwner: {owner}",
        'enter_body_name_prompt': "Please enter a full name or click 'Skip'.",
        'edit_unimplemented': "The edit function is under development.",
        'delete_person_confirm': "Are you sure you want to delete this person and all related data? This action cannot be undone.", 'delete_person_success': "Person deleted successfully.", 'delete_person_fail': "Deletion failed: {e}",
        'delete_dog_confirm': "Are you sure you want to delete this dog and all related data? This action cannot be undone.", 'delete_dog_success': "Dog deleted successfully.", 'delete_dog_fail': "Deletion failed: {e}",
    },
    'RU': {
        # Main Window
        'window_title': f"Распознавание лиц v{VERSION} - Каталогизатор людей и собак",
        'scan_tab': "Сканирование",
        'people_db_tab': "База людей",
        'dogs_db_tab': "База собак",
        'scan_settings_frame': "Настройки сканирования",
        'photo_dir_label': "Каталог с фото:",
        'include_subdirs_check': "Включая подкаталоги",
        'active_db_label': "Активная БД:",
        'ref_db_label': "БД для сверки (векторы):",
        'browse_button': "Обзор...",
        'create_new_button': "Создать...",
        'clear_button': "Очистить",
        'face_model_label': "Модель распознавания лиц:",
        'face_model_fast': "HOG (быстрая)",
        'face_model_accurate': "CNN (точная)",
        'face_threshold_label': "Порог схожести лиц:",
        'threshold_note': "(чем ниже, тем строже сравнение)",
        'yolo_model_label': "Модель YOLO (для людей):",
        'yolo_nano': "Nano (самая быстрая)", 'yolo_small': "Small (сбалансированная)", 'yolo_medium': "Medium (точная)", 'yolo_large': "Large (очень точная)", 'yolo_extra': "Extra (макс. точность)",
        'yolo_confidence_label': "Уверенность YOLO (люди):",
        'confidence_note': "(чем выше, тем строже детекция)",
        'dog_threshold_label': "Порог детекции собак (Torch):",
        'dog_threshold_note': "(вероятность, что объект - собака)",
        'reprocessing_frame': "Поведение при повторной обработке",
        'reprocess_skip': "Не обрабатывать (пропускать)",
        'reprocess_process': "Обработать заново",
        'reprocess_ask': "Спрашивать для каждого изображения",
        'start_scan_button': "🚀 Начать сканирование",
        'stop_button': "🛑 Стоп",
        'exit_button': "Выход",
        'status_ready': "Готово. Выберите или создайте БД.",
        'status_ready_db': "БД загружена. Готово к сканированию.",
        'status_ready_torch': f"Готово. Устройство Torch: {{device}}",
        'status_new_db': "Новая БД создана. Готово к сканированию.",
        'status_processing': "Обработка {current}/{total}: {filename}",
        'status_stopping': "Остановка...",
        'status_complete': "Обработка завершена",
        'status_error': "Ошибка!",
        'status_initializing': "Инициализация...",
        'status_loading_yolo': "Загрузка YOLO: {model}...",
        'status_loading_dog_models': "Загрузка моделей для собак...",
        'current_image_frame': "Текущее изображение",
        'log_frame': "Журнал обработки",
        'language_label': "Язык:",
        # People/Dogs DB Tabs
        'refresh_button': "Обновить",
        'edit_button': "Изменить",
        'delete_button': "Удалить",
        # People Tree
        'people_col_id': 'ID', 'people_col_status': 'Статус', 'people_col_fullname': 'Полное имя', 'people_col_shortname': 'Краткое имя', 'people_col_photos': 'Фото', 'people_col_notes': 'Заметки',
        # Dogs Tree
        'dogs_col_id': 'ID', 'dogs_col_status': 'Статус', 'dogs_col_name': 'Кличка', 'dogs_col_breed': 'Порода', 'dogs_col_owner': 'Владелец', 'dogs_col_photos': 'Фото', 'dogs_col_notes': 'Заметки',
        # Dialogs
        'person_dialog_title': "Идентификация человека",
        'dog_dialog_title': "Идентификация собаки",
        'body_dialog_title': "Человек без распознаваемого лица",
        'confirm_dialog_title': "Найдено совпадение в БД для сверки",
        'processed_dialog_title': "Изображение уже обработано",
        # Person Dialog
        'new_person_detected': "Обнаружен новый человек", 'new_person_tab': "Новый человек", 'select_from_db_tab': "Выбрать из БД", 'select_from_ref_db_tab': "Выбрать из БД для сверки",
        'full_name_label': "Полное имя:", 'short_name_label': "Краткое имя:", 'notes_label': "Заметки:", 'save_known_button': "Сохранить как известного", 'leave_unknown_button': "Оставить неизвестным", 'cancel_button': "Отмена",
        # Dog Dialog
        'new_dog_detected': "Обнаружена собака", 'new_dog_tab': "Новая собака", 'dog_name_label': "Кличка:", 'dog_breed_label': "Порода:", 'dog_owner_label': "Владелец:",
        # Body Dialog
        'body_detected': "Человек без распознаваемого лица", 'enter_data_tab': "Ввести данные (локально)", 'save_info_button': "Сохранить информацию", 'skip_button': "Пропустить (неизвестный)",
        # Confirm Dialog
        'match_found': "Найдено возможное совпадение!", 'ref_db_info': "Информация из БД для сверки", 'is_same_person': "Это тот же самый человек?", 'confirm_match_button': "Да, это он", 'reject_match_button': "Нет, другой человек",
        # Processed Dialog
        'image_processed_before': "Изображение '{filename}' уже было обработано.\nОбработать его снова?", 'apply_to_all_check': "Применить это решение ко всем последующим изображениям", 'yes_process_button': "Да, обработать", 'no_skip_button': "Нет, пропустить",
        # Messages
        'select_db_title': "Выберите активную базу данных", 'create_db_title': "Создать новую базу данных", 'select_ref_db_title': "Выберите БД для сверки", 'select_photo_dir_title': "Выберите каталог с фото",
        'error_title': "Ошибка", 'warning_title': "Внимание", 'success_title': "Успех", 'info_title': "Не реализовано",
        'db_create_error': "Не удалось создать или обновить базу данных: {e}", 'db_structure_error': "Структура базы данных некорректна, даже после попытки обновления.",
        'db_load_error': "Выбранный файл БД имеет неверную структуру.",
        'select_db_prompt': "Пожалуйста, выберите или создайте файл базы данных.", 'select_dir_prompt': "Пожалуйста, укажите каталог с фотографиями.",
        'enter_full_name_prompt': "Пожалуйста, введите полное имя.", 'select_person_prompt': "Пожалуйста, выберите человека из списка.",
        'person_exists_prompt': "Человек с такими именами уже существует в базе данных:\n\nПолное имя: {full_name}\nКраткое имя: {short_name}\n\nЕсли это другой человек, измените имя. Если это тот же человек, выберите его на соответствующей вкладке.",
        'enter_dog_name_prompt': "Пожалуйста, введите кличку собаки.", 'select_dog_prompt': "Пожалуйста, выберите собаку из списка.",
        'dog_exists_prompt': "Собака с такой информацией уже существует в БД:\nКличка: {name}\nПорода: {breed}\nВладелец: {owner}",
        'enter_body_name_prompt': "Пожалуйста, введите полное имя или нажмите 'Пропустить'.",
        'edit_unimplemented': "Функция редактирования находится в разработке.",
        'delete_person_confirm': "Вы уверены, что хотите удалить этого человека и все связанные данные? Это действие нельзя отменить.", 'delete_person_success': "Человек успешно удален.", 'delete_person_fail': "Ошибка удаления: {e}",
        'delete_dog_confirm': "Вы уверены, что хотите удалить эту собаку и все связанные данные? Это действие нельзя отменить.", 'delete_dog_success': "Собака успешно удалена.", 'delete_dog_fail': "Ошибка удаления: {e}",
    },
    'IT': {
        # Main Window
        'window_title': f"Rilevamento volti v{VERSION} - Riconoscimento di persone e cani",
        'scan_tab': "Scansione",
        'people_db_tab': "Database Persone",
        'dogs_db_tab': "Database Cani",
        'scan_settings_frame': "Impostazioni di Scansione",
        'photo_dir_label': "Cartella Foto:",
        'include_subdirs_check': "Includi sottocartelle",
        'active_db_label': "DB Attivo:",
        'ref_db_label': "DB di Riferimento (vettori):",
        'browse_button': "Sfoglia...",
        'create_new_button': "Crea Nuovo...",
        'clear_button': "Pulisci",
        'face_model_label': "Modello Riconoscimento Facciale:",
        'face_model_fast': "HOG (veloce)",
        'face_model_accurate': "CNN (preciso)",
        'face_threshold_label': "Soglia di Similarità Facciale:",
        'threshold_note': "(più basso = confronto più rigoroso)",
        'yolo_model_label': "Modello YOLO (per persone):",
        'yolo_nano': "Nano (più veloce)", 'yolo_small': "Small (bilanciato)", 'yolo_medium': "Medium (preciso)", 'yolo_large': "Large (molto preciso)", 'yolo_extra': "Extra (massima precisione)",
        'yolo_confidence_label': "Confidenza YOLO (Persone):",
        'confidence_note': "(più alto = rilevamento più rigoroso)",
        'dog_threshold_label': "Soglia Rilevamento Cani (Torch):",
        'dog_threshold_note': "(probabilità che l'oggetto sia un cane)",
        'reprocessing_frame': "Comportamento Rielaborazione",
        'reprocess_skip': "Non elaborare (salta)",
        'reprocess_process': "Elabora di nuovo",
        'reprocess_ask': "Chiedi per ogni immagine",
        'start_scan_button': "🚀 Avvia Scansione",
        'stop_button': "🛑 Ferma",
        'exit_button': "Esci",
        'status_ready': "Pronto. Seleziona o crea un DB.",
        'status_ready_db': "DB caricato. Pronto per la scansione.",
        'status_ready_torch': f"Pronto. Dispositivo Torch: {{device}}",
        'status_new_db': "Nuovo DB creato. Pronto per la scansione.",
        'status_processing': "Elaborazione {current}/{total}: {filename}",
        'status_stopping': "Arresto in corso...",
        'status_complete': "Elaborazione completata",
        'status_error': "Errore!",
        'status_initializing': "Inizializzazione...",
        'status_loading_yolo': "Scaricamento di YOLO: {model}...",
        'status_loading_dog_models': "Caricamento modelli di riconoscimento cani...",
        'current_image_frame': "Immagine Corrente",
        'log_frame': "Log di Elaborazione",
        'language_label': "Lingua:",
        # People/Dogs DB Tabs
        'refresh_button': "Aggiorna",
        'edit_button': "Modifica",
        'delete_button': "Elimina",
        # People Tree
        'people_col_id': 'ID', 'people_col_status': 'Stato', 'people_col_fullname': 'Nome Completo', 'people_col_shortname': 'Nome Breve', 'people_col_photos': 'Foto', 'people_col_notes': 'Note',
        # Dogs Tree
        'dogs_col_id': 'ID', 'dogs_col_status': 'Stato', 'dogs_col_name': 'Nome', 'dogs_col_breed': 'Razza', 'dogs_col_owner': 'Proprietario', 'dogs_col_photos': 'Foto', 'dogs_col_notes': 'Note',
        # Dialogs
        'person_dialog_title': "Identificazione Persona",
        'dog_dialog_title': "Identificazione Cane",
        'body_dialog_title': "Persona senza volto riconoscibile",
        'confirm_dialog_title': "Corrispondenza Trovata nel DB di Riferimento",
        'processed_dialog_title': "Immagine Già Elaborata",
        # Person Dialog
        'new_person_detected': "Rilevata nuova persona", 'new_person_tab': "Nuova Persona", 'select_from_db_tab': "Seleziona da DB", 'select_from_ref_db_tab': "Seleziona da DB Rif.",
        'full_name_label': "Nome Completo:", 'short_name_label': "Nome Breve:", 'notes_label': "Note:", 'save_known_button': "Salva come Noto", 'leave_unknown_button': "Lascia Sconosciuto", 'cancel_button': "Annulla",
        # Dog Dialog
        'new_dog_detected': "Rilevato cane", 'new_dog_tab': "Nuovo Cane", 'dog_name_label': "Nome:", 'dog_breed_label': "Razza:", 'dog_owner_label': "Proprietario:",
        # Body Dialog
        'body_detected': "Persona senza volto riconoscibile", 'enter_data_tab': "Inserisci Dati (Localmente)", 'save_info_button': "Salva Informazioni", 'skip_button': "Salta (Sconosciuto)",
        # Confirm Dialog
        'match_found': "È stata trovata una possibile corrispondenza!", 'ref_db_info': "Informazioni dal DB di Riferimento", 'is_same_person': "È la stessa persona?", 'confirm_match_button': "Sì, corrisponde", 'reject_match_button': "No, persona diversa",
        # Processed Dialog
        'image_processed_before': "L'immagine '{filename}' è già stata elaborata.\nElaborarla di nuovo?", 'apply_to_all_check': "Applica questa decisione a tutte le immagini successive", 'yes_process_button': "Sì, Elabora", 'no_skip_button': "No, Salta",
        # Messages
        'select_db_title': "Seleziona Database Attivo", 'create_db_title': "Crea Nuovo Database", 'select_ref_db_title': "Seleziona Database di Riferimento", 'select_photo_dir_title': "Seleziona Cartella Foto",
        'error_title': "Errore", 'warning_title': "Attenzione", 'success_title': "Successo", 'info_title': "Non implementato",
        'db_create_error': "Impossibile creare o aggiornare il database: {e}", 'db_structure_error': "La struttura del database non è corretta, anche dopo un tentativo di aggiornamento.",
        'db_load_error': "Il file DB selezionato ha una struttura non valida.",
        'select_db_prompt': "Seleziona o crea un file di database.", 'select_dir_prompt': "Specifica una cartella con le foto.",
        'enter_full_name_prompt': "Inserisci un nome completo.", 'select_person_prompt': "Seleziona una persona dalla lista.",
        'person_exists_prompt': "Una persona con questi nomi esiste già nel database:\n\nNome Completo: {full_name}\nNome Breve: {short_name}\n\nSe si tratta di una persona diversa, cambia il nome. Se è la stessa persona, selezionala dalla scheda appropriata.",
        'enter_dog_name_prompt': "Inserisci il nome del cane.", 'select_dog_prompt': "Seleziona un cane dalla lista.",
        'dog_exists_prompt': "Un cane con queste informazioni esiste già nel DB:\nNome: {name}\nRazza: {breed}\nProprietario: {owner}",
        'enter_body_name_prompt': "Inserisci un nome completo o fai clic su 'Salta'.",
        'edit_unimplemented': "La funzione di modifica è in fase di sviluppo.",
        'delete_person_confirm': "Sei sicuro di voler eliminare questa persona e tutti i dati correlati? Questa azione non può essere annullata.", 'delete_person_success': "Persona eliminata con successo.", 'delete_person_fail': "Eliminazione fallita: {e}",
        'delete_dog_confirm': "Sei sicuro di voler eliminare questo cane e tutti i dati correlati? Questa azione non può essere annullata.", 'delete_dog_success': "Cane eliminato con successo.", 'delete_dog_fail': "Eliminazione fallita: {e}",
    }
}

class LangManager:
    """A simple class to manage localization."""
    def __init__(self, lang_var):
        self.lang_var = lang_var
        self.loc = localization

    def get(self, key, **kwargs):
        """
        Retrieves a string for the given key in the currently selected language.
        Performs .format(**kwargs) if any keyword arguments are provided.
        """
        try:
            string = self.loc[self.lang_var.get()][key]
            if kwargs:
                return string.format(**kwargs)
            return string
        except KeyError:
            # Fallback to English if a key is missing in the current language
            try:
                string = self.loc['EN'][key]
                if kwargs:
                    return string.format(**kwargs)
                return string
            except KeyError:
                 # Return the key itself if it's not found anywhere
                return key

# --- Class to redirect stdout to the log (for the progress bar) ---
class StdOutRedirector:
    def __init__(self, queue):
        self.queue = queue
        self._buffer = ''

    def write(self, text):
        # Write to the GUI only if the text contains a newline or carriage return.
        # This allows the torchvision progress bar to update on a single line.
        if '\n' in text or '\r' in text:
            self.queue.put(('log', self._buffer + text))
            self._buffer = ''
        else:
            self._buffer += text
    
    def flush(self):
        if self._buffer:
            self.queue.put(('log', self._buffer))
            self._buffer = ''

def orient_image(img: Image.Image) -> Image.Image:
    """Applies rotation to an image based on its EXIF data."""
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
    """Base class for all dialog windows with improved centering."""
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
    def __init__(self, parent, image_path, lang_manager):
        super().__init__(parent)
        self.parent = parent; self.result = None; self.apply_to_all = False
        self.lang = lang_manager
        self.title(self.lang.get('processed_dialog_title')); self.resizable(False, False); self.transient(parent); self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        main_frame = ttk.Frame(self, padding="20"); main_frame.pack(fill=tk.BOTH, expand=True)
        message = self.lang.get('image_processed_before', filename=os.path.basename(image_path))
        ttk.Label(main_frame, text=message, wraplength=450).pack(pady=10)
        self.apply_to_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(main_frame, text=self.lang.get('apply_to_all_check'), variable=self.apply_to_all_var).pack(pady=10)
        button_frame = ttk.Frame(main_frame); button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        ttk.Button(button_frame, text=self.lang.get('yes_process_button'), command=self.process).pack(side=tk.LEFT, padx=5, expand=True)
        ttk.Button(button_frame, text=self.lang.get('no_skip_button'), command=self.skip).pack(side=tk.LEFT, padx=5, expand=True)
        ttk.Button(button_frame, text=self.lang.get('cancel_button'), command=self.cancel).pack(side=tk.RIGHT, padx=5, expand=True)
        self.center_window()
    def process(self): self.result = 'process'; self.apply_to_all = self.apply_to_all_var.get(); self.destroy()
    def skip(self): self.result = 'skip'; self.apply_to_all = self.apply_to_all_var.get(); self.destroy()
    def cancel(self): self.result = 'cancel'; self.destroy()

class PersonDialog(BaseDialog):
    def __init__(self, parent, image, face_location, lang_manager, existing_persons=None, ref_persons=None, db_path=None):
        super().__init__(parent)
        self.parent = parent; self.result = None; self.lang = lang_manager
        self.existing_persons = existing_persons or []; self.ref_persons = ref_persons or []; self.db_path = db_path
        self.title(self.lang.get('person_dialog_title')); self.resizable(True, True); self.transient(parent); self.grab_set(); self.protocol("WM_DELETE_WINDOW", self.save_unknown)
        main_frame = ttk.Frame(self); main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        face_frame = ttk.Frame(main_frame); face_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        top, right, bottom, left = face_location; face_img = image[top:bottom, left:right]; face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB); face_img = Image.fromarray(face_img)
        face_img.thumbnail((150, 150), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(face_img)
        face_label = ttk.Label(face_frame, image=photo); face_label.image = photo; face_label.pack()
        ttk.Label(face_frame, text=self.lang.get('new_person_detected'), font=('Arial', 12, 'bold')).pack(pady=5)
        self.notebook = ttk.Notebook(main_frame); self.notebook.pack(fill=tk.BOTH, expand=True)
        new_person_frame = ttk.Frame(self.notebook); self.notebook.add(new_person_frame, text=self.lang.get('new_person_tab'))
        input_frame = ttk.Frame(new_person_frame, padding="20"); input_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(input_frame, text=self.lang.get('full_name_label')).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5); self.full_name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.full_name_var, width=40).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text=self.lang.get('short_name_label')).grid(row=1, column=0, sticky=tk.W, padx=5, pady=5); self.short_name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.short_name_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text=self.lang.get('notes_label')).grid(row=2, column=0, sticky=tk.W+tk.N, padx=5, pady=5); text_frame = ttk.Frame(input_frame); text_frame.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        self.notes_text = tk.Text(text_frame, width=40, height=4, wrap=tk.WORD); notes_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.notes_text.yview); self.notes_text.configure(yscrollcommand=notes_scroll.set)
        self.notes_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); notes_scroll.pack(side=tk.RIGHT, fill=tk.Y); input_frame.columnconfigure(1, weight=1)
        if self.existing_persons:
            existing_frame = ttk.Frame(self.notebook); self.notebook.add(existing_frame, text=self.lang.get('select_from_db_tab'))
            tree_frame = ttk.Frame(existing_frame, padding="10"); tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', self.lang.get('people_col_fullname'), self.lang.get('people_col_shortname')); self.person_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.person_tree.heading(col, text=col); self.person_tree.column(col, width=50 if col == 'ID' else 200)
            tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.person_tree.yview); self.person_tree.configure(yscrollcommand=tree_scroll.set)
            for person in self.existing_persons: self.person_tree.insert('', tk.END, values=(person['id'], person['full_name'], person['short_name']))
            self.person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        if self.ref_persons:
            ref_frame = ttk.Frame(self.notebook); self.notebook.add(ref_frame, text=self.lang.get('select_from_ref_db_tab'))
            ref_tree_frame = ttk.Frame(ref_frame, padding="10"); ref_tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', self.lang.get('people_col_fullname'), self.lang.get('people_col_shortname')); self.ref_person_tree = ttk.Treeview(ref_tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.ref_person_tree.heading(col, text=col); self.ref_person_tree.column(col, width=50 if col == 'ID' else 200)
            ref_tree_scroll = ttk.Scrollbar(ref_tree_frame, orient="vertical", command=self.ref_person_tree.yview); self.ref_person_tree.configure(yscrollcommand=ref_tree_scroll.set)
            for person in self.ref_persons: self.ref_person_tree.insert('', tk.END, values=(person['id'], person['full_name'], person['short_name']))
            self.ref_person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); ref_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        button_frame = ttk.Frame(self); button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10); left_buttons = ttk.Frame(button_frame); left_buttons.pack(side=tk.LEFT); right_buttons = ttk.Frame(button_frame); right_buttons.pack(side=tk.RIGHT)
        ttk.Button(left_buttons, text=self.lang.get('save_known_button'), command=self.save_known).pack(side=tk.LEFT, padx=5)
        ttk.Button(left_buttons, text=self.lang.get('leave_unknown_button'), command=self.save_unknown).pack(side=tk.LEFT, padx=5)
        ttk.Button(right_buttons, text=self.lang.get('cancel_button'), command=self.cancel).pack(side=tk.RIGHT, padx=5)
        self.center_window(); self.full_name_var.set(""); self.notebook.select(0); self.after(100, lambda: self.focus_force())

    def check_person_exists(self, full_name, short_name):
        if not self.db_path: return False, []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor(); cursor.execute('SELECT id, full_name, short_name FROM persons WHERE is_known = 1 AND full_name = ? AND short_name = ?', (full_name, short_name)); return (dups := cursor.fetchall()), dups

    def save_known(self):
        try: active_tab_text = self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError: active_tab_text = self.lang.get('new_person_tab')
        if active_tab_text == self.lang.get('new_person_tab'):
            full_name = self.full_name_var.get().strip(); short_name = self.short_name_var.get().strip() or full_name.split()[0]
            if not full_name: messagebox.showwarning(self.lang.get('warning_title'), self.lang.get('enter_full_name_prompt'), parent=self); return
            exists, duplicates = self.check_person_exists(full_name, short_name)
            if exists: messagebox.showwarning(self.lang.get('warning_title'), self.lang.get('person_exists_prompt', full_name=duplicates[0][1], short_name=duplicates[0][2]), parent=self); return
            self.result = {'action': 'new_known', 'full_name': full_name, 'short_name': short_name, 'notes': self.notes_text.get('1.0', tk.END).strip()}; self.destroy()
        elif active_tab_text == self.lang.get('select_from_db_tab'):
            if not hasattr(self, 'person_tree') or not (selection := self.person_tree.selection()): messagebox.showwarning(self.lang.get('warning_title'), self.lang.get('select_person_prompt'), parent=self); return
            self.result = {'action': 'existing', 'person_id': self.person_tree.item(selection[0])['values'][0]}; self.destroy()
        elif active_tab_text == self.lang.get('select_from_ref_db_tab'):
            if not hasattr(self, 'ref_person_tree') or not (selection := self.ref_person_tree.selection()): messagebox.showwarning(self.lang.get('warning_title'), self.lang.get('select_person_prompt'), parent=self); return
            selected_id = self.ref_person_tree.item(selection[0])['values'][0]; person_info = next((p for p in self.ref_persons if p['id'] == selected_id), None)
            self.result = {'action': 'existing_ref', 'person_info': person_info}; self.destroy()

    def save_unknown(self): self.result = {'action': 'unknown'}; self.destroy()
    def cancel(self): self.result = None; self.destroy()

class DogDialog(BaseDialog):
    def __init__(self, parent, image, dog_bbox, lang_manager, existing_dogs=None, ref_dogs=None, db_path=None, breed=None):
        super().__init__(parent); self.parent = parent; self.result = None; self.lang = lang_manager
        self.existing_dogs = existing_dogs or []; self.ref_dogs = ref_dogs or []; self.db_path = db_path
        self.title(self.lang.get('dog_dialog_title')); self.resizable(True, True); self.transient(parent); self.grab_set(); self.protocol("WM_DELETE_WINDOW", self.save_unknown)
        main_frame = ttk.Frame(self); main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        dog_frame = ttk.Frame(main_frame); dog_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        x1, y1, x2, y2 = dog_bbox; dog_img = image[y1:y2, x1:x2]; dog_img = cv2.cvtColor(dog_img, cv2.COLOR_BGR2RGB); dog_img = Image.fromarray(dog_img)
        dog_img.thumbnail((200, 200), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(dog_img)
        dog_label = ttk.Label(dog_frame, image=photo); dog_label.image = photo; dog_label.pack()
        ttk.Label(dog_frame, text=self.lang.get('new_dog_detected'), font=('Arial', 12, 'bold')).pack(pady=5)
        self.notebook = ttk.Notebook(main_frame); self.notebook.pack(fill=tk.BOTH, expand=True)
        new_dog_frame = ttk.Frame(self.notebook); self.notebook.add(new_dog_frame, text=self.lang.get('new_dog_tab'))
        input_frame = ttk.Frame(new_dog_frame, padding="20"); input_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(input_frame, text=self.lang.get('dog_name_label')).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5); self.name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.name_var, width=40).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text=self.lang.get('dog_breed_label')).grid(row=1, column=0, sticky=tk.W, padx=5, pady=5); self.breed_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.breed_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text=self.lang.get('dog_owner_label')).grid(row=2, column=0, sticky=tk.W, padx=5, pady=5); self.owner_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.owner_var, width=40).grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text=self.lang.get('notes_label')).grid(row=3, column=0, sticky=tk.W+tk.N, padx=5, pady=5); text_frame = ttk.Frame(input_frame); text_frame.grid(row=3, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        self.notes_text = tk.Text(text_frame, width=40, height=3, wrap=tk.WORD); self.notes_text.pack(fill=tk.BOTH, expand=True); input_frame.columnconfigure(1, weight=1)
        if breed: self.breed_var.set(breed)
        if self.existing_dogs:
            existing_frame = ttk.Frame(self.notebook); self.notebook.add(existing_frame, text=self.lang.get('select_from_db_tab'))
            tree_frame = ttk.Frame(existing_frame, padding="10"); tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', self.lang.get('dogs_col_name'), self.lang.get('dogs_col_breed'), self.lang.get('dogs_col_owner')); self.dog_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.dog_tree.heading(col, text=col); self.dog_tree.column(col, width=50 if col == 'ID' else 180)
            tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.dog_tree.yview); self.dog_tree.configure(yscrollcommand=tree_scroll.set)
            for dog in self.existing_dogs: self.dog_tree.insert('', tk.END, values=(dog['id'], dog['name'], dog['breed'] or 'N/A', dog['owner'] or 'N/A'))
            self.dog_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        if self.ref_dogs:
            ref_frame = ttk.Frame(self.notebook); self.notebook.add(ref_frame, text=self.lang.get('select_from_ref_db_tab'))
            ref_tree_frame = ttk.Frame(ref_frame, padding="10"); ref_tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', self.lang.get('dogs_col_name'), self.lang.get('dogs_col_breed'), self.lang.get('dogs_col_owner')); self.ref_dog_tree = ttk.Treeview(ref_tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.ref_dog_tree.heading(col, text=col); self.ref_dog_tree.column(col, width=50 if col == 'ID' else 180)
            ref_tree_scroll = ttk.Scrollbar(ref_tree_frame, orient="vertical", command=self.ref_dog_tree.yview); self.ref_dog_tree.configure(yscrollcommand=ref_tree_scroll.set)
            for dog in self.ref_dogs: self.ref_dog_tree.insert('', tk.END, values=(dog['id'], dog['name'], dog['breed'] or '', dog['owner'] or ''))
            self.ref_dog_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); ref_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        button_frame = ttk.Frame(self); button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10); left_button_frame = ttk.Frame(button_frame); left_button_frame.pack(side=tk.LEFT); right_button_frame = ttk.Frame(button_frame); right_button_frame.pack(side=tk.RIGHT)
        ttk.Button(left_button_frame, text=self.lang.get('save_known_button'), command=self.save_known).pack(side=tk.LEFT, padx=5)
        ttk.Button(left_button_frame, text=self.lang.get('leave_unknown_button'), command=self.save_unknown).pack(side=tk.LEFT, padx=5)
        ttk.Button(right_button_frame, text=self.lang.get('cancel_button'), command=self.cancel).pack(side=tk.RIGHT, padx=5)
        self.center_window()

    def check_dog_exists(self, name, breed, owner):
        if not self.db_path: return False, []
        with sqlite3.connect(self.db_path) as conn:
            cursor=conn.cursor(); cursor.execute('SELECT id, name, breed, owner FROM dogs WHERE is_known=1 AND name=? AND(? = "" OR breed = ? ) AND (? = "" OR owner = ?)', (name, breed, breed, owner, owner)); return (dups := cursor.fetchall()), dups

    def save_known(self):
        try: active_tab_text = self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError: active_tab_text = self.lang.get('new_dog_tab')
        if active_tab_text == self.lang.get('new_dog_tab'):
            name = self.name_var.get().strip(); breed = self.breed_var.get().strip(); owner = self.owner_var.get().strip()
            if not name: messagebox.showwarning(self.lang.get('warning_title'), self.lang.get('enter_dog_name_prompt'), parent=self); return
            exists, duplicates = self.check_dog_exists(name, breed, owner)
            if exists: messagebox.showwarning(self.lang.get('warning_title'), self.lang.get('dog_exists_prompt', name=duplicates[0][1], breed=duplicates[0][2], owner=duplicates[0][3]), parent=self); return
            self.result = {'action':'new_known', 'name':name, 'breed':breed, 'owner':owner, 'notes':self.notes_text.get('1.0', tk.END).strip()}; self.destroy()
        elif active_tab_text == self.lang.get('select_from_db_tab'):
            if not hasattr(self, 'dog_tree') or not (selection := self.dog_tree.selection()): messagebox.showwarning(self.lang.get('warning_title'), self.lang.get('select_dog_prompt'), parent=self); return
            self.result = {'action':'existing', 'dog_id':self.dog_tree.item(selection[0])['values'][0]}; self.destroy()
        elif active_tab_text == self.lang.get('select_from_ref_db_tab'):
            if not hasattr(self, 'ref_dog_tree') or not (selection := self.ref_dog_tree.selection()): messagebox.showwarning(self.lang.get('warning_title'), self.lang.get('select_dog_prompt'), parent=self); return
            selected_id = self.ref_dog_tree.item(selection[0])['values'][0]; dog_info = next((d for d in self.ref_dogs if d['id'] == selected_id), None)
            self.result = {'action': 'existing_ref', 'dog_info': dog_info}; self.destroy()

    def save_unknown(self): self.result = {'action':'unknown'}; self.destroy()
    def cancel(self): self.result = None; self.destroy()

class BodyWithoutFaceDialog(BaseDialog):
    def __init__(self, parent, image, body_bbox, lang_manager, existing_persons=None, ref_persons=None, db_path=None):
        super().__init__(parent); self.parent = parent; self.result = None; self.lang = lang_manager
        self.existing_persons = existing_persons or []; self.ref_persons = ref_persons or []; self.db_path = db_path
        self.title(self.lang.get('body_dialog_title')); self.resizable(True, True); self.transient(parent); self.grab_set(); self.protocol("WM_DELETE_WINDOW", self.skip)
        main_frame = ttk.Frame(self); main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        body_frame = ttk.Frame(main_frame); body_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        x1, y1, x2, y2 = body_bbox; body_img = image[y1:y2, x1:x2]; body_img = cv2.cvtColor(body_img, cv2.COLOR_BGR2RGB); body_img = Image.fromarray(body_img)
        body_img.thumbnail((200, 300), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(body_img)
        body_label = ttk.Label(body_frame, image=photo); body_label.image = photo; body_label.pack()
        ttk.Label(body_frame, text=self.lang.get('body_detected'), font=('Arial', 12, 'bold')).pack(pady=5)
        self.notebook = ttk.Notebook(main_frame); self.notebook.pack(fill=tk.BOTH, expand=True)
        input_tab = ttk.Frame(self.notebook); self.notebook.add(input_tab, text=self.lang.get('enter_data_tab'))
        input_frame = ttk.Frame(input_tab, padding="20"); input_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(input_frame, text=self.lang.get('full_name_label')).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5); self.full_name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.full_name_var, width=40).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text=self.lang.get('short_name_label')).grid(row=1, column=0, sticky=tk.W, padx=5, pady=5); self.short_name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.short_name_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text=self.lang.get('notes_label')).grid(row=2, column=0, sticky=tk.W+tk.N, padx=5, pady=5); text_frame = ttk.Frame(input_frame); text_frame.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        self.notes_text = tk.Text(text_frame, width=40, height=3, wrap=tk.WORD); self.notes_text.pack(fill=tk.BOTH, expand=True); input_frame.columnconfigure(1, weight=1)
        if self.existing_persons:
            existing_tab = ttk.Frame(self.notebook); self.notebook.add(existing_tab, text=self.lang.get('select_from_db_tab'))
            tree_frame = ttk.Frame(existing_tab, padding="10"); tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', self.lang.get('people_col_fullname'), self.lang.get('people_col_shortname')); self.person_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.person_tree.heading(col, text=col); self.person_tree.column(col, width=50 if col == 'ID' else 250)
            tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.person_tree.yview); self.person_tree.configure(yscrollcommand=tree_scroll.set)
            for person in self.existing_persons: self.person_tree.insert('', tk.END, values=(person['id'], person['full_name'], person['short_name']))
            self.person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        if self.ref_persons:
            ref_tab = ttk.Frame(self.notebook); self.notebook.add(ref_tab, text=self.lang.get('select_from_ref_db_tab'))
            ref_tree_frame = ttk.Frame(ref_tab, padding="10"); ref_tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', self.lang.get('people_col_fullname'), self.lang.get('people_col_shortname')); self.ref_person_tree = ttk.Treeview(ref_tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.ref_person_tree.heading(col, text=col); self.ref_person_tree.column(col, width=50 if col == 'ID' else 250)
            ref_tree_scroll = ttk.Scrollbar(ref_tree_frame, orient="vertical", command=self.ref_person_tree.yview); self.ref_person_tree.configure(yscrollcommand=ref_tree_scroll.set)
            for person in self.ref_persons: self.ref_person_tree.insert('', tk.END, values=(person['id'], person['full_name'], person['short_name']))
            self.ref_person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); ref_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        button_frame = ttk.Frame(self); button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        ttk.Button(button_frame, text=self.lang.get('save_info_button'), command=self.save_info).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text=self.lang.get('skip_button'), command=self.skip).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text=self.lang.get('cancel_button'), command=self.cancel).pack(side=tk.RIGHT, padx=5)
        self.center_window()
    def save_info(self):
        try: active_tab_text = self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError: active_tab_text = self.lang.get('enter_data_tab')
        if active_tab_text == self.lang.get('enter_data_tab'):
            full_name = self.full_name_var.get().strip()
            if not full_name: messagebox.showwarning(self.lang.get('warning_title'), self.lang.get('enter_body_name_prompt'), parent=self); return
            self.result = {'action':'local_known', 'full_name':full_name, 'short_name':self.short_name_var.get().strip() or full_name.split()[0], 'notes':self.notes_text.get('1.0', tk.END).strip()}; self.destroy()
        elif active_tab_text == self.lang.get('select_from_db_tab'):
            if not hasattr(self, 'person_tree') or not (selection := self.person_tree.selection()): messagebox.showwarning(self.lang.get('warning_title'), self.lang.get('select_person_prompt'), parent=self); return
            self.result = {'action':'existing', 'person_id':self.person_tree.item(selection[0])['values'][0]}; self.destroy()
        elif active_tab_text == self.lang.get('select_from_ref_db_tab'):
            if not hasattr(self, 'ref_person_tree') or not (selection := self.ref_person_tree.selection()): messagebox.showwarning(self.lang.get('warning_title'), self.lang.get('select_person_prompt'), parent=self); return
            selected_id = self.ref_person_tree.item(selection[0])['values'][0]; person_info = next((p for p in self.ref_persons if p['id'] == selected_id), None)
            self.result = {'action': 'existing_ref', 'person_info': person_info}; self.destroy()
    def skip(self): self.result = {'action':'unknown'}; self.destroy()
    def cancel(self): self.result = None; self.destroy()

class ConfirmPersonDialog(BaseDialog):
    def __init__(self, parent, image, face_location, person_info, lang_manager):
        super().__init__(parent); self.result = None; self.person_info = person_info; self.lang = lang_manager
        self.title(self.lang.get('confirm_dialog_title')); self.resizable(False, False); self.transient(parent); self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.reject)
        main_frame = ttk.Frame(self, padding=20); main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text=self.lang.get('match_found'), font=('Arial', 14, 'bold')).pack(pady=(0, 10))
        top, right, bottom, left = face_location; face_img = image[top:bottom, left:right]; face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB); face_img = Image.fromarray(face_img)
        face_img.thumbnail((150, 150), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(face_img)
        face_label = ttk.Label(main_frame, image=photo); face_label.image = photo; face_label.pack(pady=10)
        info_frame = ttk.LabelFrame(main_frame, text=self.lang.get('ref_db_info'), padding=10); info_frame.pack(fill=tk.X, pady=10)
        ttk.Label(info_frame, text=f"{self.lang.get('full_name_label')} {person_info['full_name']}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"{self.lang.get('short_name_label')} {person_info['short_name']}").pack(anchor=tk.W)
        if person_info.get('notes'): ttk.Label(info_frame, text=f"{self.lang.get('notes_label')} {person_info['notes']}").pack(anchor=tk.W)
        ttk.Label(main_frame, text=self.lang.get('is_same_person'), font=('Arial', 11, 'bold')).pack(pady=10)
        button_frame = ttk.Frame(main_frame); button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text=self.lang.get('confirm_match_button'), command=self.confirm).pack(side=tk.LEFT, expand=True, padx=5)
        ttk.Button(button_frame, text=self.lang.get('reject_match_button'), command=self.reject).pack(side=tk.RIGHT, expand=True, padx=5)
        self.center_window()
    def confirm(self): self.result = {'confirmed': True, 'person_info': self.person_info}; self.destroy()
    def reject(self): self.result = {'confirmed': False}; self.destroy()

class FaceDetectionV2:
    def __init__(self, root):
        self.root = root
        
        # --- Language and Localization Setup ---
        self.current_lang = tk.StringVar(value="EN")
        self.lang = LangManager(self.current_lang)
        self.current_lang.trace_add('write', self.on_language_change)

        self.root.title(self.lang.get('window_title', version=VERSION))
        self.root.geometry("1400x900")
        self.style = ttk.Style(self.root)
        try: self.style.theme_use('clam')
        except tk.TclError: print("Theme 'clam' not found.")
        self.style.configure('TNotebook.Tab', font=('Arial', 12, 'bold'), padding=[10, 5]); self.style.configure('Status.TLabel', font=('Arial', 11, 'bold'), padding=5)
        self.style.configure('Idle.Status.TLabel', background='lightblue', foreground='black'); self.style.configure('Processing.Status.TLabel', background='lightyellow', foreground='black')
        self.style.configure('Complete.Status.TLabel', background='lightgreen', foreground='black'); self.style.configure('Error.Status.TLabel', background='lightcoral', foreground='black')
        
        self.update_queue = queue.Queue()
        self.source_dir = tk.StringVar(value=""); self.db_path_var = tk.StringVar(value=""); self.ref_db_path_var = tk.StringVar(value="")
        self.face_model = tk.StringVar(value=self.lang.get('face_model_fast'))
        self.include_subdirs = tk.BooleanVar(value=False)
        self.face_threshold = tk.DoubleVar(value=0.6)
        
        self.yolo_person_conf = tk.DoubleVar(value=0.5)
        self.yolo_model = tk.StringVar(value="yolov8n.pt")
        
        self.processing = False
        self.processed_mode = tk.StringVar(value="skip")
        self.processed_decision_for_all = None
        self.db_path = None
        self.ref_db_path = None
        
        # Attributes for dog recognition models
        self.dog_det_model = None; self.dog_cls_model = None; self.dog_prep_det = None
        self.dog_prep_cls = None; self.dog_labels_imagenet = None
        self.dog_device = "cuda" if torch.cuda.is_available() else "cpu"
        self.dog_detection_threshold = tk.DoubleVar(value=0.35)
        
        self.yolo = None; self.loaded_yolo_model_name = None; self.displayed_photo = None
        
        self.create_widgets()
        
        # --- Top-right corner widgets ---
        top_right_frame = ttk.Frame(self.root)
        top_right_frame.place(relx=1.0, y=0, anchor='ne') # Position frame in corner

        # Version label (packed right-most)
        self.version_label = ttk.Label(top_right_frame, text=f"v{VERSION}", font=('Arial', 9))
        self.version_label.pack(side=tk.RIGHT, padx=(5, 10), pady=5)

        # Language dropdown (to the left of version)
        lang_combo = ttk.Combobox(top_right_frame, textvariable=self.current_lang, values=['EN', 'RU', 'IT'], state='readonly', width=5)
        lang_combo.pack(side=tk.RIGHT, pady=5)

        # Language label (left-most in the frame)
        self.lang_lbl = ttk.Label(top_right_frame, text=self.lang.get('language_label'))
        self.lang_lbl.pack(side=tk.RIGHT, padx=(0, 5), pady=5)
        
        self.stdout_redirector = StdOutRedirector(self.update_queue)
        
        self.process_queue()
        self.update_status(self.lang.get('status_ready_torch', device=self.dog_device.upper()), 'idle')

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
                    self.status_label.config(text=message); self.status_label.config(style=f"{status_type.title()}.Status.TLabel")
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

    def on_language_change(self, *args):
        """Callback function to update all UI text when the language is changed."""
        # Main window title
        self.root.title(self.lang.get('window_title', version=VERSION))
        
        # Main notebook tabs
        self.main_notebook.tab(self.scan_frame, text=self.lang.get('scan_tab'))
        self.main_notebook.tab(self.people_frame, text=self.lang.get('people_db_tab'))
        self.main_notebook.tab(self.dogs_frame, text=self.lang.get('dogs_db_tab'))

        # Scan Tab Widgets
        self.dir_frame.config(text=self.lang.get('scan_settings_frame'))
        self.photo_dir_lbl.config(text=self.lang.get('photo_dir_label'))
        self.browse_source_btn.config(text=self.lang.get('browse_button'))
        self.include_subdirs_cb.config(text=self.lang.get('include_subdirs_check'))
        self.active_db_lbl.config(text=self.lang.get('active_db_label'))
        self.browse_db_btn.config(text=self.lang.get('browse_button'))
        self.create_db_btn.config(text=self.lang.get('create_new_button'))
        self.ref_db_lbl.config(text=self.lang.get('ref_db_label'))
        self.browse_ref_db_btn.config(text=self.lang.get('browse_button'))
        self.clear_ref_db_btn.config(text=self.lang.get('clear_button'))
        self.lang_lbl.config(text=self.lang.get('language_label'))
        
        self.face_model_lbl.config(text=self.lang.get('face_model_label'))
        self.face_model_combo.config(values=[self.lang.get('face_model_fast'), self.lang.get('face_model_accurate')])
        
        self.face_thresh_lbl.config(text=self.lang.get('face_threshold_label'))
        self.face_thresh_note_lbl.config(text=self.lang.get('threshold_note'))
        self.yolo_model_lbl.config(text=self.lang.get('yolo_model_label'))
        self.update_model_info() # This will update the description in the new language
        
        self.yolo_conf_lbl.config(text=self.lang.get('yolo_confidence_label'))
        self.yolo_conf_note_lbl.config(text=self.lang.get('confidence_note'))
        self.dog_thresh_lbl.config(text=self.lang.get('dog_threshold_label'))
        self.dog_thresh_note_lbl.config(text=self.lang.get('dog_threshold_note'))
        
        self.repro_frame.config(text=self.lang.get('reprocessing_frame'))
        self.repro_rb1.config(text=self.lang.get('reprocess_skip'))
        self.repro_rb2.config(text=self.lang.get('reprocess_process'))
        self.repro_rb3.config(text=self.lang.get('reprocess_ask'))
        
        self.start_btn.config(text=self.lang.get('start_scan_button'))
        self.stop_btn.config(text=self.lang.get('stop_button'))
        self.exit_btn.config(text=self.lang.get('exit_button'))
        
        self.image_frame.config(text=self.lang.get('current_image_frame'))
        self.log_frame.config(text=self.lang.get('log_frame'))
        
        # People/Dog Tab Buttons
        self.btn_refresh_people.config(text=self.lang.get('refresh_button'))
        self.btn_edit_person.config(text=self.lang.get('edit_button'))
        self.btn_delete_person.config(text=self.lang.get('delete_button'))
        self.btn_refresh_dogs.config(text=self.lang.get('refresh_button'))
        self.btn_edit_dog.config(text=self.lang.get('edit_button'))
        self.btn_delete_dog.config(text=self.lang.get('delete_button'))
        
        # Treeview Headers
        self.people_tree.heading('ID', text=self.lang.get('people_col_id'))
        self.people_tree.heading('Status', text=self.lang.get('people_col_status'))
        self.people_tree.heading('Full Name', text=self.lang.get('people_col_fullname'))
        self.people_tree.heading('Short Name', text=self.lang.get('people_col_shortname'))
        self.people_tree.heading('Photos', text=self.lang.get('people_col_photos'))
        self.people_tree.heading('Notes', text=self.lang.get('people_col_notes'))
        
        self.dogs_tree.heading('ID', text=self.lang.get('dogs_col_id'))
        self.dogs_tree.heading('Status', text=self.lang.get('dogs_col_status'))
        self.dogs_tree.heading('Name', text=self.lang.get('dogs_col_name'))
        self.dogs_tree.heading('Breed', text=self.lang.get('dogs_col_breed'))
        self.dogs_tree.heading('Owner', text=self.lang.get('dogs_col_owner'))
        self.dogs_tree.heading('Photos', text=self.lang.get('dogs_col_photos'))
        self.dogs_tree.heading('Notes', text=self.lang.get('dogs_col_notes'))

    def create_widgets(self):
        self.main_notebook = ttk.Notebook(self.root); self.main_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.scan_frame = ttk.Frame(self.main_notebook); self.main_notebook.add(self.scan_frame, text=self.lang.get('scan_tab'))
        self.create_scan_tab(self.scan_frame)
        self.people_frame = ttk.Frame(self.main_notebook); self.main_notebook.add(self.people_frame, text=self.lang.get('people_db_tab'))
        self.create_people_tab(self.people_frame)
        self.dogs_frame = ttk.Frame(self.main_notebook); self.main_notebook.add(self.dogs_frame, text=self.lang.get('dogs_db_tab'))
        self.create_dogs_tab(self.dogs_frame)

    def create_scan_tab(self, parent):
        self.dir_frame = ttk.LabelFrame(parent, text=self.lang.get('scan_settings_frame'), padding="10"); self.dir_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=5); self.dir_frame.columnconfigure(1, weight=1)
        
        self.photo_dir_lbl = ttk.Label(self.dir_frame, text=self.lang.get('photo_dir_label')); self.photo_dir_lbl.grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(self.dir_frame, textvariable=self.source_dir, width=60).grid(row=0, column=1, padx=5, sticky=tk.EW)
        self.browse_source_btn = ttk.Button(self.dir_frame, text=self.lang.get('browse_button'), command=self.browse_source); self.browse_source_btn.grid(row=0, column=2)
        self.include_subdirs_cb = ttk.Checkbutton(self.dir_frame, text=self.lang.get('include_subdirs_check'), variable=self.include_subdirs); self.include_subdirs_cb.grid(row=0, column=3, padx=10, sticky=tk.W)
        
        self.active_db_lbl = ttk.Label(self.dir_frame, text=self.lang.get('active_db_label')); self.active_db_lbl.grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(self.dir_frame, textvariable=self.db_path_var, width=60, state='readonly').grid(row=1, column=1, padx=5, sticky=tk.EW)
        db_button_frame = ttk.Frame(self.dir_frame); db_button_frame.grid(row=1, column=2, columnspan=2, sticky=tk.W)
        self.browse_db_btn = ttk.Button(db_button_frame, text=self.lang.get('browse_button'), command=self.select_database_file); self.browse_db_btn.pack(side=tk.LEFT)
        self.create_db_btn = ttk.Button(db_button_frame, text=self.lang.get('create_new_button'), command=self.create_new_database); self.create_db_btn.pack(side=tk.LEFT, padx=5)
        
        self.ref_db_lbl = ttk.Label(self.dir_frame, text=self.lang.get('ref_db_label')); self.ref_db_lbl.grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(self.dir_frame, textvariable=self.ref_db_path_var, width=60, state='readonly').grid(row=2, column=1, padx=5, sticky=tk.EW)
        ref_db_button_frame = ttk.Frame(self.dir_frame); ref_db_button_frame.grid(row=2, column=2, columnspan=2, sticky=tk.W)
        self.browse_ref_db_btn = ttk.Button(ref_db_button_frame, text=self.lang.get('browse_button'), command=self.select_reference_database); self.browse_ref_db_btn.pack(side=tk.LEFT)
        self.clear_ref_db_btn = ttk.Button(ref_db_button_frame, text=self.lang.get('clear_button'), command=self.clear_reference_database); self.clear_ref_db_btn.pack(side=tk.LEFT, padx=5)
        
        self.face_model_lbl = ttk.Label(self.dir_frame, text=self.lang.get('face_model_label')); self.face_model_lbl.grid(row=3, column=0, sticky=tk.W, pady=5)
        self.face_model_combo = ttk.Combobox(self.dir_frame, textvariable=self.face_model, values=[self.lang.get('face_model_fast'), self.lang.get('face_model_accurate')], state='readonly', width=18)
        self.face_model_combo.grid(row=3, column=1, padx=5, sticky=tk.W)

        self.face_thresh_lbl = ttk.Label(self.dir_frame, text=self.lang.get('face_threshold_label')); self.face_thresh_lbl.grid(row=4, column=0, sticky=tk.W, pady=5)
        threshold_frame = ttk.Frame(self.dir_frame); threshold_frame.grid(row=4, column=1, columnspan=3, sticky=tk.W)
        self.threshold_label = ttk.Label(threshold_frame, text=f"{self.face_threshold.get():.2f}", font=('Arial', 10, 'bold'))
        def update_threshold_label(value): self.threshold_label.config(text=f"{float(value):.2f}")
        ttk.Scale(threshold_frame, from_=0.3, to=0.8, variable=self.face_threshold, orient=tk.HORIZONTAL, length=200, command=update_threshold_label).pack(side=tk.LEFT)
        self.threshold_label.pack(side=tk.LEFT, padx=10)
        self.face_thresh_note_lbl = ttk.Label(threshold_frame, text=self.lang.get('threshold_note'), font=('Arial', 9, 'italic')); self.face_thresh_note_lbl.pack(side=tk.LEFT)

        self.yolo_model_lbl = ttk.Label(self.dir_frame, text=self.lang.get('yolo_model_label')); self.yolo_model_lbl.grid(row=5, column=0, sticky=tk.W, pady=5)
        model_frame = ttk.Frame(self.dir_frame); model_frame.grid(row=5, column=1, columnspan=3, sticky=tk.W)
        models = ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt"]
        model_combo = ttk.Combobox(model_frame, textvariable=self.yolo_model, values=models, state="readonly", width=15); model_combo.pack(side=tk.LEFT, padx=5)
        self.model_info_label = ttk.Label(model_frame, font=('Arial', 9), foreground='gray'); self.model_info_label.pack(side=tk.LEFT, padx=10)
        def update_model_info_text(event=None): self.update_model_info()
        model_combo.bind('<<ComboboxSelected>>', update_model_info_text); model_combo.set(self.yolo_model.get()); self.update_model_info()

        self.yolo_conf_lbl = ttk.Label(self.dir_frame, text=self.lang.get('yolo_confidence_label')); self.yolo_conf_lbl.grid(row=6, column=0, sticky=tk.W, pady=5)
        person_conf_frame = ttk.Frame(self.dir_frame); person_conf_frame.grid(row=6, column=1, columnspan=3, sticky=tk.W)
        self.person_conf_label = ttk.Label(person_conf_frame, text=f"{self.yolo_person_conf.get():.2f}", font=('Arial', 10, 'bold'))
        def update_person_conf_label(value): self.person_conf_label.config(text=f"{float(value):.2f}")
        ttk.Scale(person_conf_frame, from_=0.1, to=0.9, variable=self.yolo_person_conf, orient=tk.HORIZONTAL, length=200, command=update_person_conf_label).pack(side=tk.LEFT)
        self.person_conf_label.pack(side=tk.LEFT, padx=10)
        self.yolo_conf_note_lbl = ttk.Label(person_conf_frame, text=self.lang.get('confidence_note'), font=('Arial', 9, 'italic')); self.yolo_conf_note_lbl.pack(side=tk.LEFT)
        
        self.dog_thresh_lbl = ttk.Label(self.dir_frame, text=self.lang.get('dog_threshold_label')); self.dog_thresh_lbl.grid(row=7, column=0, sticky=tk.W, pady=5)
        dog_conf_frame = ttk.Frame(self.dir_frame); dog_conf_frame.grid(row=7, column=1, columnspan=3, sticky=tk.W)
        self.dog_conf_label = ttk.Label(dog_conf_frame, text=f"{self.dog_detection_threshold.get():.2f}", font=('Arial', 10, 'bold'))
        def update_dog_conf_label(value): self.dog_conf_label.config(text=f"{float(value):.2f}")
        ttk.Scale(dog_conf_frame, from_=0.1, to=0.9, variable=self.dog_detection_threshold, orient=tk.HORIZONTAL, length=200, command=update_dog_conf_label).pack(side=tk.LEFT)
        self.dog_conf_label.pack(side=tk.LEFT, padx=10)
        self.dog_thresh_note_lbl = ttk.Label(dog_conf_frame, text=self.lang.get('dog_threshold_note'), font=('Arial', 9, 'italic')); self.dog_thresh_note_lbl.pack(side=tk.LEFT)

        self.repro_frame = ttk.LabelFrame(self.dir_frame, text=self.lang.get('reprocessing_frame'), padding="10"); self.repro_frame.grid(row=8, column=0, columnspan=4, sticky="ew", pady=10, padx=5)
        self.repro_rb1 = ttk.Radiobutton(self.repro_frame, text=self.lang.get('reprocess_skip'), variable=self.processed_mode, value="skip"); self.repro_rb1.pack(anchor=tk.W)
        self.repro_rb2 = ttk.Radiobutton(self.repro_frame, text=self.lang.get('reprocess_process'), variable=self.processed_mode, value="process"); self.repro_rb2.pack(anchor=tk.W)
        self.repro_rb3 = ttk.Radiobutton(self.repro_frame, text=self.lang.get('reprocess_ask'), variable=self.processed_mode, value="ask"); self.repro_rb3.pack(anchor=tk.W)
        
        control_frame = ttk.Frame(parent, padding="10"); control_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5)
        self.start_btn = ttk.Button(control_frame, text=self.lang.get('start_scan_button'), command=self.start_processing, state=tk.DISABLED); self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(control_frame, text=self.lang.get('stop_button'), command=self.stop_processing, state=tk.DISABLED); self.stop_btn.pack(side=tk.LEFT, padx=5)
        self.exit_btn = ttk.Button(control_frame, text=self.lang.get('exit_button'), command=self.root.destroy); self.exit_btn.pack(side=tk.RIGHT, padx=5)
        self.status_label = ttk.Label(control_frame, text=self.lang.get('status_ready'), style="Idle.Status.TLabel"); self.status_label.pack(side=tk.LEFT, padx=20, fill=tk.X, expand=True)

        self.image_frame = ttk.LabelFrame(parent, text=self.lang.get('current_image_frame'), padding="10"); self.image_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        self.image_label = ttk.Label(self.image_frame); self.image_label.pack(expand=True, fill=tk.BOTH)
        self.log_frame = ttk.LabelFrame(parent, text=self.lang.get('log_frame'), padding="10"); self.log_frame.grid(row=2, column=1, sticky="nsew", padx=10, pady=10)
        self.log_text = scrolledtext.ScrolledText(self.log_frame, width=50, height=30, wrap=tk.WORD); self.log_text.pack(fill=tk.BOTH, expand=True)
        self.copy_btn = ttk.Button(self.log_frame, text="📋", width=3, command=self.copy_log_to_clipboard); self.copy_btn.place(relx=1.0, rely=0, x=-5, y=2, anchor="ne")
        parent.grid_rowconfigure(2, weight=1); parent.grid_columnconfigure(0, weight=2); parent.grid_columnconfigure(1, weight=1)

    def update_model_info(self):
        """Updates the descriptive text for the selected YOLO model based on the current language."""
        model_descriptions = {
            "yolov8n.pt": self.lang.get('yolo_nano'), "yolov8s.pt": self.lang.get('yolo_small'),
            "yolov8m.pt": self.lang.get('yolo_medium'), "yolov8l.pt": self.lang.get('yolo_large'),
            "yolov8x.pt": self.lang.get('yolo_extra')}
        self.model_info_label.config(text=model_descriptions.get(self.yolo_model.get(), ""))

    def copy_log_to_clipboard(self):
        content = self.log_text.get('1.0', tk.END).strip();
        if content: self.root.clipboard_clear(); self.root.clipboard_append(content); self.log("Log copied to clipboard.")

    def create_people_tab(self, parent):
        toolbar = ttk.Frame(parent); toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        self.btn_refresh_people = ttk.Button(toolbar, text=self.lang.get('refresh_button'), command=self.refresh_people_list, state=tk.DISABLED); self.btn_refresh_people.pack(side=tk.LEFT, padx=5)
        self.btn_edit_person = ttk.Button(toolbar, text=self.lang.get('edit_button'), command=self.edit_person, state=tk.DISABLED); self.btn_edit_person.pack(side=tk.LEFT, padx=5)
        self.btn_delete_person = ttk.Button(toolbar, text=self.lang.get('delete_button'), command=self.delete_person, state=tk.DISABLED); self.btn_delete_person.pack(side=tk.LEFT, padx=5)
        columns = ('ID', 'Status', 'Full Name', 'Short Name', 'Photos', 'Notes'); self.people_tree = ttk.Treeview(parent, columns=columns, show='headings')
        self.people_tree.heading('ID', text=self.lang.get('people_col_id')); self.people_tree.column('ID', width=50, anchor='center'); self.people_tree.heading('Status', text=self.lang.get('people_col_status')); self.people_tree.column('Status', width=100); self.people_tree.heading('Full Name', text=self.lang.get('people_col_fullname')); self.people_tree.column('Full Name', width=200); self.people_tree.heading('Short Name', text=self.lang.get('people_col_shortname')); self.people_tree.column('Short Name', width=150); self.people_tree.heading('Photos', text=self.lang.get('people_col_photos')); self.people_tree.column('Photos', width=80, anchor='center'); self.people_tree.heading('Notes', text=self.lang.get('people_col_notes')); self.people_tree.column('Notes', width=300)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.people_tree.yview); self.people_tree.configure(yscrollcommand=scrollbar.set)
        self.people_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5); scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def create_dogs_tab(self, parent):
        toolbar = ttk.Frame(parent); toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        self.btn_refresh_dogs = ttk.Button(toolbar, text=self.lang.get('refresh_button'), command=self.refresh_dogs_list, state=tk.DISABLED); self.btn_refresh_dogs.pack(side=tk.LEFT, padx=5)
        self.btn_edit_dog = ttk.Button(toolbar, text=self.lang.get('edit_button'), command=self.edit_dog, state=tk.DISABLED); self.btn_edit_dog.pack(side=tk.LEFT, padx=5)
        self.btn_delete_dog = ttk.Button(toolbar, text=self.lang.get('delete_button'), command=self.delete_dog, state=tk.DISABLED); self.btn_delete_dog.pack(side=tk.LEFT, padx=5)
        columns = ('ID', 'Status', 'Name', 'Breed', 'Owner', 'Photos', 'Notes'); self.dogs_tree = ttk.Treeview(parent, columns=columns, show='headings')
        col_map = {'ID': self.lang.get('dogs_col_id'), 'Status': self.lang.get('dogs_col_status'), 'Name': self.lang.get('dogs_col_name'), 'Breed': self.lang.get('dogs_col_breed'), 'Owner': self.lang.get('dogs_col_owner'), 'Photos': self.lang.get('dogs_col_photos'), 'Notes': self.lang.get('dogs_col_notes')}
        widths = {'ID':50, 'Status':100, 'Name':150, 'Breed':150, 'Owner':150, 'Photos':80, 'Notes':200}
        for col in columns: self.dogs_tree.heading(col, text=col_map[col]); self.dogs_tree.column(col, width=widths[col])
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.dogs_tree.yview); self.dogs_tree.configure(yscrollcommand=scrollbar.set)
        self.dogs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5); scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def set_db_dependent_widgets_state(self, state):
        self.start_btn.config(state=state); self.btn_refresh_people.config(state=state); self.btn_edit_person.config(state=state); self.btn_delete_person.config(state=state); self.btn_refresh_dogs.config(state=state); self.btn_edit_dog.config(state=state); self.btn_delete_dog.config(state=state)
    
    def init_database(self, db_path):
        """Creates tables if they don't exist, and adds missing columns."""
        try:
            if db_dir := os.path.dirname(db_path): os.makedirs(db_dir, exist_ok=True)
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                base_tables_sql = """
                CREATE TABLE IF NOT EXISTS persons (id INTEGER PRIMARY KEY, is_known BOOLEAN, full_name TEXT, short_name TEXT, notes TEXT, created_date TEXT, updated_date TEXT);
                CREATE TABLE IF NOT EXISTS dogs (id INTEGER PRIMARY KEY, is_known BOOLEAN, name TEXT, breed TEXT, owner TEXT, notes TEXT, created_date TEXT, updated_date TEXT);
                CREATE TABLE IF NOT EXISTS images (id INTEGER PRIMARY KEY, filename TEXT, filepath TEXT, created_date TEXT, file_size INTEGER, num_bodies INTEGER, num_faces INTEGER, num_dogs INTEGER, processed_date TEXT);
                CREATE TABLE IF NOT EXISTS face_encodings (id INTEGER PRIMARY KEY, person_id INTEGER, image_id INTEGER, face_encoding TEXT, face_location TEXT, FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE CASCADE, FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS person_detections (id INTEGER PRIMARY KEY, image_id INTEGER, person_id INTEGER, person_index INTEGER, bbox TEXT, confidence REAL, has_face BOOLEAN, face_encoding_id INTEGER, is_locally_identified BOOLEAN, local_full_name TEXT, local_short_name TEXT, local_notes TEXT, FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE, FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE CASCADE, FOREIGN KEY(face_encoding_id) REFERENCES face_encodings(id) ON DELETE SET NULL);
                CREATE TABLE IF NOT EXISTS dog_detections (id INTEGER PRIMARY KEY, image_id INTEGER, dog_id INTEGER, dog_index INTEGER, bbox TEXT, confidence REAL, FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE, FOREIGN KEY(dog_id) REFERENCES dogs(id) ON DELETE CASCADE);
                """
                for statement in base_tables_sql.strip().split(';'):
                    if statement.strip(): cursor.execute(statement)
                
                def add_column_if_not_exists(table, column, col_type):
                    cursor.execute(f"PRAGMA table_info({table})")
                    columns = [col[1] for col in cursor.fetchall()]
                    if column not in columns:
                        self.log(f"Updating DB schema: adding column {column} to table {table}...")
                        cursor.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}')

                add_column_if_not_exists('images', 'ai_short_description', 'TEXT'); add_column_if_not_exists('images', 'ai_long_description', 'TEXT')
                add_column_if_not_exists('images', 'ai_processed_date', 'TEXT'); add_column_if_not_exists('images', 'ai_llm_used', 'TEXT')
                add_column_if_not_exists('images', 'ai_language', 'TEXT'); add_column_if_not_exists('dog_detections', 'breed_source', 'TEXT')
                
                cursor.execute('PRAGMA foreign_keys = ON;')
            return True
        except Exception as e: messagebox.showerror(self.lang.get('error_title'), self.lang.get('db_create_error', e=e)); return False

    def validate_database_structure(self, db_path):
        REQUIRED_TABLES = {'persons':['id','full_name'], 'dogs':['id','name'], 'images':['id','filepath'], 'face_encodings':['id','person_id'], 'person_detections':['id','image_id'], 'dog_detections':['id','image_id']}
        try:
            with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'"); tables = {row[0] for row in cursor.fetchall()}
                if not set(REQUIRED_TABLES.keys()).issubset(tables): return False
            return True
        except Exception as e: self.log(f"Error reading database: {e}"); return False

    def select_database_file(self):
        if filepath := filedialog.askopenfilename(title=self.lang.get('select_db_title'), filetypes=[("SQLite DB", "*.db")]):
            if self.init_database(filepath):
                if self.validate_database_structure(filepath):
                    self.db_path = filepath; self.db_path_var.set(filepath); self.log(f"Active DB loaded and verified: {filepath}")
                    self.set_db_dependent_widgets_state(tk.NORMAL); self.refresh_people_list(); self.refresh_dogs_list()
                    self.update_status(self.lang.get('status_ready_db'), 'complete')
                else:
                    messagebox.showerror(self.lang.get('error_title'), self.lang.get('db_structure_error'))
                    self.db_path = None; self.db_path_var.set(""); self.set_db_dependent_widgets_state(tk.DISABLED)
            else: self.db_path = None; self.db_path_var.set(""); self.set_db_dependent_widgets_state(tk.DISABLED)

    def create_new_database(self):
        if filepath := filedialog.asksaveasfilename(title=self.lang.get('create_db_title'), defaultextension=".db", filetypes=[("SQLite DB", "*.db")]):
            if self.init_database(filepath):
                self.db_path = filepath; self.db_path_var.set(filepath); self.set_db_dependent_widgets_state(tk.NORMAL)
                self.refresh_people_list(); self.refresh_dogs_list(); self.log(f"New DB created and loaded: {filepath}")
                self.update_status(self.lang.get('status_new_db'), 'complete')
            else: self.db_path = None; self.db_path_var.set(""); self.set_db_dependent_widgets_state(tk.DISABLED)

    def select_reference_database(self):
        if filepath := filedialog.askopenfilename(title=self.lang.get('select_ref_db_title'), filetypes=[("SQLite DB", "*.db")]):
            if self.validate_database_structure(filepath): self.ref_db_path = filepath; self.ref_db_path_var.set(filepath); self.log(f"Reference DB loaded: {filepath}")
            else: self.log(self.lang.get('db_load_error'))

    def clear_reference_database(self): self.ref_db_path = None; self.ref_db_path_var.set(""); self.log("Reference DB cleared.")
    
    def browse_source(self):
        if directory := filedialog.askdirectory(title=self.lang.get('select_photo_dir_title')): self.source_dir.set(directory)
    
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
                cursor.execute('DELETE FROM images WHERE id = ?', (result[0],)); self.log(f"Old data for {os.path.basename(image_path)} has been deleted.")

    def display_image(self, image_path, annotated_image=None):
        try:
            image = Image.fromarray(cv2.cvtColor(annotated_image, cv2.COLOR_BGR2RGB)) if annotated_image is not None else orient_image(Image.open(image_path))
            self.image_label.update_idletasks()
            w, h = self.image_label.winfo_width(), self.image_label.winfo_height()
            max_w, max_h = (w - 20) if w > 20 else 700, (h - 20) if h > 20 else 700
            image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            self.displayed_photo = ImageTk.PhotoImage(image)
            self.image_label.config(image=self.displayed_photo)
        except Exception as e:
            self.log(f"Display error: {e}"); self.image_label.config(image=None); self.image_label.config(text=f"Failed to display\n{os.path.basename(image_path)}")

    def init_dog_models(self):
        """Initializes Torchvision models for dogs, displaying a progress bar."""
        if self.dog_det_model and self.dog_cls_model: return True
        self.log(f"Loading dog recognition models to device: {self.dog_device.upper()}...")
        original_stdout = sys.stdout; sys.stdout = self.stdout_redirector
        try:
            self.update_status(self.lang.get('status_loading_dog_models'), 'processing')
            det_w = tv_det.FasterRCNN_ResNet50_FPN_Weights.DEFAULT
            self.dog_det_model = tv_det.fasterrcnn_resnet50_fpn(weights=det_w, box_score_thresh=0.0, progress=True).eval().to(self.dog_device)
            self.dog_prep_det = det_w.transforms()
            cls_w = tv_cls.DenseNet121_Weights.DEFAULT
            self.dog_cls_model = tv_cls.densenet121(weights=cls_w, progress=True).eval().to(self.dog_device)
            self.dog_prep_cls = cls_w.transforms(); self.dog_labels_imagenet = cls_w.meta["categories"]
            self.log("Dog recognition models loaded successfully."); return True
        except Exception as e: self.log(f"Error loading Torchvision models: {e}"); return False
        finally: sys.stdout = original_stdout
            
    def start_processing(self):
        if not self.db_path: messagebox.showerror(self.lang.get('error_title'), self.lang.get('select_db_prompt')); return
        if not self.source_dir.get() or not os.path.exists(self.source_dir.get()): messagebox.showerror(self.lang.get('error_title'), self.lang.get('select_dir_prompt')); return
        if not self.processing:
            self.processing = True; self.start_btn.config(state=tk.DISABLED); self.stop_btn.config(state=tk.NORMAL); self.update_status(self.lang.get('status_initializing'), 'processing')
            try:
                if not self.init_dog_models(): raise Exception("Failed to load dog recognition models.")
                if self.yolo is None or self.loaded_yolo_model_name != self.yolo_model.get():
                    model_file = Path(self.yolo_model.get())
                    if not model_file.exists():
                        self.log(f"YOLO model '{model_file}' not found. Download will begin..."); self.log("This may take a moment. The application has not frozen.")
                        self.update_status(self.lang.get('status_loading_yolo', model=model_file), 'processing')
                    self.log(f"Loading YOLO model: {self.yolo_model.get()}..."); self.yolo = YOLO(self.yolo_model.get()); self.loaded_yolo_model_name = self.yolo_model.get()
                    self.log(f"YOLO model {self.yolo_model.get()} loaded.")
            except Exception as e:
                self.log(f"Model initialization error: {e}"); self.processing = False; self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED); self.update_status(self.lang.get('status_error'), 'error'); return
            threading.Thread(target=self.process_images, daemon=True).start()

    def stop_processing(self): self.processing = False; self.log("Stopping process..."); self.update_status(self.lang.get('status_stopping'), 'idle'); self.start_btn.config(state=tk.NORMAL); self.stop_btn.config(state=tk.DISABLED)

    def refresh_people_list(self):
        if not self.db_path: return
        for item in self.people_tree.get_children(): self.people_tree.delete(item)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT p.id, CASE WHEN p.is_known THEN 'Known' ELSE 'Unknown' END, p.full_name, p.short_name, COUNT(DISTINCT pd.image_id), p.notes FROM persons p LEFT JOIN person_detections pd ON p.id = pd.person_id GROUP BY p.id ORDER BY p.is_known DESC, p.full_name")
                for row in cursor.fetchall(): self.people_tree.insert('', tk.END, values=row)
        except Exception as e: self.log(f"Error refreshing people list: {e}")

    def refresh_dogs_list(self):
        if not self.db_path: return
        for item in self.dogs_tree.get_children(): self.dogs_tree.delete(item)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT d.id, CASE WHEN d.is_known THEN 'Known' ELSE 'Unknown' END, d.name, d.breed, d.owner, COUNT(DISTINCT dd.image_id), d.notes FROM dogs d LEFT JOIN dog_detections dd ON d.id = dd.dog_id GROUP BY d.id ORDER BY d.is_known DESC, d.name")
                for row in cursor.fetchall(): self.dogs_tree.insert('', tk.END, values=row)
        except Exception as e: self.log(f"Error refreshing dogs list: {e}")

    def edit_person(self): messagebox.showinfo(self.lang.get('info_title'), self.lang.get('edit_unimplemented'))

    def delete_person(self):
        if not (sel := self.people_tree.selection()): messagebox.showwarning(self.lang.get('warning_title'), self.lang.get('select_person_prompt')); return
        if messagebox.askyesno(self.lang.get('delete_button'), self.lang.get('delete_person_confirm')):
            person_id = self.people_tree.item(sel[0])['values'][0]
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor(); cursor.execute('PRAGMA foreign_keys = ON;'); cursor.execute('DELETE FROM persons WHERE id = ?', (person_id,))
                self.refresh_people_list(); messagebox.showinfo(self.lang.get('success_title'), self.lang.get('delete_person_success'))
            except Exception as e: messagebox.showerror(self.lang.get('error_title'), self.lang.get('delete_person_fail', e=e))

    def edit_dog(self): messagebox.showinfo(self.lang.get('info_title'), self.lang.get('edit_unimplemented'))
    
    def delete_dog(self):
        if not (sel := self.dogs_tree.selection()): messagebox.showwarning(self.lang.get('warning_title'), self.lang.get('select_dog_prompt')); return
        if messagebox.askyesno(self.lang.get('delete_button'), self.lang.get('delete_dog_confirm')):
            dog_id = self.dogs_tree.item(sel[0])['values'][0]
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor(); cursor.execute('PRAGMA foreign_keys = ON;'); cursor.execute('DELETE FROM dogs WHERE id = ?', (dog_id,));
                self.refresh_dogs_list(); messagebox.showinfo(self.lang.get('success_title'), self.lang.get('delete_dog_success'))
            except Exception as e: messagebox.showerror(self.lang.get('error_title'), self.lang.get('delete_dog_fail', e=e))

    def get_existing_persons(self, db_path=None):
        target_db = db_path or self.db_path;
        if not target_db: return []
        try:
            with sqlite3.connect(f'file:{target_db}?mode=ro', uri=True) as conn:
                conn.row_factory = sqlite3.Row; cursor = conn.cursor()
                cursor.execute('SELECT id, full_name, short_name, notes FROM persons WHERE is_known = 1 ORDER BY full_name')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e: self.log(f"Error reading list of people from {os.path.basename(target_db)}: {e}"); return []

    def get_existing_dogs(self, db_path=None):
        target_db = db_path or self.db_path;
        if not target_db: return []
        try:
            with sqlite3.connect(f'file:{target_db}?mode=ro', uri=True) as conn:
                conn.row_factory = sqlite3.Row; cursor = conn.cursor()
                cursor.execute('SELECT id, name, breed, owner, notes FROM dogs WHERE is_known = 1 ORDER BY name')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e: self.log(f"Error reading list of dogs from {os.path.basename(target_db)}: {e}"); return []

    def show_person_dialog_main(self, data):
        image, face_location, face_encoding, callback = data
        ref_persons = self.get_existing_persons(self.ref_db_path) if self.ref_db_path else []
        dialog = PersonDialog(self.root, image, face_location, self.lang, self.get_existing_persons(), ref_persons, self.db_path)
        self.root.wait_window(dialog); callback(dialog.result)

    def show_dog_dialog_main(self, data):
        image, dog_bbox, callback, breed = data
        ref_dogs = self.get_existing_dogs(self.ref_db_path) if self.ref_db_path else []
        dialog = DogDialog(self.root, image, dog_bbox, self.lang, self.get_existing_dogs(), ref_dogs, self.db_path, breed=breed)
        self.root.wait_window(dialog); callback(dialog.result)

    def show_body_dialog_main(self, data):
        image, body_bbox, callback = data
        existing_persons = self.get_existing_persons(); ref_persons = self.get_existing_persons(db_path=self.ref_db_path) if self.ref_db_path else []
        dialog = BodyWithoutFaceDialog(self.root, image, body_bbox, self.lang, existing_persons, ref_persons, self.db_path)
        self.root.wait_window(dialog); callback(dialog.result)
    
    def show_confirm_person_dialog_main(self, data):
        image, face_location, person_info, callback = data
        dialog = ConfirmPersonDialog(self.root, image, face_location, person_info, self.lang)
        self.root.wait_window(dialog); callback(dialog.result)

    def show_processed_dialog_main(self, data):
        image_path, callback = data
        dialog = ProcessedImageDialog(self.root, image_path, self.lang)
        self.root.wait_window(dialog); callback(dialog.result, dialog.apply_to_all)

    def create_or_update_person(self, result, conn):
        cursor = conn.cursor(); now = datetime.now().isoformat(); person_id = None
        if result['action'] == 'new_known':
            cursor.execute('INSERT INTO persons (is_known, full_name, short_name, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?)',(result['full_name'], result['short_name'], result['notes'], now, now)); person_id = cursor.lastrowid
            self.log(f"  Created new person: {result['full_name']} (ID: {person_id})"); self.update_queue.put(('refresh_people', None))
        elif result['action'] == 'local_known':
            cursor.execute('INSERT INTO persons (is_known, full_name, short_name, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?)', (result['full_name'], result['short_name'], result['notes'], now, now)); person_id = cursor.lastrowid
            self.log(f"  Created new person (no face): {result['full_name']} (ID: {person_id})"); self.update_queue.put(('refresh_people', None))   
        elif result['action'] == 'unknown':
            cursor.execute('INSERT INTO persons (is_known, created_date, updated_date) VALUES (0, ?, ?)',(now, now)); person_id = cursor.lastrowid
            self.log(f"  Added an unknown person (ID: {person_id})")
        elif result['action'] == 'existing':
            person_id = result['person_id']; self.log(f"  Selected existing person (ID: {person_id})")
        elif result['action'] == 'existing_ref': pass
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
            self.log(f"  Person '{person_info['full_name']}' already exists in the active DB. ID: {result[0]}"); return result[0]
        else:
            now = datetime.now().isoformat()
            cursor.execute('INSERT INTO persons (is_known, full_name, short_name, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?)',
                           (person_info['full_name'], person_info['short_name'], person_info.get('notes', ''), now, now))
            new_id = cursor.lastrowid; self.log(f"  Person '{person_info['full_name']}' imported into the active DB. New ID: {new_id}"); self.update_queue.put(('refresh_people', None)); return new_id
    
    def get_or_create_dog_by_name(self, dog_info, conn):
        cursor = conn.cursor(); cursor.execute("SELECT id FROM dogs WHERE name = ?", (dog_info['name'],))
        if result := cursor.fetchone():
            self.log(f"  Dog '{dog_info['name']}' already exists in the active DB. ID: {result[0]}"); return result[0]
        else:
            now = datetime.now().isoformat()
            cursor.execute('INSERT INTO dogs (is_known, name, breed, owner, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?, ?)',
                           (dog_info['name'], dog_info.get('breed', ''), dog_info.get('owner', ''), dog_info.get('notes', ''), now, now))
            new_id = cursor.lastrowid; self.log(f"  Dog '{dog_info['name']}' imported into the active DB. New ID: {new_id}"); self.update_queue.put(('refresh_dogs', None)); return new_id

    def get_name_from_db(self, entity_id, conn, entity_type='person'):
        if not entity_id: return "Unknown"
        table, column = ('persons', 'short_name') if entity_type == 'person' else ('dogs', 'name')
        try: cursor = conn.cursor(); cursor.execute(f'SELECT {column} FROM {table} WHERE id = ?', (entity_id,)); return (result[0] if (result := cursor.fetchone()) else None) or "Unknown"
        except Exception: return "Unknown"

    def identify_person(self, face_encoding_to_check, db_path, main_conn=None):
        if not db_path: return None
        conn = main_conn if main_conn and db_path == self.db_path else sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        try:
            conn.row_factory = sqlite3.Row; cursor = conn.cursor()
            cursor.execute("SELECT p.id, p.full_name, p.short_name, p.notes, fe.face_encoding FROM face_encodings fe JOIN persons p ON fe.person_id = p.id WHERE p.is_known = 1")
            rows = cursor.fetchall();
            if not rows: return None
            known_face_encodings, known_face_metadata = [], []
            for row in rows:
                try: known_face_encodings.append(np.array(json.loads(row['face_encoding']))); known_face_metadata.append(dict(row))
                except (json.JSONDecodeError, TypeError): continue
            if not known_face_encodings: return None
            distances = face_recognition.face_distance(known_face_encodings, face_encoding_to_check)
            if len(distances) == 0: return None
            best_match_index = np.argmin(distances)
            if distances[best_match_index] < self.face_threshold.get(): return known_face_metadata[best_match_index]
        except Exception as e: self.log(f"Identification error in {os.path.basename(db_path)}: {e}")
        finally:
            if not main_conn or (main_conn and db_path != self.db_path): conn.close()
        return None

    def _identify_person(self, person_obj, image, conn, already_assigned_ids):
        if person_obj.get('has_face'):
            identified_person_id = None
            match = self.identify_person(person_obj['face_encoding'], self.db_path, main_conn=conn)
            if match and match['id'] not in already_assigned_ids:
                identified_person_id = match['id']; self.log(f"  Recognized (main DB): {match['short_name']} (ID: {match['id']})")
            elif self.ref_db_path:
                ref_match = self.identify_person(person_obj['face_encoding'], self.ref_db_path)
                if ref_match:
                    dialog_event = threading.Event(); dialog_result = {}; cb = lambda r: (dialog_result.update({'result': r}), dialog_event.set())
                    self.update_queue.put(('show_confirm_person_dialog', (image, person_obj['face_location'], ref_match, cb))); dialog_event.wait()
                    if dialog_result.get('result', {}).get('confirmed'):
                        person_info_from_ref = dialog_result['result']['person_info']
                        potential_id = self.get_or_create_person_by_name(person_info_from_ref, conn)
                        if potential_id and potential_id not in already_assigned_ids: identified_person_id = potential_id
                        else: self.log(f"  Skipped assignment of '{person_info_from_ref['short_name']}' (ID={potential_id}) as it's already assigned in this photo.")
            if identified_person_id: person_obj['person_id'] = identified_person_id
            else:
                dialog_event = threading.Event(); dialog_result = {}; cb = lambda r: (dialog_result.update({'result': r}), dialog_event.set())
                self.update_queue.put(('show_person_dialog', (image, person_obj['face_location'], person_obj['face_encoding'], cb))); dialog_event.wait()
                if person_result := dialog_result.get('result'):
                    if person_id := self.create_or_update_person(person_result, conn): person_obj['person_id'] = person_id
        else: # Person without face
            dialog_event = threading.Event(); dialog_result = {}; cb = lambda r: (dialog_result.update({'result': r}), dialog_event.set())
            self.update_queue.put(('show_body_dialog', (image, person_obj['bbox'], cb))); dialog_event.wait()
            if person_result := dialog_result.get('result'):
                action = person_result['action']; person_id_to_assign = None
                if action == 'existing': person_id_to_assign = person_result['person_id']
                elif action == 'existing_ref': person_id_to_assign = self.get_or_create_person_by_name(person_result['person_info'], conn)
                elif action == 'local_known':
                    person_id_to_assign = self.create_or_update_person(person_result, conn)
                    person_obj.update({'is_locally_identified': True, 'local_full_name': person_result['full_name'], 'local_short_name': person_result['short_name'], 'local_notes': person_result['notes']})
                elif action == 'unknown': person_id_to_assign = self.create_or_update_person(person_result, conn)
                if person_id_to_assign is not None and person_id_to_assign not in already_assigned_ids: person_obj['person_id'] = person_id_to_assign
                elif person_id_to_assign is not None: self.log(f"  Skipped assignment of ID={person_id_to_assign} as it's already assigned in this photo.")
        return person_obj

    def detect_dogs_torchvision(self, pil_image):
        """Detects dogs and their breeds using Torchvision models."""
        self.log("  Running dog detection (Torchvision)..."); DOG_COCO_CLASS = 18; threshold = self.dog_detection_threshold.get()
        with torch.no_grad(): out = self.dog_det_model(self.dog_prep_det(pil_image).unsqueeze(0).to(self.dog_device))[0]
        detected_dogs = []
        for i, (box, label, score) in enumerate(zip(out["boxes"], out["labels"], out["scores"])):
            if label.item() == DOG_COCO_CLASS and score.item() >= threshold:
                crop = pil_image.crop((box[0].item(), box[1].item(), box[2].item(), box[3].item()))
                with torch.no_grad(): probs = torch.softmax(self.dog_cls_model(self.dog_prep_cls(crop).unsqueeze(0).to(self.dog_device)), 1)[0]
                idx = int(probs.argmax()); breed_p = probs[idx].item(); breed = self.dog_labels_imagenet[idx]
                detected_dogs.append({'dog_index': i, 'bbox': [int(c) for c in box.cpu().numpy()], 'confidence': score.item(), 'breed': breed.split(',')[0].capitalize(), 'breed_confidence': breed_p})
        self.log(f"  Torchvision detected: {len(detected_dogs)} dog(s)."); return detected_dogs

    def analyze_image(self, image_path, image_id, conn):
        try:
            pil_image = Image.open(image_path).convert("RGB"); oriented_pil_image = orient_image(pil_image)
            image = cv2.cvtColor(np.array(oriented_pil_image), cv2.COLOR_RGB2BGR); rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            self.log("  Running person detection (YOLO) and face recognition...")
            person_detections = []
            if results := self.yolo(image, conf=self.yolo_person_conf.get(), classes=[0]):
                if results[0].boxes:
                    for i, box in enumerate(results[0].boxes):
                        x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy()); confidence = float(box.conf[0])
                        person_detections.append({'person_index': i, 'bbox': [x1, y1, x2, y2], 'confidence': confidence, 'has_face': False})
            self.log(f"  YOLO detected: {len(person_detections)} person(s).")
            model_name = 'cnn' if self.lang.get('face_model_accurate') in self.face_model.get() else 'hog'
            self.log(f"  Using face recognition model: {model_name.upper()}")
            face_locations = face_recognition.face_locations(rgb_image, model=model_name)
            face_encodings = face_recognition.face_encodings(rgb_image, face_locations); self.log(f"  Found {len(face_locations)} face(s).")
            unmatched_faces = []
            for face_idx, (face_location, face_encoding) in enumerate(zip(face_locations, face_encodings)):
                top, right, bottom, left = face_location; face_center_x, face_center_y = (left + right) // 2, (top + bottom) // 2
                best_person_idx, best_overlap = -1, 0
                for person_idx, person in enumerate(person_detections):
                    if person.get('has_face'): continue
                    px1, py1, px2, py2 = person['bbox']
                    if px1 <= face_center_x <= px2 and py1 <= face_center_y <= py2:
                        x1_i, y1_i, x2_i, y2_i = max(left, px1), max(top, py1), min(right, px2), min(bottom, py2)
                        if x2_i > x1_i and y2_i > y1_i:
                            intersection = (x2_i - x1_i) * (y2_i - y1_i); face_area = (right - left) * (bottom - top)
                            if face_area > 0 and (overlap := intersection / face_area) > best_overlap: best_overlap, best_person_idx = overlap, person_idx
                if best_person_idx != -1 and best_overlap > 0.5: person_detections[best_person_idx].update({'has_face': True, 'face_encoding': face_encoding, 'face_location': face_location})
                else: unmatched_faces.append({'face_location': face_location, 'face_encoding': face_encoding})
            all_people_to_process = person_detections[:]
            for f in unmatched_faces: f['bbox'] = [f['face_location'][3], f['face_location'][0], f['face_location'][1], f['face_location'][2]]; f['has_face'] = True; f['person_index'] = -1; all_people_to_process.append(f)
            def get_sort_key(p):
                has_face = p.get('has_face', False)
                if has_face: area = (p['face_location'][2] - p['face_location'][0]) * (p['face_location'][1] - p['face_location'][3]); return (1, area)
                else: area = (p['bbox'][2] - p['bbox'][0]) * (p['bbox'][3] - p['bbox'][1]); return (0, area)
            all_people_to_process.sort(key=get_sort_key, reverse=True); self.log("  Person objects sorted for processing (largest faces first).")
            final_person_detections = []; assigned_ids_this_photo = set()
            for person_obj in all_people_to_process:
                if not self.processing: break
                processed_person = self._identify_person(person_obj, image, conn, assigned_ids_this_photo)
                if processed_person.get('person_id'): assigned_ids_this_photo.add(processed_person['person_id'])
                final_person_detections.append(processed_person)
            dog_detections = self.detect_dogs_torchvision(oriented_pil_image)
            for dog in dog_detections:
                if not self.processing: break
                dialog_event = threading.Event(); dialog_result = {}; cb = lambda r: (dialog_result.update({'result': r}), dialog_event.set())
                self.update_queue.put(('show_dog_dialog', (image, dog['bbox'], cb, dog['breed']))); dialog_event.wait()
                if res := dialog_result.get('result'):
                    if res['action'] == 'existing_ref': dog['dog_id'] = self.get_or_create_dog_by_name(res['dog_info'], conn)
                    else:
                        if res['action'] == 'new_known' and not res.get('breed'): res['breed'] = dog['breed']
                        dog['dog_id'] = self.create_or_update_dog(res, conn)
            annotated_image = image.copy()
            for person in final_person_detections:
                p_id = person.get('person_id'); name = person.get('local_short_name') or self.get_name_from_db(p_id, conn, 'person'); x1, y1, x2, y2 = person['bbox']
                cv2.rectangle(annotated_image, (x1, y1), (x2, y2), (255, 0, 0), 2); cv2.putText(annotated_image, name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)
                if person.get('has_face'): top, right, bottom, left = person['face_location']; cv2.rectangle(annotated_image, (left, top), (right, bottom), (0, 255, 0), 2)
            for dog in dog_detections:
                d_id = dog.get('dog_id'); name = self.get_name_from_db(d_id, conn, 'dog'); x1, y1, x2, y2 = dog['bbox']
                label = f"{name} ({dog['breed']})" if name != "Unknown" else dog['breed']
                cv2.rectangle(annotated_image, (x1, y1), (x2, y2), (0, 0, 255), 2); cv2.putText(annotated_image, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
            return len(final_person_detections), len(face_locations), len(dog_detections), final_person_detections, annotated_image, dog_detections
        except Exception as e: self.log(f"Critical error during image analysis: {e}\n{traceback.format_exc()}"); return 0, 0, 0, [], None, []

    def save_to_database(self, image_id, person_detections, dog_detections, conn):
        try:
            cursor = conn.cursor()
            for person in person_detections:
                person_id, face_encoding_id = person.get('person_id'), None
                if person_id and person.get('has_face'):
                    cursor.execute("SELECT is_known FROM persons WHERE id = ?", (person_id,))
                    if (is_known_res := cursor.fetchone()) and is_known_res[0] == 1:
                        self.log(f"  Adding new face vector for Person ID: {person_id}"); enc_str = json.dumps(person['face_encoding'].tolist()); loc_str = json.dumps(person['face_location'])
                        cursor.execute('INSERT INTO face_encodings (person_id, image_id, face_encoding, face_location) VALUES (?, ?, ?, ?)',(person_id, image_id, enc_str, loc_str)); face_encoding_id = cursor.lastrowid
                cursor.execute("INSERT INTO person_detections (image_id, person_id, person_index, bbox, confidence, has_face, face_encoding_id, is_locally_identified, local_full_name, local_short_name, local_notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (image_id, person_id, person.get('person_index', -1), json.dumps(person['bbox']), person.get('confidence', 1.0), person.get('has_face', False), face_encoding_id, person.get('is_locally_identified', False), person.get('local_full_name'), person.get('local_short_name'), person.get('local_notes')))
            for dog in dog_detections:
                cursor.execute('INSERT INTO dog_detections (image_id, dog_id, dog_index, bbox, confidence, breed_source) VALUES (?, ?, ?, ?, ?, ?)', (image_id, dog.get('dog_id'), dog.get('dog_index'), json.dumps(dog['bbox']), dog['confidence'], dog['breed']))
        except Exception as e: self.log(f"Error saving to database: {e}\n{traceback.format_exc()}")

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
            self.log(f"Found {len(image_files)} images to process."); self.processed_decision_for_all = None
            for i, image_path in enumerate(image_files):
                if not self.processing: self.log("Processing stopped by user."); break
                self.update_status(self.lang.get('status_processing', current=i+1, total=len(image_files), filename=os.path.basename(image_path)), 'processing'); self.log(f"\nProcessing: {os.path.basename(image_path)}"); self.update_image(image_path)
                if self.is_image_processed(image_path):
                    decision = self.processed_decision_for_all
                    if not decision:
                        process_mode = self.processed_mode.get()
                        if process_mode == 'ask':
                            dialog_event = threading.Event(); dialog_res = {}; cb = lambda res, apply_all: (dialog_res.update({'res':res, 'apply_all':apply_all}), dialog_event.set())
                            self.update_queue.put(('show_processed_dialog', (image_path, cb))); dialog_event.wait()
                            decision = dialog_res.get('res')
                            if dialog_res.get('apply_all'): self.processed_decision_for_all = decision
                        else: decision = process_mode
                    if decision == 'cancel': self.log("Processing cancelled."); break
                    if decision == 'skip': self.log("  Skipped (already processed)."); continue
                    self.clear_image_data(image_path)

                with sqlite3.connect(self.db_path, timeout=10) as conn:
                    cursor = conn.cursor(); cursor.execute('PRAGMA foreign_keys = ON;')
                    file_stat = os.stat(image_path); created_date, now = datetime.fromtimestamp(file_stat.st_ctime).isoformat(), datetime.now().isoformat()
                    cursor.execute('INSERT INTO images (filename, filepath, created_date, file_size, processed_date) VALUES (?, ?, ?, ?, ?)',(os.path.basename(image_path), image_path, created_date, file_stat.st_size, now)); image_id = cursor.lastrowid
                    num_bodies, num_faces, num_dogs, person_detections, annotated_image, dog_detections = self.analyze_image(image_path, image_id, conn)
                    self.update_image(image_path, annotated_image); self.log(f"  Found: {num_bodies} bodies, {num_faces} faces, {num_dogs} dogs.")
                    cursor.execute('UPDATE images SET num_bodies = ?, num_faces = ?, num_dogs = ? WHERE id = ?', (num_bodies, num_faces, num_dogs, image_id))
                    self.save_to_database(image_id, person_detections, dog_detections, conn)
            self.log(f"\n{self.lang.get('status_complete')}!"); self.update_status(self.lang.get('status_complete'), 'complete'); self.update_queue.put(('refresh_people', None)); self.update_queue.put(('refresh_dogs', None))
        except Exception as e: self.log(f"Critical error in processing loop: {e}\n{traceback.format_exc()}"); self.update_status(self.lang.get('status_error'), 'error')
        finally: self.processing = False; self.update_queue.put(('enable_buttons', None))

def main():
    root = tk.Tk()
    app = FaceDetectionV2(root)
    root.mainloop()

if __name__ == "__main__":
    # This is recommended for PyTorch multiprocessing/multithreading on Windows
    # https://pytorch.org/docs/stable/notes/windows.html#multiprocessing-error-without-if-clause-protection
    main()