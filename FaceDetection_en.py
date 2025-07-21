"""
Face Detection v3.9en
A program to recognize and catalog people and dogs in photographs.

Version: 3.9en
- Full translation of the entire user interface, comments, and log messages
  from Russian to English.

Version: 3.9.0
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
VERSION = "3.9en"

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
    def __init__(self, parent, image_path):
        super().__init__(parent)
        self.parent = parent; self.result = None; self.apply_to_all = False
        self.title("Image Already Processed"); self.resizable(False, False); self.transient(parent); self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        main_frame = ttk.Frame(self, padding="20"); main_frame.pack(fill=tk.BOTH, expand=True)
        message = f"The image '{os.path.basename(image_path)}' has been processed before.\nProcess it again?"
        ttk.Label(main_frame, text=message, wraplength=450).pack(pady=10)
        self.apply_to_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(main_frame, text="Apply this decision to all subsequent images", variable=self.apply_to_all_var).pack(pady=10)
        button_frame = ttk.Frame(main_frame); button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        ttk.Button(button_frame, text="Yes, Process", command=self.process).pack(side=tk.LEFT, padx=5, expand=True)
        ttk.Button(button_frame, text="No, Skip", command=self.skip).pack(side=tk.LEFT, padx=5, expand=True)
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side=tk.RIGHT, padx=5, expand=True)
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
        self.title("Person Identification"); self.resizable(True, True); self.transient(parent); self.grab_set(); self.protocol("WM_DELETE_WINDOW", self.save_unknown)
        main_frame = ttk.Frame(self); main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        face_frame = ttk.Frame(main_frame); face_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        top, right, bottom, left = face_location; face_img = image[top:bottom, left:right]; face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB); face_img = Image.fromarray(face_img)
        face_img.thumbnail((150, 150), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(face_img)
        face_label = ttk.Label(face_frame, image=photo); face_label.image = photo; face_label.pack()
        ttk.Label(face_frame, text="New person detected", font=('Arial', 12, 'bold')).pack(pady=5)
        self.notebook = ttk.Notebook(main_frame); self.notebook.pack(fill=tk.BOTH, expand=True)
        new_person_frame = ttk.Frame(self.notebook); self.notebook.add(new_person_frame, text="New Person")
        input_frame = ttk.Frame(new_person_frame, padding="20"); input_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(input_frame, text="Full Name:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5); self.full_name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.full_name_var, width=40).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text="Short Name:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5); self.short_name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.short_name_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text="Notes:").grid(row=2, column=0, sticky=tk.W+tk.N, padx=5, pady=5); text_frame = ttk.Frame(input_frame); text_frame.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        self.notes_text = tk.Text(text_frame, width=40, height=4, wrap=tk.WORD); notes_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.notes_text.yview); self.notes_text.configure(yscrollcommand=notes_scroll.set)
        self.notes_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); notes_scroll.pack(side=tk.RIGHT, fill=tk.Y); input_frame.columnconfigure(1, weight=1)
        if self.existing_persons:
            existing_frame = ttk.Frame(self.notebook); self.notebook.add(existing_frame, text="Select from DB")
            tree_frame = ttk.Frame(existing_frame, padding="10"); tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', 'Full Name', 'Short Name'); self.person_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.person_tree.heading(col, text=col); self.person_tree.column(col, width=50 if col == 'ID' else 200)
            tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.person_tree.yview); self.person_tree.configure(yscrollcommand=tree_scroll.set)
            for person in self.existing_persons: self.person_tree.insert('', tk.END, values=(person['id'], person['full_name'], person['short_name']))
            self.person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        if self.ref_persons:
            ref_frame = ttk.Frame(self.notebook); self.notebook.add(ref_frame, text="Select from Ref DB")
            ref_tree_frame = ttk.Frame(ref_frame, padding="10"); ref_tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', 'Full Name', 'Short Name'); self.ref_person_tree = ttk.Treeview(ref_tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.ref_person_tree.heading(col, text=col); self.ref_person_tree.column(col, width=50 if col == 'ID' else 200)
            ref_tree_scroll = ttk.Scrollbar(ref_tree_frame, orient="vertical", command=self.ref_person_tree.yview); self.ref_person_tree.configure(yscrollcommand=ref_tree_scroll.set)
            for person in self.ref_persons: self.ref_person_tree.insert('', tk.END, values=(person['id'], person['full_name'], person['short_name']))
            self.ref_person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); ref_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        button_frame = ttk.Frame(self); button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10); left_buttons = ttk.Frame(button_frame); left_buttons.pack(side=tk.LEFT); right_buttons = ttk.Frame(button_frame); right_buttons.pack(side=tk.RIGHT)
        ttk.Button(left_buttons, text="Save as Known", command=self.save_known).pack(side=tk.LEFT, padx=5)
        ttk.Button(left_buttons, text="Leave as Unknown", command=self.save_unknown).pack(side=tk.LEFT, padx=5)
        ttk.Button(right_buttons, text="Cancel", command=self.cancel).pack(side=tk.RIGHT, padx=5)
        self.center_window(); self.full_name_var.set(""); self.notebook.select(0); self.after(100, lambda: self.focus_force())

    def check_person_exists(self, full_name, short_name):
        if not self.db_path: return False, []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, full_name, short_name FROM persons WHERE is_known = 1 AND full_name = ? AND short_name = ?', (full_name, short_name)); return (dups := cursor.fetchall()), dups

    def save_known(self):
        try: active_tab_text = self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError: active_tab_text = "New Person"
        if active_tab_text == "New Person":
            full_name = self.full_name_var.get().strip(); short_name = self.short_name_var.get().strip() or full_name.split()[0]
            if not full_name: messagebox.showwarning("Warning", "Please enter a full name.", parent=self); return
            exists, duplicates = self.check_person_exists(full_name, short_name)
            if exists: messagebox.showwarning("Person Exists", f"A person with these names already exists in the database:\n\nFull Name: {duplicates[0][1]}\nShort Name: {duplicates[0][2]}\n\nIf this is a different person, change the name. If it's the same person, select them from the appropriate tab.", parent=self); return
            self.result = {'action': 'new_known', 'full_name': full_name, 'short_name': short_name, 'notes': self.notes_text.get('1.0', tk.END).strip()}; self.destroy()
        elif active_tab_text == "Select from DB":
            if not hasattr(self, 'person_tree') or not (selection := self.person_tree.selection()): messagebox.showwarning("Warning", "Please select a person from the list.", parent=self); return
            self.result = {'action': 'existing', 'person_id': self.person_tree.item(selection[0])['values'][0]}; self.destroy()
        elif active_tab_text == "Select from Ref DB":
            if not hasattr(self, 'ref_person_tree') or not (selection := self.ref_person_tree.selection()): messagebox.showwarning("Warning", "Please select a person from the list.", parent=self); return
            selected_id = self.ref_person_tree.item(selection[0])['values'][0]
            person_info = next((p for p in self.ref_persons if p['id'] == selected_id), None)
            self.result = {'action': 'existing_ref', 'person_info': person_info}; self.destroy()

    def save_unknown(self): self.result = {'action': 'unknown'}; self.destroy()
    def cancel(self): self.result = None; self.destroy()

class DogDialog(BaseDialog):
    def __init__(self, parent, image, dog_bbox, existing_dogs=None, ref_dogs=None, db_path=None, breed=None):
        super().__init__(parent); self.parent = parent; self.result = None
        self.existing_dogs = existing_dogs or []; self.ref_dogs = ref_dogs or []; self.db_path = db_path
        self.title("Dog Identification"); self.resizable(True, True); self.transient(parent); self.grab_set(); self.protocol("WM_DELETE_WINDOW", self.save_unknown)
        main_frame = ttk.Frame(self); main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        dog_frame = ttk.Frame(main_frame); dog_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        x1, y1, x2, y2 = dog_bbox; dog_img = image[y1:y2, x1:x2]; dog_img = cv2.cvtColor(dog_img, cv2.COLOR_BGR2RGB); dog_img = Image.fromarray(dog_img)
        dog_img.thumbnail((200, 200), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(dog_img)
        dog_label = ttk.Label(dog_frame, image=photo); dog_label.image = photo; dog_label.pack()
        ttk.Label(dog_frame, text="Dog detected", font=('Arial', 12, 'bold')).pack(pady=5)
        self.notebook = ttk.Notebook(main_frame); self.notebook.pack(fill=tk.BOTH, expand=True)
        new_dog_frame = ttk.Frame(self.notebook); self.notebook.add(new_dog_frame, text="New Dog")
        input_frame = ttk.Frame(new_dog_frame, padding="20"); input_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(input_frame, text="Name:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5); self.name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.name_var, width=40).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text="Breed:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5); self.breed_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.breed_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text="Owner:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5); self.owner_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.owner_var, width=40).grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text="Notes:").grid(row=3, column=0, sticky=tk.W+tk.N, padx=5, pady=5); text_frame = ttk.Frame(input_frame); text_frame.grid(row=3, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        self.notes_text = tk.Text(text_frame, width=40, height=3, wrap=tk.WORD); self.notes_text.pack(fill=tk.BOTH, expand=True); input_frame.columnconfigure(1, weight=1)
        
        if breed:
            self.breed_var.set(breed)

        if self.existing_dogs:
            existing_frame = ttk.Frame(self.notebook); self.notebook.add(existing_frame, text="Select from DB")
            tree_frame = ttk.Frame(existing_frame, padding="10"); tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', 'Name', 'Breed', 'Owner'); self.dog_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.dog_tree.heading(col, text=col); self.dog_tree.column(col, width=50 if col == 'ID' else 180)
            tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.dog_tree.yview); self.dog_tree.configure(yscrollcommand=tree_scroll.set)
            for dog in self.existing_dogs: self.dog_tree.insert('', tk.END, values=(dog['id'], dog['name'], dog['breed'] or 'N/A', dog['owner'] or 'N/A'))
            self.dog_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        if self.ref_dogs:
            ref_frame = ttk.Frame(self.notebook); self.notebook.add(ref_frame, text="Select from Ref DB")
            ref_tree_frame = ttk.Frame(ref_frame, padding="10"); ref_tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', 'Name', 'Breed', 'Owner'); self.ref_dog_tree = ttk.Treeview(ref_tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.ref_dog_tree.heading(col, text=col); self.ref_dog_tree.column(col, width=50 if col == 'ID' else 180)
            ref_tree_scroll = ttk.Scrollbar(ref_tree_frame, orient="vertical", command=self.ref_dog_tree.yview); self.ref_dog_tree.configure(yscrollcommand=ref_tree_scroll.set)
            for dog in self.ref_dogs: self.ref_dog_tree.insert('', tk.END, values=(dog['id'], dog['name'], dog['breed'] or '', dog['owner'] or ''))
            self.ref_dog_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); ref_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        button_frame = ttk.Frame(self); button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10); left_button_frame = ttk.Frame(button_frame); left_button_frame.pack(side=tk.LEFT); right_button_frame = ttk.Frame(button_frame); right_button_frame.pack(side=tk.RIGHT)
        ttk.Button(left_button_frame, text="Save as Known", command=self.save_known).pack(side=tk.LEFT, padx=5); ttk.Button(left_button_frame, text="Leave as Unknown", command=self.save_unknown).pack(side=tk.LEFT, padx=5)
        ttk.Button(right_button_frame, text="Cancel", command=self.cancel).pack(side=tk.RIGHT, padx=5)
        self.center_window()

    def check_dog_exists(self, name, breed, owner):
        if not self.db_path: return False, []
        with sqlite3.connect(self.db_path) as conn:
            cursor=conn.cursor(); cursor.execute('SELECT id, name, breed, owner FROM dogs WHERE is_known=1 AND name=? AND(? = "" OR breed = ? ) AND (? = "" OR owner = ?)', (name, breed, breed, owner, owner)); return (dups := cursor.fetchall()), dups

    def save_known(self):
        try: active_tab_text = self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError: active_tab_text = "New Dog"
        if active_tab_text == "New Dog":
            name = self.name_var.get().strip(); breed = self.breed_var.get().strip(); owner = self.owner_var.get().strip()
            if not name: messagebox.showwarning("Warning", "Please enter the dog's name.", parent=self); return
            exists, duplicates = self.check_dog_exists(name, breed, owner)
            if exists: messagebox.showwarning("Dog Exists", f"A dog with this information already exists in the DB:\nName: {duplicates[0][1]}\nBreed: {duplicates[0][2]}\nOwner: {duplicates[0][3]}", parent=self); return
            self.result = {'action':'new_known', 'name':name, 'breed':breed, 'owner':owner, 'notes':self.notes_text.get('1.0', tk.END).strip()}; self.destroy()
        elif active_tab_text == "Select from DB":
            if not hasattr(self, 'dog_tree') or not (selection := self.dog_tree.selection()): messagebox.showwarning("Warning", "Please select a dog from the list.", parent=self); return
            self.result = {'action':'existing', 'dog_id':self.dog_tree.item(selection[0])['values'][0]}; self.destroy()
        elif active_tab_text == "Select from Ref DB":
            if not hasattr(self, 'ref_dog_tree') or not (selection := self.ref_dog_tree.selection()): messagebox.showwarning("Warning", "Please select a dog from the list.", parent=self); return
            selected_id = self.ref_dog_tree.item(selection[0])['values'][0]
            dog_info = next((d for d in self.ref_dogs if d['id'] == selected_id), None)
            self.result = {'action': 'existing_ref', 'dog_info': dog_info}; self.destroy()

    def save_unknown(self): self.result = {'action':'unknown'}; self.destroy()
    def cancel(self): self.result = None; self.destroy()

class BodyWithoutFaceDialog(BaseDialog):
    def __init__(self, parent, image, body_bbox, existing_persons=None, ref_persons=None, db_path=None):
        super().__init__(parent); self.parent = parent; self.result = None
        self.existing_persons = existing_persons or []; self.ref_persons = ref_persons or []; self.db_path = db_path
        self.title("Person without a Recognizable Face"); self.resizable(True, True); self.transient(parent); self.grab_set(); self.protocol("WM_DELETE_WINDOW", self.skip)
        main_frame = ttk.Frame(self); main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        body_frame = ttk.Frame(main_frame); body_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        x1, y1, x2, y2 = body_bbox; body_img = image[y1:y2, x1:x2]; body_img = cv2.cvtColor(body_img, cv2.COLOR_BGR2RGB); body_img = Image.fromarray(body_img)
        body_img.thumbnail((200, 300), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(body_img)
        body_label = ttk.Label(body_frame, image=photo); body_label.image = photo; body_label.pack()
        ttk.Label(body_frame, text="Person without a recognizable face", font=('Arial', 12, 'bold')).pack(pady=5)
        self.notebook = ttk.Notebook(main_frame); self.notebook.pack(fill=tk.BOTH, expand=True)
        input_tab = ttk.Frame(self.notebook); self.notebook.add(input_tab, text="Enter Data (Locally)")
        input_frame = ttk.Frame(input_tab, padding="20"); input_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(input_frame, text="Full Name:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5); self.full_name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.full_name_var, width=40).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text="Short Name:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5); self.short_name_var = tk.StringVar(); ttk.Entry(input_frame, textvariable=self.short_name_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Label(input_frame, text="Notes:").grid(row=2, column=0, sticky=tk.W+tk.N, padx=5, pady=5); text_frame = ttk.Frame(input_frame); text_frame.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        self.notes_text = tk.Text(text_frame, width=40, height=3, wrap=tk.WORD); self.notes_text.pack(fill=tk.BOTH, expand=True); input_frame.columnconfigure(1, weight=1)
        if self.existing_persons:
            existing_tab = ttk.Frame(self.notebook); self.notebook.add(existing_tab, text="Select from DB")
            tree_frame = ttk.Frame(existing_tab, padding="10"); tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', 'Full Name', 'Short Name'); self.person_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.person_tree.heading(col, text=col); self.person_tree.column(col, width=50 if col == 'ID' else 250)
            tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.person_tree.yview); self.person_tree.configure(yscrollcommand=tree_scroll.set)
            for person in self.existing_persons: self.person_tree.insert('', tk.END, values=(person['id'], person['full_name'], person['short_name']))
            self.person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        if self.ref_persons:
            ref_tab = ttk.Frame(self.notebook); self.notebook.add(ref_tab, text="Select from Ref DB")
            ref_tree_frame = ttk.Frame(ref_tab, padding="10"); ref_tree_frame.pack(fill=tk.BOTH, expand=True)
            columns = ('ID', 'Full Name', 'Short Name'); self.ref_person_tree = ttk.Treeview(ref_tree_frame, columns=columns, show='headings', height=8)
            for col in columns: self.ref_person_tree.heading(col, text=col); self.ref_person_tree.column(col, width=50 if col == 'ID' else 250)
            ref_tree_scroll = ttk.Scrollbar(ref_tree_frame, orient="vertical", command=self.ref_person_tree.yview)
            self.ref_person_tree.configure(yscrollcommand=ref_tree_scroll.set)
            for person in self.ref_persons: self.ref_person_tree.insert('', tk.END, values=(person['id'], person['full_name'], person['short_name']))
            self.ref_person_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); ref_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        button_frame = ttk.Frame(self); button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        ttk.Button(button_frame, text="Save Information", command=self.save_info).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Skip (Unknown)", command=self.skip).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side=tk.RIGHT, padx=5)
        self.center_window()
    def save_info(self):
        try: active_tab_text = self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError: active_tab_text = "Enter Data (Locally)"
        if active_tab_text == "Enter Data (Locally)":
            full_name = self.full_name_var.get().strip()
            if not full_name: messagebox.showwarning("Warning", "Please enter a full name or click 'Skip'.", parent=self); return
            self.result = {'action':'local_known', 'full_name':full_name, 'short_name':self.short_name_var.get().strip() or full_name.split()[0], 'notes':self.notes_text.get('1.0', tk.END).strip()}; self.destroy()
        elif active_tab_text == "Select from DB":
            if not hasattr(self, 'person_tree') or not (selection := self.person_tree.selection()): messagebox.showwarning("Warning", "Please select a person from the list.", parent=self); return
            self.result = {'action':'existing', 'person_id':self.person_tree.item(selection[0])['values'][0]}; self.destroy()
        elif active_tab_text == "Select from Ref DB":
            if not hasattr(self, 'ref_person_tree') or not (selection := self.ref_person_tree.selection()): messagebox.showwarning("Warning", "Please select a person from the list.", parent=self); return
            selected_id = self.ref_person_tree.item(selection[0])['values'][0]
            person_info = next((p for p in self.ref_persons if p['id'] == selected_id), None)
            self.result = {'action': 'existing_ref', 'person_info': person_info}; self.destroy()
    def skip(self): self.result = {'action':'unknown'}; self.destroy()
    def cancel(self): self.result = None; self.destroy()

class ConfirmPersonDialog(BaseDialog):
    def __init__(self, parent, image, face_location, person_info):
        super().__init__(parent); self.result = None; self.person_info = person_info
        self.title("Match Found in Reference DB"); self.resizable(False, False); self.transient(parent); self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.reject)
        main_frame = ttk.Frame(self, padding=20); main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text="A possible match was found!", font=('Arial', 14, 'bold')).pack(pady=(0, 10))
        top, right, bottom, left = face_location; face_img = image[top:bottom, left:right]; face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB); face_img = Image.fromarray(face_img)
        face_img.thumbnail((150, 150), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(face_img)
        face_label = ttk.Label(main_frame, image=photo); face_label.image = photo; face_label.pack(pady=10)
        info_frame = ttk.LabelFrame(main_frame, text="Information from Reference DB", padding=10); info_frame.pack(fill=tk.X, pady=10)
        ttk.Label(info_frame, text=f"Full Name: {person_info['full_name']}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"Short Name: {person_info['short_name']}").pack(anchor=tk.W)
        if person_info.get('notes'): ttk.Label(info_frame, text=f"Notes: {person_info['notes']}").pack(anchor=tk.W)
        ttk.Label(main_frame, text="Is this the same person?", font=('Arial', 11, 'bold')).pack(pady=10)
        button_frame = ttk.Frame(main_frame); button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="Yes, it's a match", command=self.confirm).pack(side=tk.LEFT, expand=True, padx=5)
        ttk.Button(button_frame, text="No, different person", command=self.reject).pack(side=tk.RIGHT, expand=True, padx=5)
        self.center_window()
    def confirm(self): self.result = {'confirmed': True, 'person_info': self.person_info}; self.destroy()
    def reject(self): self.result = {'confirmed': False}; self.destroy()

class FaceDetectionV2:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Face Detection v{VERSION} - Person and Dog Recognition")
        self.root.geometry("1400x900")
        self.style = ttk.Style(self.root)
        try: self.style.theme_use('clam')
        except tk.TclError: print("Theme 'clam' not found.")
        self.style.configure('TNotebook.Tab', font=('Arial', 12, 'bold'), padding=[10, 5]); self.style.configure('Status.TLabel', font=('Arial', 11, 'bold'), padding=5)
        self.style.configure('Idle.Status.TLabel', background='lightblue', foreground='black'); self.style.configure('Processing.Status.TLabel', background='lightyellow', foreground='black')
        self.style.configure('Complete.Status.TLabel', background='lightgreen', foreground='black'); self.style.configure('Error.Status.TLabel', background='lightcoral', foreground='black')
        
        self.update_queue = queue.Queue()
        self.source_dir = tk.StringVar(value=""); self.db_path_var = tk.StringVar(value=""); self.ref_db_path_var = tk.StringVar(value="")
        self.face_model = tk.StringVar(value="HOG (fast)")
        self.include_subdirs = tk.BooleanVar(value=False)
        self.face_threshold = tk.DoubleVar(value=0.6)
        
        self.yolo_person_conf = tk.DoubleVar(value=0.5)
        self.yolo_model = tk.StringVar(value="yolov8n.pt")
        
        self.processing = False
        self.processed_mode = tk.StringVar(value="skip")
        self.processed_decision_for_all = None
        self.db_path = None
        self.ref_db_path = None
        
        # --- Attributes for dog recognition models ---
        self.dog_det_model = None
        self.dog_cls_model = None
        self.dog_prep_det = None
        self.dog_prep_cls = None
        self.dog_labels_imagenet = None
        self.dog_device = "cuda" if torch.cuda.is_available() else "cpu"
        self.dog_detection_threshold = tk.DoubleVar(value=0.35)
        
        self.yolo = None
        self.loaded_yolo_model_name = None
        self.displayed_photo = None
        
        self.create_widgets()
        self.version_label = ttk.Label(self.root, text=f"v{VERSION}", font=('Arial', 9)); self.version_label.place(relx=0.99, y=5, anchor='ne')
        
        self.stdout_redirector = StdOutRedirector(self.update_queue)
        
        self.process_queue()
        self.update_status(f"Ready. Torch device: {self.dog_device.upper()}", 'idle')

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

    def create_widgets(self):
        main_notebook = ttk.Notebook(self.root); main_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        scan_frame = ttk.Frame(main_notebook); main_notebook.add(scan_frame, text="Scanning")
        self.create_scan_tab(scan_frame)
        people_frame = ttk.Frame(main_notebook); main_notebook.add(people_frame, text="People Database")
        self.create_people_tab(people_frame)
        dogs_frame = ttk.Frame(main_notebook); main_notebook.add(dogs_frame, text="Dogs Database")
        self.create_dogs_tab(dogs_frame)

    def create_scan_tab(self, parent):
        dir_frame = ttk.LabelFrame(parent, text="Scan Settings", padding="10"); dir_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=5); dir_frame.columnconfigure(1, weight=1)
        
        ttk.Label(dir_frame, text="Photo Directory:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(dir_frame, textvariable=self.source_dir, width=60).grid(row=0, column=1, padx=5, sticky=tk.EW)
        ttk.Button(dir_frame, text="Browse...", command=self.browse_source).grid(row=0, column=2)
        ttk.Checkbutton(dir_frame, text="Include subdirectories", variable=self.include_subdirs).grid(row=0, column=3, padx=20)
        
        ttk.Label(dir_frame, text="Active DB:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(dir_frame, textvariable=self.db_path_var, width=60, state='readonly').grid(row=1, column=1, padx=5, sticky=tk.EW)
        db_button_frame = ttk.Frame(dir_frame); db_button_frame.grid(row=1, column=2, columnspan=2, sticky=tk.W)
        ttk.Button(db_button_frame, text="Browse...", command=self.select_database_file).pack(side=tk.LEFT)
        ttk.Button(db_button_frame, text="Create New...", command=self.create_new_database).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(dir_frame, text="Reference DB (vectors):").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(dir_frame, textvariable=self.ref_db_path_var, width=60, state='readonly').grid(row=2, column=1, padx=5, sticky=tk.EW)
        ref_db_button_frame = ttk.Frame(dir_frame); ref_db_button_frame.grid(row=2, column=2, columnspan=2, sticky=tk.W)
        ttk.Button(ref_db_button_frame, text="Browse...", command=self.select_reference_database).pack(side=tk.LEFT)
        ttk.Button(ref_db_button_frame, text="Clear", command=self.clear_reference_database).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(dir_frame, text="Face Recognition Model:").grid(row=3, column=0, sticky=tk.W, pady=5)
        face_model_combo = ttk.Combobox(dir_frame, textvariable=self.face_model, values=['HOG (fast)', 'CNN (accurate)'], state='readonly', width=18)
        face_model_combo.grid(row=3, column=1, padx=5, sticky=tk.W)

        ttk.Label(dir_frame, text="Face Similarity Threshold:").grid(row=4, column=0, sticky=tk.W, pady=5)
        threshold_frame = ttk.Frame(dir_frame)
        threshold_frame.grid(row=4, column=1, columnspan=3, sticky=tk.W)
        self.threshold_label = ttk.Label(threshold_frame, text=f"{self.face_threshold.get():.2f}", font=('Arial', 10, 'bold'))
        def update_threshold_label(value): self.threshold_label.config(text=f"{float(value):.2f}")
        ttk.Scale(threshold_frame, from_=0.3, to=0.8, variable=self.face_threshold, orient=tk.HORIZONTAL, length=200, command=update_threshold_label).pack(side=tk.LEFT)
        self.threshold_label.pack(side=tk.LEFT, padx=10)
        ttk.Label(threshold_frame, text="(lower = stricter comparison)", font=('Arial', 9, 'italic')).pack(side=tk.LEFT)

        ttk.Label(dir_frame, text="YOLO Model (for people):").grid(row=5, column=0, sticky=tk.W, pady=5)
        model_frame = ttk.Frame(dir_frame)
        model_frame.grid(row=5, column=1, columnspan=3, sticky=tk.W)
        models = ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt"]
        model_combo = ttk.Combobox(model_frame, textvariable=self.yolo_model, values=models, state="readonly", width=15)
        model_combo.pack(side=tk.LEFT, padx=5)
        model_info_label = ttk.Label(model_frame, font=('Arial', 9), foreground='gray')
        model_info_label.pack(side=tk.LEFT, padx=10)
        def update_model_info(event=None):
            model_descriptions = {"yolov8n.pt": "Nano (fastest)", "yolov8s.pt": "Small (balanced)", "yolov8m.pt": "Medium (accurate)", "yolov8l.pt": "Large (very accurate)", "yolov8x.pt": "Extra (max accuracy)"}
            model_info_label.config(text=model_descriptions.get(self.yolo_model.get(), ""))
        model_combo.bind('<<ComboboxSelected>>', update_model_info)
        model_combo.set(self.yolo_model.get())
        update_model_info()

        ttk.Label(dir_frame, text="YOLO Confidence (People):").grid(row=6, column=0, sticky=tk.W, pady=5)
        person_conf_frame = ttk.Frame(dir_frame)
        person_conf_frame.grid(row=6, column=1, columnspan=3, sticky=tk.W)
        self.person_conf_label = ttk.Label(person_conf_frame, text=f"{self.yolo_person_conf.get():.2f}", font=('Arial', 10, 'bold'))
        def update_person_conf_label(value): self.person_conf_label.config(text=f"{float(value):.2f}")
        ttk.Scale(person_conf_frame, from_=0.1, to=0.9, variable=self.yolo_person_conf, orient=tk.HORIZONTAL, length=200, command=update_person_conf_label).pack(side=tk.LEFT)
        self.person_conf_label.pack(side=tk.LEFT, padx=10)
        ttk.Label(person_conf_frame, text="(higher = stricter detection)", font=('Arial', 9, 'italic')).pack(side=tk.LEFT)
        
        ttk.Label(dir_frame, text="Dog Detection Threshold (Torch):").grid(row=7, column=0, sticky=tk.W, pady=5)
        dog_conf_frame = ttk.Frame(dir_frame)
        dog_conf_frame.grid(row=7, column=1, columnspan=3, sticky=tk.W)
        self.dog_conf_label = ttk.Label(dog_conf_frame, text=f"{self.dog_detection_threshold.get():.2f}", font=('Arial', 10, 'bold'))
        def update_dog_conf_label(value): self.dog_conf_label.config(text=f"{float(value):.2f}")
        ttk.Scale(dog_conf_frame, from_=0.1, to=0.9, variable=self.dog_detection_threshold, orient=tk.HORIZONTAL, length=200, command=update_dog_conf_label).pack(side=tk.LEFT)
        self.dog_conf_label.pack(side=tk.LEFT, padx=10)
        ttk.Label(dog_conf_frame, text="(probability that object is a dog)", font=('Arial', 9, 'italic')).pack(side=tk.LEFT)

        processed_frame = ttk.LabelFrame(dir_frame, text="Re-processing Behavior", padding="10")
        processed_frame.grid(row=8, column=0, columnspan=4, sticky="ew", pady=10, padx=5)
        ttk.Radiobutton(processed_frame, text="Do not process (skip)", variable=self.processed_mode, value="skip").pack(anchor=tk.W)
        ttk.Radiobutton(processed_frame, text="Process again", variable=self.processed_mode, value="process").pack(anchor=tk.W)
        ttk.Radiobutton(processed_frame, text="Ask for each image", variable=self.processed_mode, value="ask").pack(anchor=tk.W)
        
        control_frame = ttk.Frame(parent, padding="10"); control_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5)
        self.start_btn = ttk.Button(control_frame, text="🚀 Start Scan", command=self.start_processing, state=tk.DISABLED); self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(control_frame, text="🛑 Stop", command=self.stop_processing, state=tk.DISABLED); self.stop_btn.pack(side=tk.LEFT, padx=5)
        self.exit_btn = ttk.Button(control_frame, text="Exit", command=self.root.destroy); self.exit_btn.pack(side=tk.RIGHT, padx=5)
        self.status_label = ttk.Label(control_frame, text="Ready. Please select or create a DB.", style="Idle.Status.TLabel"); self.status_label.pack(side=tk.LEFT, padx=20, fill=tk.X, expand=True)

        image_frame = ttk.LabelFrame(parent, text="Current Image", padding="10"); image_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        self.image_label = ttk.Label(image_frame); self.image_label.pack(expand=True, fill=tk.BOTH)
        log_frame = ttk.LabelFrame(parent, text="Processing Log", padding="10"); log_frame.grid(row=2, column=1, sticky="nsew", padx=10, pady=10)
        self.log_text = scrolledtext.ScrolledText(log_frame, width=50, height=30, wrap=tk.WORD); self.log_text.pack(fill=tk.BOTH, expand=True)
        self.copy_btn = ttk.Button(log_frame, text="📋", width=3, command=self.copy_log_to_clipboard)
        self.copy_btn.place(relx=1.0, rely=0, x=-5, y=2, anchor="ne")
        parent.grid_rowconfigure(2, weight=1); parent.grid_columnconfigure(0, weight=2); parent.grid_columnconfigure(1, weight=1)

    def copy_log_to_clipboard(self):
        content = self.log_text.get('1.0', tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.log("Log copied to clipboard.")

    def create_people_tab(self, parent):
        toolbar = ttk.Frame(parent); toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        self.btn_refresh_people = ttk.Button(toolbar, text="Refresh", command=self.refresh_people_list, state=tk.DISABLED); self.btn_refresh_people.pack(side=tk.LEFT, padx=5)
        self.btn_edit_person = ttk.Button(toolbar, text="Edit", command=self.edit_person, state=tk.DISABLED); self.btn_edit_person.pack(side=tk.LEFT, padx=5)
        self.btn_delete_person = ttk.Button(toolbar, text="Delete", command=self.delete_person, state=tk.DISABLED); self.btn_delete_person.pack(side=tk.LEFT, padx=5)
        columns = ('ID', 'Status', 'Full Name', 'Short Name', 'Photos', 'Notes'); self.people_tree = ttk.Treeview(parent, columns=columns, show='headings')
        self.people_tree.heading('ID', text='ID'); self.people_tree.column('ID', width=50, anchor='center'); self.people_tree.heading('Status', text='Status'); self.people_tree.column('Status', width=100); self.people_tree.heading('Full Name', text='Full Name'); self.people_tree.column('Full Name', width=200); self.people_tree.heading('Short Name', text='Short Name'); self.people_tree.column('Short Name', width=150); self.people_tree.heading('Photos', text='Photos'); self.people_tree.column('Photos', width=80, anchor='center'); self.people_tree.heading('Notes', text='Notes'); self.people_tree.column('Notes', width=300)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.people_tree.yview); self.people_tree.configure(yscrollcommand=scrollbar.set)
        self.people_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5); scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def create_dogs_tab(self, parent):
        toolbar = ttk.Frame(parent); toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        self.btn_refresh_dogs = ttk.Button(toolbar, text="Refresh", command=self.refresh_dogs_list, state=tk.DISABLED); self.btn_refresh_dogs.pack(side=tk.LEFT, padx=5)
        self.btn_edit_dog = ttk.Button(toolbar, text="Edit", command=self.edit_dog, state=tk.DISABLED); self.btn_edit_dog.pack(side=tk.LEFT, padx=5)
        self.btn_delete_dog = ttk.Button(toolbar, text="Delete", command=self.delete_dog, state=tk.DISABLED); self.btn_delete_dog.pack(side=tk.LEFT, padx=5)
        columns = ('ID', 'Status', 'Name', 'Breed', 'Owner', 'Photos', 'Notes'); self.dogs_tree = ttk.Treeview(parent, columns=columns, show='headings')
        for col, w in [('ID',50), ('Status',100), ('Name',150), ('Breed',150), ('Owner',150), ('Photos',80), ('Notes',200)]: self.dogs_tree.heading(col, text=col); self.dogs_tree.column(col, width=w)
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

                add_column_if_not_exists('images', 'ai_short_description', 'TEXT')
                add_column_if_not_exists('images', 'ai_long_description', 'TEXT')
                add_column_if_not_exists('images', 'ai_processed_date', 'TEXT')
                add_column_if_not_exists('images', 'ai_llm_used', 'TEXT')
                add_column_if_not_exists('images', 'ai_language', 'TEXT')
                add_column_if_not_exists('dog_detections', 'breed_source', 'TEXT')
                
                cursor.execute('PRAGMA foreign_keys = ON;')
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Could not create or update the database: {e}")
            return False

    def validate_database_structure(self, db_path):
        REQUIRED_TABLES = {'persons':['id','full_name'], 'dogs':['id','name'], 'images':['id','filepath'], 'face_encodings':['id','person_id'], 'person_detections':['id','image_id'], 'dog_detections':['id','image_id']}
        try:
            with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'"); tables = {row[0] for row in cursor.fetchall()}
                if not set(REQUIRED_TABLES.keys()).issubset(tables):
                    return False
            return True
        except Exception as e: 
            self.log(f"Error reading database: {e}")
            return False

    def select_database_file(self):
        if filepath := filedialog.askopenfilename(title="Select Active Database", filetypes=[("SQLite DB", "*.db")]):
            if self.init_database(filepath):
                if self.validate_database_structure(filepath):
                    self.db_path = filepath
                    self.db_path_var.set(filepath)
                    self.log(f"Active DB loaded and verified: {filepath}")
                    self.set_db_dependent_widgets_state(tk.NORMAL)
                    self.refresh_people_list()
                    self.refresh_dogs_list()
                    self.update_status("DB loaded. Ready to scan.", 'complete')
                else:
                    messagebox.showerror("Error", "The database structure is incorrect, even after an update attempt.")
                    self.db_path = None; self.db_path_var.set(""); self.set_db_dependent_widgets_state(tk.DISABLED)
            else:
                self.db_path = None; self.db_path_var.set(""); self.set_db_dependent_widgets_state(tk.DISABLED)

    def create_new_database(self):
        if filepath := filedialog.asksaveasfilename(title="Create New Database", defaultextension=".db", filetypes=[("SQLite DB", "*.db")]):
            if self.init_database(filepath):
                self.db_path = filepath
                self.db_path_var.set(filepath)
                self.set_db_dependent_widgets_state(tk.NORMAL)
                self.refresh_people_list()
                self.refresh_dogs_list()
                self.log(f"New DB created and loaded: {filepath}")
                self.update_status("New DB created. Ready to scan.", 'complete')
            else:
                self.db_path = None; self.db_path_var.set(""); self.set_db_dependent_widgets_state(tk.DISABLED)

    def select_reference_database(self):
        if filepath := filedialog.askopenfilename(title="Select Reference Database", filetypes=[("SQLite DB", "*.db")]):
            if self.validate_database_structure(filepath): self.ref_db_path = filepath; self.ref_db_path_var.set(filepath); self.log(f"Reference DB loaded: {filepath}")
            else: self.log("The selected reference DB file has an invalid structure.")

    def clear_reference_database(self): self.ref_db_path = None; self.ref_db_path_var.set(""); self.log("Reference DB cleared.")
    
    def browse_source(self):
        if directory := filedialog.askdirectory(title="Select Photo Directory"): self.source_dir.set(directory)
    
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
            if annotated_image is not None:
                image = Image.fromarray(cv2.cvtColor(annotated_image, cv2.COLOR_BGR2RGB))
            else:
                image = orient_image(Image.open(image_path))
            self.image_label.update_idletasks()
            w, h = self.image_label.winfo_width(), self.image_label.winfo_height()
            max_w, max_h = (w - 20) if w > 20 else 700, (h - 20) if h > 20 else 700
            image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            self.displayed_photo = ImageTk.PhotoImage(image)
            self.image_label.config(image=self.displayed_photo)
        except Exception as e:
            self.log(f"Display error: {e}")
            self.image_label.config(image=None); self.image_label.config(text=f"Failed to display\n{os.path.basename(image_path)}")

    def init_dog_models(self):
        """Initializes Torchvision models for dogs, displaying a progress bar."""
        if self.dog_det_model and self.dog_cls_model:
            return True
        self.log(f"Loading dog recognition models to device: {self.dog_device.upper()}...")
        
        original_stdout = sys.stdout
        sys.stdout = self.stdout_redirector
        try:
            self.update_status("Loading dog recognition models...", 'processing')
            # Detector
            det_w = tv_det.FasterRCNN_ResNet50_FPN_Weights.DEFAULT
            self.dog_det_model = tv_det.fasterrcnn_resnet50_fpn(weights=det_w, box_score_thresh=0.0, progress=True).eval().to(self.dog_device)
            self.dog_prep_det = det_w.transforms()
            
            # Classifier
            cls_w = tv_cls.DenseNet121_Weights.DEFAULT
            self.dog_cls_model = tv_cls.densenet121(weights=cls_w, progress=True).eval().to(self.dog_device)
            self.dog_prep_cls = cls_w.transforms()
            self.dog_labels_imagenet = cls_w.meta["categories"]
            
            self.log("Dog recognition models loaded successfully.")
            return True
        except Exception as e:
            self.log(f"Error loading Torchvision models: {e}")
            return False
        finally:
            sys.stdout = original_stdout # Restore stdout
            
    def start_processing(self):
        if not self.db_path:
            messagebox.showerror("Error", "Please select or create a database file.")
            return
        if not self.source_dir.get() or not os.path.exists(self.source_dir.get()):
            messagebox.showerror("Error", "Please specify a directory with photos.")
            return
        if not self.processing:
            self.processing = True
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.update_status("Initializing...", 'processing')
            try:
                # Initialize dog models
                if not self.init_dog_models():
                    raise Exception("Failed to load dog recognition models.")

                # Initialize YOLO
                if self.yolo is None or self.loaded_yolo_model_name != self.yolo_model.get():
                    model_file = Path(self.yolo_model.get())
                    if not model_file.exists():
                        self.log(f"YOLO model '{model_file}' not found. Download will begin...")
                        self.log("This may take a moment. The application has not frozen.")
                        self.update_status(f"Downloading YOLO: {model_file}...", 'processing')

                    self.log(f"Loading YOLO model: {self.yolo_model.get()}...")
                    self.yolo = YOLO(self.yolo_model.get())
                    self.loaded_yolo_model_name = self.yolo_model.get()
                    self.log(f"YOLO model {self.yolo_model.get()} loaded.")
            except Exception as e:
                self.log(f"Model initialization error: {e}")
                self.processing = False
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
                self.update_status("Error!", 'error')
                return
            
            threading.Thread(target=self.process_images, daemon=True).start()

    def stop_processing(self): self.processing = False; self.log("Stopping process..."); self.update_status("Stopping...", 'idle'); self.start_btn.config(state=tk.NORMAL); self.stop_btn.config(state=tk.DISABLED)

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

    def edit_person(self): messagebox.showinfo("Not Implemented", "The edit function is under development.")

    def delete_person(self):
        if not (sel := self.people_tree.selection()): messagebox.showwarning("Warning", "Please select a person to delete."); return
        if messagebox.askyesno("Confirm Deletion", "Are you sure you want to delete this person and all related data? This action cannot be undone."):
            person_id = self.people_tree.item(sel[0])['values'][0]
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor(); cursor.execute('PRAGMA foreign_keys = ON;'); cursor.execute('DELETE FROM persons WHERE id = ?', (person_id,));
                self.refresh_people_list(); messagebox.showinfo("Success", "Person deleted successfully.")
            except Exception as e: messagebox.showerror("Error", f"Deletion failed: {e}")

    def edit_dog(self): messagebox.showinfo("Not Implemented", "The edit function is under development.")
    
    def delete_dog(self):
        if not (sel := self.dogs_tree.selection()): messagebox.showwarning("Warning", "Please select a dog to delete."); return
        if messagebox.askyesno("Confirm Deletion", "Are you sure you want to delete this dog and all related data? This action cannot be undone."):
            dog_id = self.dogs_tree.item(sel[0])['values'][0]
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor(); cursor.execute('PRAGMA foreign_keys = ON;'); cursor.execute('DELETE FROM dogs WHERE id = ?', (dog_id,));
                self.refresh_dogs_list(); messagebox.showinfo("Success", "Dog deleted successfully.")
            except Exception as e: messagebox.showerror("Error", f"Deletion failed: {e}")

    def get_existing_persons(self, db_path=None):
        target_db = db_path or self.db_path
        if not target_db: return []
        try:
            with sqlite3.connect(f'file:{target_db}?mode=ro', uri=True) as conn:
                conn.row_factory = sqlite3.Row; cursor = conn.cursor()
                cursor.execute('SELECT id, full_name, short_name, notes FROM persons WHERE is_known = 1 ORDER BY full_name')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e: self.log(f"Error reading list of people from {os.path.basename(target_db)}: {e}"); return []

    def get_existing_dogs(self, db_path=None):
        target_db = db_path or self.db_path
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
        dialog = PersonDialog(self.root, image, face_location, self.get_existing_persons(), ref_persons, self.db_path)
        self.root.wait_window(dialog); callback(dialog.result)

    def show_dog_dialog_main(self, data):
        image, dog_bbox, callback, breed = data
        ref_dogs = self.get_existing_dogs(self.ref_db_path) if self.ref_db_path else []
        dialog = DogDialog(self.root, image, dog_bbox, self.get_existing_dogs(), ref_dogs, self.db_path, breed=breed)
        self.root.wait_window(dialog); callback(dialog.result)

    def show_body_dialog_main(self, data):
        image, body_bbox, callback = data
        existing_persons = self.get_existing_persons()
        ref_persons = self.get_existing_persons(db_path=self.ref_db_path) if self.ref_db_path else []
        dialog = BodyWithoutFaceDialog(self.root, image, body_bbox, existing_persons, ref_persons, self.db_path)
        self.root.wait_window(dialog)
        callback(dialog.result)
    
    def show_confirm_person_dialog_main(self, data):
        image, face_location, person_info, callback = data
        dialog = ConfirmPersonDialog(self.root, image, face_location, person_info)
        self.root.wait_window(dialog)
        callback(dialog.result)

    def show_processed_dialog_main(self, data):
        image_path, callback = data
        dialog = ProcessedImageDialog(self.root, image_path)
        self.root.wait_window(dialog)
        callback(dialog.result, dialog.apply_to_all)

    def create_or_update_person(self, result, conn):
        cursor = conn.cursor(); now = datetime.now().isoformat(); person_id = None
        if result['action'] == 'new_known':
            cursor.execute('INSERT INTO persons (is_known, full_name, short_name, notes, created_date, updated_date) VALUES (1, ?, ?, ?, ?, ?)', (result['full_name'], result['short_name'], result['notes'], now, now)); person_id = cursor.lastrowid; self.log(f"  Created new person: {result['full_name']}")
        elif result['action'] == 'unknown':
            cursor.execute('INSERT INTO persons (is_known, created_date, updated_date) VALUES (0, ?, ?)', (now, now)); person_id = cursor.lastrowid; self.log(f"  Added an unknown person (ID: {person_id})")
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
            rows = cursor.fetchall()
            if not rows: return None

            known_face_encodings, known_face_metadata = [], []
            for row in rows:
                try: 
                    known_face_encodings.append(np.array(json.loads(row['face_encoding'])))
                    known_face_metadata.append(dict(row))
                except (json.JSONDecodeError, TypeError): continue
            
            if not known_face_encodings: return None
            
            distances = face_recognition.face_distance(known_face_encodings, face_encoding_to_check)
            if len(distances) == 0: return None

            best_match_index = np.argmin(distances)
            if distances[best_match_index] < self.face_threshold.get():
                return known_face_metadata[best_match_index]

        except Exception as e: self.log(f"Identification error in {os.path.basename(db_path)}: {e}")
        finally:
            if not main_conn or (main_conn and db_path != self.db_path): conn.close()
        return None

    def _identify_person(self, person_obj, image, conn, already_assigned_ids):
        if person_obj.get('has_face'):
            identified_person_id = None
            
            match = self.identify_person(person_obj['face_encoding'], self.db_path, main_conn=conn)
            if match and match['id'] not in already_assigned_ids:
                identified_person_id = match['id']
                self.log(f"  Recognized (main DB): {match['short_name']}")
            
            elif self.ref_db_path:
                ref_match = self.identify_person(person_obj['face_encoding'], self.ref_db_path)
                if ref_match:
                    dialog_event = threading.Event(); dialog_result = {}; cb = lambda r: (dialog_result.update({'result': r}), dialog_event.set())
                    self.update_queue.put(('show_confirm_person_dialog', (image, person_obj['face_location'], ref_match, cb)))
                    dialog_event.wait()
                    if dialog_result.get('result', {}).get('confirmed'):
                        person_info_from_ref = dialog_result['result']['person_info']
                        potential_id = self.get_or_create_person_by_name(person_info_from_ref, conn)
                        if potential_id not in already_assigned_ids:
                            identified_person_id = potential_id
                        else:
                            self.log(f"  Skipped assignment of '{person_info_from_ref['short_name']}' (ID={potential_id}) as it's already assigned in this photo.")
            
            if identified_person_id:
                person_obj['person_id'] = identified_person_id
            else:
                dialog_event = threading.Event(); dialog_result = {}; cb = lambda r: (dialog_result.update({'result': r}), dialog_event.set())
                self.update_queue.put(('show_person_dialog', (image, person_obj['face_location'], person_obj['face_encoding'], cb)))
                dialog_event.wait()
                person_result = dialog_result.get('result')
                if person_result:
                    person_id = self.create_or_update_person(person_result, conn)
                    if person_id:
                        person_obj['person_id'] = person_id
        else: # Person without face
            dialog_event = threading.Event(); dialog_result = {}; cb = lambda r: (dialog_result.update({'result': r}), dialog_event.set())
            self.update_queue.put(('show_body_dialog', (image, person_obj['bbox'], cb)))
            dialog_event.wait()
            person_result = dialog_result.get('result')
            if person_result:
                if person_result['action'] == 'existing':
                    if person_result['person_id'] not in already_assigned_ids:
                        person_obj['person_id'] = person_result['person_id']
                    else:
                        self.log(f"  Skipped assignment of ID={person_result['person_id']} as it's already assigned in this photo.")
                elif person_result['action'] == 'existing_ref':
                     person_id = self.get_or_create_person_by_name(person_result['person_info'], conn)
                     if person_id not in already_assigned_ids:
                        person_obj['person_id'] = person_id
                     else:
                        self.log(f"  Skipped assignment of ID={person_id} as it's already assigned in this photo.")
                elif person_result['action'] == 'local_known':
                    person_obj.update({'is_locally_identified': True, 'local_full_name': person_result['full_name'], 'local_short_name': person_result['short_name'], 'local_notes': person_result['notes']})
                elif person_result['action'] == 'unknown':
                    person_obj['person_id'] = self.create_or_update_person(person_result, conn)
        return person_obj

    def detect_dogs_torchvision(self, pil_image):
        """Detects dogs and their breeds using Torchvision models."""
        self.log("  Running dog detection (Torchvision)...")
        DOG_COCO_CLASS = 18 # "dog" class in the COCO dataset
        threshold = self.dog_detection_threshold.get()
        
        with torch.no_grad():
            out = self.dog_det_model(self.dog_prep_det(pil_image).unsqueeze(0).to(self.dog_device))[0]

        detected_dogs = []
        for i, (box, label, score) in enumerate(zip(out["boxes"], out["labels"], out["scores"])):
            if label.item() == DOG_COCO_CLASS and score.item() >= threshold:
                crop = pil_image.crop((box[0].item(), box[1].item(), box[2].item(), box[3].item()))
                with torch.no_grad():
                    probs = torch.softmax(self.dog_cls_model(self.dog_prep_cls(crop).unsqueeze(0).to(self.dog_device)), 1)[0]
                idx = int(probs.argmax())
                breed_p = probs[idx].item()
                breed = self.dog_labels_imagenet[idx]
                detected_dogs.append({
                    'dog_index': i,
                    'bbox': [int(c) for c in box.cpu().numpy()],
                    'confidence': score.item(),
                    'breed': breed.split(',')[0].capitalize(),
                    'breed_confidence': breed_p
                })
        self.log(f"  Torchvision detected: {len(detected_dogs)} dog(s).")
        return detected_dogs

    def analyze_image(self, image_path, image_id, conn):
        try:
            pil_image = Image.open(image_path).convert("RGB")
            oriented_pil_image = orient_image(pil_image)
            image = cv2.cvtColor(np.array(oriented_pil_image), cv2.COLOR_RGB2BGR)
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # --- Step 1: Detect People (YOLO) and Faces (face_recognition) ---
            self.log("  Running person detection (YOLO) and face recognition...")
            results = self.yolo(image, conf=self.yolo_person_conf.get(), classes=[0]) # People only
            person_detections = []
            if results and results[0].boxes:
                for i, box in enumerate(results[0].boxes):
                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                    confidence = float(box.conf[0])
                    person_detections.append({'person_index': i, 'bbox': [x1, y1, x2, y2], 'confidence': confidence, 'has_face': False})
            self.log(f"  YOLO detected: {len(person_detections)} person(s).")

            model_name = 'cnn' if 'CNN' in self.face_model.get() else 'hog'
            self.log(f"  Using face recognition model: {model_name.upper()}")
            face_locations = face_recognition.face_locations(rgb_image, model=model_name)
            face_encodings = face_recognition.face_encodings(rgb_image, face_locations)
            self.log(f"  Found {len(face_locations)} face(s).")

            # Match faces to bodies
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
                            intersection = (x2_i - x1_i) * (y2_i - y1_i)
                            face_area = (right - left) * (bottom - top)
                            if face_area > 0 and (overlap := intersection / face_area) > best_overlap:
                                best_overlap, best_person_idx = overlap, person_idx
                if best_person_idx != -1 and best_overlap > 0.5:
                    person_detections[best_person_idx].update({'has_face': True, 'face_encoding': face_encoding, 'face_location': face_location})
                else:
                    unmatched_faces.append({'face_location': face_location, 'face_encoding': face_encoding})
            
            all_people_to_process = []
            all_people_to_process.extend(person_detections)
            for f in unmatched_faces:
                f['bbox'] = [f['face_location'][3], f['face_location'][0], f['face_location'][1], f['face_location'][2]]
                f['has_face'] = True; f['person_index'] = -1
                all_people_to_process.append(f)
            
            # **FIXED SORTING LOGIC HERE**
            def get_sort_key(p_obj):
                """Defines the sorting priority: faces first, then by area (face area if available)."""
                has_face = p_obj.get('has_face', False)
                if has_face:
                    # For objects with a face, sort by the face's area
                    face_loc = p_obj['face_location']  # (top, right, bottom, left)
                    area = (face_loc[2] - face_loc[0]) * (face_loc[1] - face_loc[3])
                    return (1, area)  # Priority 1 (has face), sorted by face area
                else:
                    # For objects without a face, sort by the body's area
                    body_bbox = p_obj['bbox']  # (x1, y1, x2, y2)
                    area = (body_bbox[2] - body_bbox[0]) * (body_bbox[3] - body_bbox[1])
                    return (0, area)  # Priority 0 (no face), sorted by body area

            all_people_to_process.sort(key=get_sort_key, reverse=True)
            self.log("  Person objects sorted for processing (largest faces first).")

            final_person_detections = []
            assigned_ids_this_photo = set()
            for person_obj in all_people_to_process:
                if not self.processing: break
                processed_person = self._identify_person(person_obj, image, conn, assigned_ids_this_photo)
                if processed_person.get('person_id'):
                    assigned_ids_this_photo.add(processed_person['person_id'])
                final_person_detections.append(processed_person)

            # --- Step 2: Detect Dogs (Torchvision) ---
            dog_detections = self.detect_dogs_torchvision(oriented_pil_image)

            for dog in dog_detections:
                if not self.processing: break
                dialog_event = threading.Event(); dialog_result = {}; 
                cb = lambda r: (dialog_result.update({'result': r}), dialog_event.set())
                self.update_queue.put(('show_dog_dialog', (image, dog['bbox'], cb, dog['breed']))); 
                dialog_event.wait()

                if res := dialog_result.get('result'):
                    if res['action'] == 'existing_ref': 
                        dog['dog_id'] = self.get_or_create_dog_by_name(res['dog_info'], conn)
                    else: 
                        if res['action'] == 'new_known' and not res.get('breed'):
                            res['breed'] = dog['breed']
                        dog['dog_id'] = self.create_or_update_dog(res, conn)
            
            # --- Step 3: Annotate image and return results ---
            annotated_image = image.copy()
            for person in final_person_detections:
                p_id = person.get('person_id'); name = person.get('local_short_name') or self.get_name_from_db(p_id, conn, 'person')
                x1, y1, x2, y2 = person['bbox']; cv2.rectangle(annotated_image, (x1, y1), (x2, y2), (255, 0, 0), 2); cv2.putText(annotated_image, name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)
                if person.get('has_face'): top, right, bottom, left = person['face_location']; cv2.rectangle(annotated_image, (left, top), (right, bottom), (0, 255, 0), 2)
            
            for dog in dog_detections:
                d_id = dog.get('dog_id'); name = self.get_name_from_db(d_id, conn, 'dog');
                x1, y1, x2, y2 = dog['bbox']
                breed_text = dog['breed']
                label = f"{name} ({breed_text})" if name != "Unknown" else breed_text
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
                        self.log(f"  Adding new face vector for Person ID: {person_id}")
                        enc_str = json.dumps(person['face_encoding'].tolist())
                        loc_str = json.dumps(person['face_location'])
                        cursor.execute('INSERT INTO face_encodings (person_id, image_id, face_encoding, face_location) VALUES (?, ?, ?, ?)',
                                       (person_id, image_id, enc_str, loc_str))
                        face_encoding_id = cursor.lastrowid
                cursor.execute("INSERT INTO person_detections (image_id, person_id, person_index, bbox, confidence, has_face, face_encoding_id, is_locally_identified, local_full_name, local_short_name, local_notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (image_id, person_id, person.get('person_index', -1), json.dumps(person['bbox']), person.get('confidence', 1.0), person.get('has_face', False), face_encoding_id, person.get('is_locally_identified', False), person.get('local_full_name'), person.get('local_short_name'), person.get('local_notes')))
            
            for dog in dog_detections:
                cursor.execute('INSERT INTO dog_detections (image_id, dog_id, dog_index, bbox, confidence, breed_source) VALUES (?, ?, ?, ?, ?, ?)', 
                               (image_id, dog.get('dog_id'), dog.get('dog_index'), json.dumps(dog['bbox']), dog['confidence'], dog['breed']))
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
                self.update_status(f"Processing {i+1}/{len(image_files)}: {os.path.basename(image_path)}", 'processing'); self.log(f"\nProcessing: {os.path.basename(image_path)}"); self.update_image(image_path)
                
                if self.is_image_processed(image_path):
                    decision = self.processed_decision_for_all
                    if not decision:
                        process_mode = self.processed_mode.get()
                        if process_mode == 'ask':
                            dialog_event = threading.Event(); dialog_res = {}; cb = lambda res, apply_all: (dialog_res.update({'res':res, 'apply_all':apply_all}), dialog_event.set())
                            self.update_queue.put(('show_processed_dialog', (image_path, cb))); dialog_event.wait()
                            decision = dialog_res.get('res')
                            if dialog_res.get('apply_all'): self.processed_decision_for_all = decision
                        else:
                            decision = process_mode
                    
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
            self.log("\nProcessing complete!"); self.update_status("Processing complete", 'complete'); self.update_queue.put(('refresh_people', None)); self.update_queue.put(('refresh_dogs', None))
        except Exception as e: self.log(f"Critical error in processing loop: {e}\n{traceback.format_exc()}"); self.update_status("Error!", 'error')
        finally: self.processing = False; self.update_queue.put(('enable_buttons', None))

def main():
    root = tk.Tk()
    app = FaceDetectionV2(root)
    root.mainloop()

if __name__ == "__main__":
    # This is recommended for PyTorch multiprocessing/multithreading on Windows
    # https://pytorch.org/docs/stable/notes/windows.html#multiprocessing-error-without-if-clause-protection
    main()