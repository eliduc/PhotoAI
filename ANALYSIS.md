# PhotoAI Repository Analysis

## BUGS & ERRORS (Ordered by Criticality)

### CRITICAL -- Data Loss / Incorrect Behavior

**1. `AIPhotoDescriptionGenerator.py:345` -- LLM dropdown never gets populated**

`init_llm_clients()` is called at line 214 *before* `create_widgets()`. At line 345, it
checks `if hasattr(self, 'llm_combo')` -- which is `False` because the widget hasn't been
created yet. The combo box values are never set, so users can only see the hardcoded default
"OpenAI" and cannot switch to Anthropic or Gemini even if their API keys are valid.

**2. `FaceDetection.py:1267` -- Face model selection breaks on language change**

The face recognition model is selected by comparing localized strings:
```python
model_name = 'cnn' if self.lang.get('face_model_accurate') in self.face_model.get() else 'hog'
```
When the user selects "CNN (accurate)" in English and then switches to Russian,
`self.face_model.get()` still holds `"CNN (accurate)"` but
`self.lang.get('face_model_accurate')` becomes `"CNN (точная)"`. The substring check fails,
and the system silently falls back to HOG regardless of user selection. This causes
significantly worse recognition accuracy without any indication to the user.

**3. `FaceDetection.py:1147` -- Selecting a person from Reference DB via PersonDialog does nothing**

In `create_or_update_person`, the `'existing_ref'` action is handled with a bare `pass` and
returns `None`. When a user selects a person from the Reference DB tab inside the face
identification dialog (not the confirm dialog), the person is never actually imported or
linked. The detection remains unidentified. The ref DB import only works through the
separate `_identify_person` confirm dialog path (line 1213-1219), not through the manual
person dialog.

**4. `AIPhotoDescriptionGenerator.py:381,398` -- `locals().get('result')` leaks state across loop iterations**

```python
if not short_d or (locals().get('result') and result['status'] == 'reprocess'):
```
The variable `result` from a *previous* loop iteration can persist in the local scope and
affect the current iteration's control flow. If the previous image's dialog returned
`{'status': 'reprocess'}`, the current image may incorrectly enter the reprocess branch
even though the user never interacted with it.

**5. `FaceDB_Cleaner.py:1005-1015` -- Physical file deletion happens before DB commit**

In `process_photo_duplicates`, files are physically deleted from disk (line 1011), but the
DB `commit()` only happens later in `cleaning_thread` (line 877). If the commit fails or an
error occurs in a subsequent operation, the transaction is rolled back but the files are
already gone -- permanent data loss with inconsistent DB state.

**6. `NA-to-ID.py:589` -- Post-apply re-analysis never runs**

After `apply_changes` succeeds, it calls `self.start_action(self.analyze_database)` (line
589). But `apply_changes` itself was launched via `start_action`, which sets
`self.is_running = True`. Since `start_action` checks `if self.is_running: return` at the
top, the re-analysis is silently skipped. The UI shows stale analysis data.

---

### HIGH -- Functional Issues / Thread Safety

**7. `NA-to-ID.py:425-427` -- Tkinter widgets modified from worker thread**

`end_action()` directly calls `self.analyze_btn.config(state=tk.NORMAL)` from the
background thread. Tkinter is not thread-safe; GUI modifications from non-main threads can
cause intermittent crashes, display corruption, or deadlocks.

**8. `PhotoSuiteLauncher.py:144` -- Relative icon path breaks when CWD differs**

`icon_dir = Path('icons')` uses a relative path. If the launcher is started from any
directory other than the project root (e.g., via a desktop shortcut or file manager), all
icons fail to load and the launcher shows an error. Other modules correctly use
`Path(__file__).parent` for relative paths.

**9. `PhotoSuiteLauncher.py:146,158` -- Hardcoded Russian error messages**

Error messages like `"Папка 'icons' не найдена."` and `"Не удалось загрузить иконку"` are
hardcoded in Russian, despite the launcher supporting English and Russian via
`TRANSLATIONS`. Users who don't read Russian won't understand these errors.

**10. `FaceDetection.py:932,1364-1365` -- `PRAGMA foreign_keys` set on wrong connection**

`PRAGMA foreign_keys = ON` is set in `init_database()` but that connection is closed
immediately. The pragma is per-connection in SQLite. The processing connection at line 1364
sets it correctly, but other ad-hoc connections (e.g., in `clear_image_data`) may not have
it set, risking orphaned records on deletion.

**11. `FaceDBViewer.py:578` -- Singular form hack fails for non-English languages**

```python
t_dog = ld['col_dogs'][:-1] if ld['col_dogs'].endswith('s') else ld['col_dogs']
```
This strips trailing 's' to get a singular form. For Russian `"Собаки"` (Dogs), it doesn't
end in 's', so it stays as the plural. For Italian or other languages with different
pluralization rules, this would also fail. A separate translation key for the singular is
needed.

**12. All files -- `correct_image_orientation` only handles 3 of 8 EXIF orientations**

The orientation function across all files only handles EXIF orientations 3 (180deg), 6
(270deg), and 8 (90deg). It ignores orientations 2 (horizontal flip), 4 (vertical flip), 5
(transpose), and 7 (transverse). Images from some cameras/phones with these orientations
will be processed with incorrect orientation, producing bad face vectors.

---

### MEDIUM -- Correctness / Robustness

**13. `FaceVectorUpdater.py:436` -- Hardcoded 'hog' model ignores user's FaceDetection setting**

`face_recognition.face_locations(image_np, model='hog')` is hardcoded. If the user
originally processed images with the CNN model in FaceDetection, re-extracting vectors with
HOG may find different face locations, producing incompatible or misaligned vectors.

**14. `FaceDetection.py:1366` -- `st_ctime` used for file creation date (wrong on Linux)**

`datetime.fromtimestamp(file_stat.st_ctime)` uses `st_ctime` which is the *inode change
time* on Linux, not the file creation time. This records incorrect creation dates in the
database on Linux systems. `st_birthtime` (Python 3.12+) or falling back to `st_mtime`
would be more correct.

**15. `FaceDB_Cleaner.py:53,58` -- `exit()` at module level kills importing process**

If `imagehash` or `numpy` is missing, `exit()` is called at module scope. This terminates
any Python process that imports this module, not just standalone execution. Should raise
`ImportError` or use conditional import with graceful handling.

**16. `AIPhotoDescriptionGenerator.py:208` -- Default language mismatch**

`self.ui_language = tk.StringVar(value="RU")` defaults to Russian, but the window title is
set in English at line 207. The initial UI state is inconsistent until
`update_ui_language()` runs.

**17. `FaceDBViewer.py:670,676` -- Translated strings interpolated into SQL**

```python
query = f"SELECT pd.person_index, CASE WHEN pd.has_face THEN '{ld['person_type_face']}' ..."
```
Localized strings are directly interpolated into SQL queries. If a translation ever contains
a single quote (e.g., Italian contractions like "l'uomo"), the SQL would break or be
vulnerable to injection. Should use parameterized queries.

**18. All files -- No protection against `TclError` on shutdown**

Background threads use `root.after(0, ...)` for GUI updates. If the user closes the window
while processing is active, `root.after()` raises `TclError` because the Tk interpreter is
destroyed. Only `FaceDB_Cleaner.py` has a partial guard in `_bring_to_front`.

**19. `FaceVectorUpdater.py:432` -- PIL Image opened but never closed**

`pil_image = Image.open(image_path)` is never closed (no `with` statement or explicit
`.close()`). Processing many images accumulates open file handles, potentially hitting OS
limits.

---

## SUGGESTED FUNCTIONALITY IMPROVEMENTS

**1. Add `requirements.txt`**

No dependency file exists. Users must manually figure out all required packages
(`face_recognition`, `ultralytics`, `torch`, `torchvision`, `opencv-python`, `Pillow`,
`imagehash`, `openai`, `anthropic`, `google-generativeai`, `numpy`). A `requirements.txt`
(or `pyproject.toml`) would make setup straightforward.

**2. Extract shared utilities into a common module**

`correct_image_orientation()` is copy-pasted in 5 files with slight variations. Database
connection helpers, EXIF handling, and logging setup should live in a shared `utils.py`.
This eliminates code duplication and ensures bug fixes propagate everywhere.

**3. Implement the "Edit Person" / "Edit Dog" placeholders in FaceDetection**

`edit_person` and `edit_dog` in FaceDetection.py currently show an "under development"
message. These are fundamental CRUD operations that users expect to work from the main
scanning interface.

**4. Persist user settings between sessions**

Settings like face model, YOLO model, thresholds, language preference, last-used database
path, and window geometry are lost on every restart. A `config.ini` or JSON settings file
would significantly improve usability.

**5. Add a database backup mechanism before destructive operations**

FaceDB_Cleaner, NA-to-ID, and FaceVectorUpdater all modify the database destructively
(merge, delete, overwrite). Creating an automatic `.bak` copy before operations would
provide a safety net.

**6. Support HEIF/HEIC image format (iPhone photos)**

The supported extensions list includes common formats but not HEIF/HEIC, which is the
default format on modern iPhones. Adding `pillow-heif` support would cover a major use
case.

**7. Add batch/auto-assign mode in FaceDetection**

Currently, every unrecognized person/dog requires manual dialog interaction. An
"auto-assign as unknown" mode for large initial imports would save significant time when
cataloging a new photo collection.

**8. Show face recognition confidence scores**

The distance from face matching is computed but never displayed to the user. Showing the
confidence/distance score would help users understand why certain identifications were made
and catch incorrect matches.

**9. Add progress bar/percentage to FaceDetection main scan**

The main scanning loop only shows current file number in the status bar. A proper progress
bar with estimated completion would improve the UX for large photo collections.

**10. Add file-based logging alongside GUI logging**

All logging is only to GUI ScrolledText widgets. If the app crashes, all diagnostic info is
lost. Writing logs to a timestamped file would help troubleshooting.

**11. Add search/filter capability in the People and Dogs database tabs**

FaceDetection's People and Dogs database tabs have no search functionality. With hundreds
of entries, finding a specific person or dog requires manual scrolling.

**12. Add export functionality (CSV/JSON)**

There is no way to export the database contents (people list, detection statistics, AI
descriptions) outside the application. CSV or JSON export would be useful for reporting and
integration with other tools.

**13. Update AI model versions**

The code uses Claude 3 Haiku (old), GPT-4o, and Gemini 1.5 Flash. These could be updated
to newer model versions (Claude Haiku 3.5/Sonnet 4, GPT-4.1, Gemini 2.0 Flash) for
improved description quality and potentially lower costs.

**14. Add keyboard shortcuts**

No keyboard shortcuts exist for common operations (start scan, stop, next image, save).
Power users would benefit from hotkeys for repetitive actions during photo cataloging.

**15. Add undo capability for database operations**

No undo exists for any database modifications (merging, deleting, re-assigning). Even a
single-level undo (or snapshot-based rollback) would prevent accidental data loss.
