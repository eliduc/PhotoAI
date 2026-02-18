# -*- coding: utf-8 -*-
"""
Shared utilities for the PhotoSuite application.
Contains common functions used across multiple modules.
"""

import os
import shutil
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from PIL import Image

# --- EXIF Orientation ---

def correct_image_orientation(image: Image.Image) -> Image.Image:
    """Applies rotation/flip to a PIL image based on its EXIF orientation data.
    Handles all 8 EXIF orientation values."""
    try:
        exif = image.getexif()
        orientation_tag = 0x0112  # 274

        if orientation_tag in exif:
            orientation = exif[orientation_tag]
            if orientation == 2:
                image = image.transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 3:
                image = image.rotate(180, expand=True)
            elif orientation == 4:
                image = image.transpose(Image.FLIP_TOP_BOTTOM)
            elif orientation == 5:
                image = image.transpose(Image.FLIP_LEFT_RIGHT).rotate(270, expand=True)
            elif orientation == 6:
                image = image.rotate(270, expand=True)
            elif orientation == 7:
                image = image.transpose(Image.FLIP_LEFT_RIGHT).rotate(90, expand=True)
            elif orientation == 8:
                image = image.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError):
        pass
    return image

# Alias for backward compatibility
orient_image = correct_image_orientation


# --- Image Extensions ---

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}

# Try to add HEIF/HEIC support
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    IMAGE_EXTENSIONS |= {'.heif', '.heic'}
except ImportError:
    pass


# --- Database Backup ---

def backup_database(db_path: str) -> str:
    """Creates a timestamped backup of the database file.
    Returns the backup file path."""
    if not db_path or not os.path.exists(db_path):
        return ""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base, ext = os.path.splitext(db_path)
    backup_path = f"{base}_backup_{timestamp}{ext}"
    shutil.copy2(db_path, backup_path)
    return backup_path


# --- File Creation Date ---

def get_file_creation_date(file_path: str) -> str:
    """Returns the file creation date as ISO string.
    Uses st_birthtime if available, falls back to st_mtime."""
    stat = os.stat(file_path)
    birth_ts = getattr(stat, 'st_birthtime', None) or stat.st_mtime
    return datetime.fromtimestamp(birth_ts).isoformat()


# --- File-based Logging ---

def setup_file_logger(name: str, log_dir: str = None) -> logging.Logger:
    """Creates a file logger that writes to a timestamped log file.
    Returns the logger instance."""
    if log_dir is None:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"{name}_{timestamp}.log")

    logger = logging.getLogger(f"photosuite.{name}")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        handler = logging.FileHandler(log_file, encoding='utf-8')
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
