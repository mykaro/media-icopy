# Media iCopy: Purpose and How It Works

This application is designed for reliable, automated transfer of media files (photos and videos) from an iPhone to a Windows PC. It focuses on data integrity, duplicate prevention, and stable operation even with large volumes of data.

---

### Primary Purpose
The application solves the problem of complex and often unreliable file copying through the standard Windows Explorer, providing incremental backup: only new files are copied.

### Technology Stack
- Programming language: Python 3.10+
- Graphical interface: Terminal Mode (Fallout / RobCo Aesthetic) built on CustomTkinter
- Font: Consolas (monospace, retro-terminal style)
- Colour scheme: Neon Green on a high-contrast dark background
- Device communication: MTP (Media Transfer Protocol) via Windows Shell API (`pywin32`)
- Database: SQLite (for tracking session state and retry queue)
- Localisation: YAML-based i18n system (Ukrainian / English)

---

### How the Application Works (Step by Step)

#### 1. Establishing a Connection and Selecting a Device
The application detects Apple iPhone devices connected via USB in a background thread using `MTPDeviceRegistry`. The connection is initialised via the system MTP protocol through the Windows Shell API. The iPhone must be unlocked and the computer must have been granted "Trust" status.

#### 2. Source Folder Selection
The user selects source folders on the iPhone using the built-in `DeviceFolderBrowser` dialog, which navigates the MTP device tree in real time. Multiple folders can be selected (comma-separated).

#### 3. Smart Scanning and Analysis
Rather than performing a simple copy, the application conducts a deep scan:
- A `set` of all existing local files is pre-built from the destination folder to enable O(1) lookup.
- Files are scanned using a generator-based recursive traversal — thousands of files can be processed without excessive memory usage.
- The `ParseName()` Shell API method is used for O(1) folder navigation (with linear fallback).
- Scan duration is logged and displayed.

#### 4. Incremental Copying and Deduplication
Before the transfer begins, each discovered file is checked for physical presence in the destination folder (case-insensitive path match):
- If a file already exists at the expected path, it is skipped.
- The pre-cached file set is passed into the scanner to avoid fetching MTP metadata for already-existing files — this significantly speeds up repeated runs.
- Apple edit sidecar files (`.AAE`) can be skipped via the UI checkbox.

#### 5. Batch Processing (Batching)
Files are grouped into batches (up to 300 MB by default):
- Very large files get their own batch automatically.
- Session state is saved to SQLite after batch completion.
- In the event of a disconnect or power failure, the application can resume from the last batch.

#### 6. Atomic Copy and Verification
To prevent partial or corrupted files in the destination:
- The file is copied via Windows Shell `CopyHere` to a session-level temp directory (avoids per-file `mkdtemp` overhead).
- Completion is detected via `os.stat().st_size` polling (not `open()`) to avoid Windows file-lock conflicts.
- For files with a known size, copy is confirmed when `actual_size >= expected_size`.
- For files with unknown size (size=0 from MTP), N=3 consecutive stable reads confirm completion.
- An atomic `os.replace()` renames the temp file to the final destination path.
- Size is verified before the rename; mismatch raises `TransientError` → retry.

#### 7. Automatic Recovery System (Retry Policy)
In the event of connection errors:
- Several automatic retries are performed with progressive delays (1, 5, 15 seconds by default).
- On `DeviceDisconnectedError`, `MTPDeviceRegistry.refresh_shell_cache()` is called to force Windows to re-enumerate the MTP device.
- If a file cannot be copied after all retries, it is added to a `retry_queue` in SQLite, processed at the end of the session.

#### 8. Visual Feedback, Localisation, and Logging
The user sees a complete real-time picture of the process:
- A progress bar with file count, data volume (GB/MB), and ETA.
- Support for two languages: Ukrainian and English — switchable in the UI without restart.
- A detailed operation log (successes, skips, errors) in RobCo terminal style.
- Separate scan duration and copy duration metrics logged to console and `logs/events.log`.
- Auto-update check on startup — notifies the user if a newer version is available on GitHub.
- **Share button** in the header — copies the GitHub repository URL to the clipboard with visual confirmation.
- **Update Indicator button** in the header — appears when a new version is detected; clicking it re-opens the update dialog.

#### 9. Path Management (`src/paths.py`)
The application separates two categories of file paths:
- **Bundled resources** (`resource_path()`): read-only files shipped with the app (assets, locale YAML, default config). In a PyInstaller bundle these are extracted to `sys._MEIPASS`; in development they reside in the project root.
- **User-writable data** (`user_data_path()`): runtime files that must survive between sessions (SQLite DB, logs, user config). In frozen mode these are placed next to the `.exe`; in development they are in the project root.

#### 10. Configuration Persistence
Language preference and other user settings are saved automatically to `config/defaults.yaml` in the user data directory whenever the user changes the language in the UI. On the next launch the saved preference is restored.

---
**Result:** A reliable, well-organised media library on your PC with no duplicates and no corrupted files.
