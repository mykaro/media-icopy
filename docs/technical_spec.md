# Technical Specification: iPhone → PC File Copier
> **For the AI agent:** This document is the single authoritative source of requirements.  
> Read it in full before writing any code. Do not invent details — if something is not here, ask.

---

## 1. Project Goal

A Python application for Windows (GUI only) that copies media files from an iPhone to a PC via MTP (USB), with support for:
- incremental copying (skips already-copied files)
- batch processing (≤ 300 MB per iteration)
- crash recovery without losing progress
- preserving the iPhone's folder structure

---

## 2. System Requirements

| Parameter | Value |
|---|---|
| Python | 3.10+ |
| OS | Windows 10 / Windows 11 (x64 only) |
| Privileges | Regular user (no admin required) |
| External dependencies | `pywin32`, `customtkinter`, `pyyaml`, `pillow`, `pillow-heif` |
| iPhone | iOS 15+ with "Trust This Computer" confirmation |

---

## 3. Project Structure

```
Media iCopy/
├── src/
│   ├── adapters/
│   │   ├── mtp_adapter.py       # MTP via pywin32 Shell API (MTPFileSource, MTPDeviceRegistry)
│   │   ├── local_source.py      # LocalFileSource — test implementation
│   │   ├── cleanup_stream.py    # CleanupStream — auto-cleanup wrapper for temp files
│   │   └── protocol.py          # FileSource Protocol
│   ├── domain/
│   │   ├── models.py            # RemoteFile, CopyTask, Batch, CopyResult, ProgressInfo, MessageType
│   │   ├── batcher.py           # Batch formation algorithm
│   │   ├── copier.py            # Copy pipeline (single file, uses download_file)
│   │   ├── retry.py             # Retry with backoff
│   │   └── exceptions.py        # Exception hierarchy (CopierError, TransientError, etc.)
│   ├── state/
│   │   ├── db.py                # SQLite DAL
│   │   ├── schema.sql           # SQLite schema
│   │   └── session.py           # State machine
│   ├── infrastructure/
│   │   ├── config.py            # AppConfig dataclass + loading
│   │   └── logger.py            # Structured logging setup
│   ├── gui/
│   │   ├── components/          # UI sub-components
│   │   │   ├── __init__.py      # Re-exports DeviceFolderBrowser, SayThanksWindow, UpdateDialog
│   │   │   ├── folder_browser.py # MTP folder browser dialog
│   │   │   ├── modal.py         # Base modal window helper
│   │   │   ├── say_thanks.py    # "Support the project" window
│   │   │   └── update_dialog.py # Auto-update notification dialog
│   │   ├── app.py               # customtkinter GUI (main App class)
│   │   ├── main.py              # GUI entry point
│   │   ├── constants.py         # Styles, colours, fonts, APP_VERSION, GITHUB_REPO
│   │   ├── mixins.py            # AnimationMixin, TooltipMixin
│   │   └── state.py             # AppState dataclass (GUI state management)
│   ├── i18n/
│   │   ├── i18n.py              # Localisation system (UA/EN)
│   │   └── locales/
│   │       ├── uk.yaml          # Ukrainian translations
│   │       └── en.yaml          # English translations
│   ├── core_runner.py           # Pipeline orchestrator (CopierRunner, decoupled from GUI)
│   ├── paths.py                 # Path helpers: resource_path() vs user_data_path() (PyInstaller-aware)
│   └── utils.py                 # Utility functions (size formatting, ETA, update check)
├── tests/
│   ├── conftest.py              # Shared pytest fixtures
│   ├── unit/                    # 10 unit test files (no real MTP/iPhone)
│   └── integration/             # 3 integration test files (real SQLite, LocalFileSource)
├── config/
│   └── defaults.yaml
├── assets/                      # Logos and icons
├── audit/                       # Audit reports and backlog
├── logs/                        # Runtime logs (gitignored)
├── session.db                   # SQLite database (gitignored)
└── pyproject.toml
```

---

## 4. Domain Models

```python
# src/domain/models.py

from dataclasses import dataclass
from enum import Enum, auto

@dataclass(frozen=True)
class RemoteFile:
    """A file on the iPhone."""
    object_id: str          # MTP object path (used as unique identifier)
    relative_path: str      # Relative path from the copy root
    name: str
    size_bytes: int
    modified_at: float | None  # Unix timestamp, may be None

@dataclass
class CopyTask:
    """Unit of work: a single file to be copied."""
    file: RemoteFile
    dest_path: str          # Absolute path on the PC
    attempt: int = 0

@dataclass
class Batch:
    """A batch of files for a single iteration."""
    index: int
    total_batches: int
    tasks: list[CopyTask]
    total_size_bytes: int

class CopyStatus(Enum):
    SUCCESS = auto()
    FAILED_TRANSIENT = auto()   # Retry is possible
    FAILED_FATAL = auto()       # Do not retry

@dataclass
class CopyResult:
    task: CopyTask
    status: CopyStatus
    copied_size_bytes: int = 0

@dataclass
class ProgressInfo:
    """Information about the current copy progress."""
    current_file: int
    total_files: int
    copied_bytes: int
    total_bytes: int
    batch_index: int

class MessageType(Enum):
    """Categorises log messages for GUI rendering."""
    GENERAL = auto()
    SCANNING = auto()
    PROGRESS = auto()
```

---

## 5. FileSource Protocol (mandatory contract)

```python
# src/adapters/protocol.py

from typing import Protocol, BinaryIO, Generator
from pathlib import Path
from collections.abc import Callable

class FileSource(Protocol):
    """
    Abstraction of a file source. MUST be the sole interface
    between domain logic and MTP/filesystem.
    Never import pywin32 outside of mtp_adapter.py.
    """

    def list_files(
        self,
        existing_files_set: set[str] | None = None,
        skip_aae: bool = False,
        on_file_found: Callable[[int, int], None] | None = None,
    ) -> Generator[RemoteFile, None, None]:
        """
        Generator — do NOT return the full list at once.
        Accepts existing_files_set to skip metadata fetch for known files.
        Reports progress via on_file_found(found_count, aae_count).
        """
        ...

    def download_file(
        self,
        file: RemoteFile,
        local_dest: Path,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        """
        Downloads the file directly to local_dest via Windows Shell CopyHere.
        Primary copy method — avoids Python IO bottleneck.
        Reuses session-level temp directories to avoid per-file mkdtemp overhead.
        """
        ...

    def open_stream(self, file: RemoteFile) -> BinaryIO:
        """
        Returns a BinaryIO stream by copying to a temp location first.
        Used as fallback when direct download_file is not suitable.
        """
        ...

    def is_connected(self) -> bool:
        """Checks device availability without raising an exception."""
        ...

    def cleanup(self) -> None:
        """Cleans up session-level temporary directories."""
        ...
```

> **Rule:** All code in `domain/` and `state/` knows only about `FileSource`.  
> `mtp_adapter.py` is the only place where `import win32com` appears.

---

## 6. Configuration

### 6.1 `config/defaults.yaml`

```yaml
batch_limit_mb: 300
retry_attempts: 3
retry_backoff_seconds: [1, 5, 15]
source_folders: ["DCIM"]   # list of folders relative to the iPhone root
log_level: INFO
db_path: ./session.db
log_path: ./logs/events.log
skip_aae: true             # ignore Apple Adjustment Extension (.aae) files
language: auto             # auto | uk | en
```

### 6.2 `AppConfig` dataclass (`src/infrastructure/config.py`)

The `AppConfig` class contains all parameters as dataclass fields with defaults.  
Additional fields not present in YAML:
- `device_name: str` — MTP device name (default: `"Apple iPhone"`)
- `dry_run: bool` — preview mode with no actual copying (default: `False`)
- `language: str` — UI language (default: `"auto"` — detects system locale)

### 6.3 Configuration Priority

`GUI args` > `env variables` > `user config (user_data_path)` > `config/defaults.yaml` > `hardcoded defaults`

- On first launch the bundled `config/defaults.yaml` is read (via `resource_path()`).
- On subsequent launches the user config saved to `user_data_path("config", "defaults.yaml")` takes precedence.
- Language changes in the UI are saved automatically to the user config via `AppConfig.save()`.

Env variables format: `MEDIA_ICOPY_BATCH_LIMIT_MB`, `MEDIA_ICOPY_SKIP_AAE`, etc.

---

## 7. State Machine

### Session States

```
NEW → SCANNING → BATCHING → COPYING → COMPLETED
                                ↓
                             FAILED → RECOVERING → COPYING
```

| State | Description |
|---|---|
| `NEW` | First run, no journal |
| `SCANNING` | Traversing the iPhone, collecting `RemoteFile` objects |
| `BATCHING` | Forming batches |
| `COPYING` | Active copying |
| `FAILED` | Critical error (disconnect, etc.) |
| `RECOVERING` | Loading previous state from DB |
| `COMPLETED` | All files copied, session.db cleared |

### Transition Rules

- On start, always clear the DB (`clear_all_state()`) — the **filesystem** is the source of truth
- `FAILED` → `RECOVERING` happens automatically on the next launch
- `COMPLETED` → delete the session record from DB (not the DB itself)

---

## 8. SQLite Schema

```sql
-- src/state/schema.sql

CREATE TABLE IF NOT EXISTS copied_files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    relative_path TEXT NOT NULL UNIQUE,
    size_bytes    INTEGER NOT NULL,
    copied_at     REAL NOT NULL    -- Unix timestamp
);

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      REAL NOT NULL,
    state           TEXT NOT NULL,  -- value from the SessionState enum
    total_files     INTEGER,
    batch_index     INTEGER DEFAULT 0,
    source_root     TEXT NOT NULL,
    dest_root       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retry_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER REFERENCES sessions(id),
    relative_path   TEXT NOT NULL,
    object_id       TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    attempt         INTEGER DEFAULT 0,
    last_error      TEXT,
    scheduled_at    REAL    -- Unix timestamp of the next attempt
);

CREATE INDEX IF NOT EXISTS idx_copied_path ON copied_files(relative_path);
CREATE INDEX IF NOT EXISTS idx_retry_session ON retry_queue(session_id, scheduled_at);
```

> **Rule:** Always use transactions when writing results.  
> `BEGIN; INSERT INTO copied_files ...; COMMIT;`  
> Never perform a single write outside a transaction during batch operations.

---

## 9. Retry Policy

### Error Classification

| Error Type | Category | Action |
|---|---|---|
| MTP timeout | `TRANSIENT` | Retry with backoff |
| USB disconnect | `TRANSIENT` | Refresh shell cache, wait, retry |
| Disk write error | `TRANSIENT` | Retry |
| No disk space | `FATAL` | Stop, notify user |
| File unavailable on iPhone | `FATAL` | Skip, log |
| Metadata error | `TRANSIENT` | Retry |

### Retry Algorithm

```python
MAX_ATTEMPTS = config.retry_attempts  # default: 3
BACKOFF = config.retry_backoff_seconds  # default: [1, 5, 15]

for attempt in range(MAX_ATTEMPTS):
    try:
        result = copy_file(task)
        break
    except TransientError as e:
        if attempt == MAX_ATTEMPTS - 1:
            mark_failed(task, e)
        else:
            sleep(BACKOFF[attempt])
    except FatalError as e:
        mark_failed(task, e)
        break
```

On `DeviceDisconnectedError`: `MTPDeviceRegistry.refresh_shell_cache()` is called before the next retry.

### Retry Queue

After retries are exhausted, the file is placed in `retry_queue`. After all batches are complete, one additional pass through the retry queue is made using the same rules.

---

## 10. Exception Hierarchy

All custom exceptions inherit from `CopierError` (`src/domain/exceptions.py`).

| Exception | Inherits | Description |
|---|---|---|
| `CopierError` | `Exception` | Base for all application-level errors |
| `TransientError` | `CopierError` | Recoverable errors (timeout, I/O glitch) → triggers **Retry** |
| `FatalError` | `CopierError` | Unrecoverable errors (logic error, missing file) → stops task |
| `DeviceDisconnectedError`| `TransientError`| Specific case for USB disconnect → triggers cache refresh |
| `DiskFullError` | `FatalError` | Destination disk has no space → triggers immediate stop |

---

## 11. Batching Algorithm

```python
# src/domain/batcher.py

def generate_batches(
    files: Generator[RemoteFile, None, None],
    dest_root: Path,
    limit_mb: int,
) -> Generator[Batch, None, None]:
    """
    Incremental batching — does not accumulate all files before starting.
    Files are not sorted — processed in the order received from the scanner.
    """
    limit_bytes = limit_mb * 1024 * 1024
    current_tasks: list[CopyTask] = []
    current_size = 0
    batch_index = 0

    for file in files:
        if file.size_bytes > limit_bytes:
            # Large file → its own batch
            if current_tasks:
                yield Batch(index=batch_index, total_batches=-1,
                            tasks=current_tasks, total_size_bytes=current_size)
                batch_index += 1
                current_tasks, current_size = [], 0
            yield Batch(index=batch_index, total_batches=-1,
                        tasks=[CopyTask(file, dest_path=...)], total_size_bytes=file.size_bytes)
            batch_index += 1
            continue

        if current_size + file.size_bytes > limit_bytes:
            yield Batch(index=batch_index, total_batches=-1,
                        tasks=current_tasks, total_size_bytes=current_size)
            batch_index += 1
            current_tasks, current_size = [], 0

        current_tasks.append(CopyTask(file, dest_path=str(dest_root / file.relative_path)))
        current_size += file.size_bytes

    if current_tasks:
        yield Batch(index=batch_index, total_batches=-1,
                    tasks=current_tasks, total_size_bytes=current_size)
```

> **Important:** `generate_batches` is a generator, it does not return `list[Batch]`.  
> `total_batches` in each batch equals `-1`, as the total number of batches is unknown in incremental mode.  
> `dest_root` and `limit_mb` are passed explicitly — config is not imported inside the module.

---

## 12. Copy Pipeline

### Sequence for Each File

```
1. Check is_connected()
2. Call source.download_file(file, tmp_path, cancel_check)
   └─ Shell CopyHere → temp dir → os.replace() to final .tmp path
3. Verify .tmp size == RemoteFile.size_bytes (skip if size was 0/unknown)
4. os.replace(tmp_path, dest_path)  ← atomic rename
5. BEGIN; INSERT INTO copied_files ...; COMMIT;
6. Delete .tmp (if left behind due to an exception)
```

> **Note:** `download_file` uses Windows Shell `CopyHere` directly to the destination drive.  
> A session-level temp directory is reused per parent folder to avoid per-file `mkdtemp` overhead.  
> `open_stream` (via `CleanupStream`) is available as a fallback for streaming scenarios.

### Graceful Shutdown

- GUI `Stop` button calls `runner.request_cancel()` → sets `_cancel_requested = True`
- `WM_DELETE_WINDOW` handler also calls `stop_copy()` before `destroy()`
- Current file finishes or `.tmp` is cleaned up
- State is written to DB

---

## 13. Idempotency Rules

At every run, the DB is cleared entirely (`clear_all_state()`). The **filesystem** is the sole source of truth.

| Situation | Action |
|---|---|
| File physically exists on disk at the expected path | Skip |
| File does not exist on disk | Copy |
| A `.tmp` file exists | Delete, re-copy |
| After retries exhausted → `retry_queue` | Skip in this run, log |

> **Rule:** The filesystem is the sole source of truth. The DB is used to track the retry queue within the current session.  
> The DB does not persist state between runs — it is cleared at the start of every `run()`.

---

## 14. File Comparison (Deduplication)

### Algorithm

Deduplication logic is embedded in `core_runner.py` (`_scan_phase` and `_pre_cache_dest_files`).

```python
# src/core_runner.py → _pre_cache_dest_files()

def _pre_cache_dest_files(self) -> set[str]:
    """Pre-caches local file list to avoid thousands of disk hits."""
    dest_path = Path(self.config.dest_root)
    existing_files_set = set()
    if dest_path.exists():
        for p in dest_path.rglob("*"):
            if p.is_file():
                rel = p.relative_to(dest_path).as_posix()
                existing_files_set.add(rel.lower())
    return existing_files_set
```

The set is passed into `list_files(existing_files_set=...)` so `mtp_adapter.py` can skip
the expensive `ExtendedProperty("System.Size")` call for already-existing files.

**Comparison criterion:** physical presence of the file on disk at `relative_path` (case-insensitive)  
**Size:** not verified (if the file exists, it is considered valid)  
**Modification date:** ignored (unreliable over MTP)  

---

## 15. Logging Strategy

### Two Streams

| Stream | File | Purpose |
|---|---|---|
| Human log | `logs/events.log` | Plain text, human-readable, not for parsing |
| Structured log | SQLite `sessions` | Machine-readable state |

### Log Levels Policy

```python
DEBUG   # MTP object paths, raw Shell API calls, folder traversal details
INFO    # Every copied file, batch start/end, scan/copy duration
WARNING # Transient errors, retry attempts, device disconnect
ERROR   # Fatal errors, failed files, critical exceptions
```

### Human Log Format

```
2025-01-15 14:23:01 [INFO]    Пристрій: Apple iPhone | Зберігати в: D:/Backup
2025-01-15 14:23:05 [INFO]    Результат аналізу: Знайдено: 3847 | Вже є: 1203 | До копіювання: 2644
2025-01-15 14:23:05 [INFO]    Тривалість аналізу: 00:23
2025-01-15 14:25:33 [INFO]    Відкриття папки: 202510_a
2025-01-15 14:26:01 [WARNING] Помилка копіювання DCIM/101APPLE/IMG_0371.MOV: MTP timeout
2025-01-15 14:26:07 [INFO]    Тривалість копіювання: 01:37
```

> **Note:** Log messages are generated in the active UI language (UA/EN) via the `t()` function.

---

## 16. Observability Metrics

The GUI displays real-time metrics:

```
> ПРОГРЕС [01:37]: 199/199 | 1.05 GB / 1.05 GB
> ЗАЛИШИЛОСЬ: ~0 сек

Завершено!
  • Скопійовано: 199 файлів (1.05 GB)
  • Пропущено: 726 файлів
```

Scan duration and copy duration are logged separately via `runner.scan_duration` and `runner.copy_duration`.

---

## 17. Test Strategy

### Unit Tests (`tests/unit/`) — no iPhone, no Windows API

| File | Coverage |
|---|---|
| `test_batcher.py` | Batch algorithm with mock files of varying sizes |
| `test_comparator.py` | Idempotency scenarios (via `_pre_cache_dest_files` logic) |
| `test_config.py` | AppConfig loading, env vars, YAML |
| `test_copier.py` | Copy pipeline with mocked FileSource |
| `test_core_runner.py` | CopierRunner orchestration with injected dependencies |
| `test_edge_cases.py` | Edge cases: empty folders, large files, cancel mid-copy |
| `test_local_source.py` | LocalFileSource (filesystem-based FileSource) |
| `test_mtp_adapter.py` | MTPFileSource with mocked win32com |
| `test_retry_policy.py` | Exponential backoff and error classification |
| `test_state_machine.py` | All SessionState transitions |
| `test_utils.py` | format_size, format_elapsed, calculate_eta, check_for_updates |

### Integration Tests (`tests/integration/`)

| File | Coverage |
|---|---|
| `test_copy_pipeline.py` | End-to-end copy using `LocalFileSource` (real folder) |
| `test_db.py` | Real SQLite operations (not mocked) |
| `test_recovery.py` | Simulate failure mid-batch, verify state recovery |

### MTP Mock (Dependency Injection)

```python
class LocalFileSource:
    """
    Test implementation of FileSource based on a local folder.
    Used in all tests instead of real MTP.
    """
    def __init__(self, root: Path): ...
    def list_files(...) -> Generator[RemoteFile, None, None]: ...
    def download_file(file, local_dest, cancel_check=None) -> None: ...
    def open_stream(self, file: RemoteFile) -> BinaryIO: ...
    def is_connected(self) -> bool: return True
    def cleanup(self) -> None: ...
```

`CopierRunner` accepts a `source_factory: Callable[[str], FileSource]` parameter for dependency injection, enabling full unit-test coverage without Windows API.

---

## 18. Dependency Management

```toml
# pyproject.toml
[project]
name = "media-icopy"
version = "1.0.0"
description = "Copy media files from iPhone to Windows PC via MTP"
requires-python = ">=3.10"
dependencies = [
    "pywin32==311",
    "customtkinter==5.2.2",
    "pyyaml==6.0.3",
    "pillow==12.2.0",
    "pillow-heif==1.3.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pyinstaller>=6.0",
]

[project.scripts]
media-icopy-gui = "src.gui.main:main"
```

> **Note:** `tqdm` has been removed — progress is displayed via GUI callbacks, not a console progress bar.  
> `pillow` and `pillow-heif` are required for HEIC/HEIF image format support.  
> `pyinstaller` is a dev dependency — install dev extras (`pip install -e ".[dev]"`) to build the executable.

---

## 19. Implementation Roadmap

| Stage | What to Implement | Status |
|---|---|---|
| **0** | `FileSource` protocol + `LocalFileSource` | ✅ Done |
| **1** | SQLite schema + DAL (`db.py`) | ✅ Done |
| **2** | Domain models + batcher | ✅ Done |
| **3** | Deduplication (filesystem-based, in `core_runner.py`) | ✅ Done |
| **4** | Copy pipeline (`copier.py`, `retry.py`, `download_file`) | ✅ Done |
| **5** | State machine (`session.py`) | ✅ Done |
| **6** | Retry policy (`retry.py`, `exceptions.py`) | ✅ Done |
| **7** | `mtp_adapter.py` + `core_runner.py` | ✅ Done |
| **8** | GUI (`customtkinter`) + config | ✅ Done |
| **9** | Logging + metrics | ✅ Done |
| **10** | Localisation (i18n, uk/en YAML) | ✅ Done |
| **11** | Tests (unit + integration) | ✅ Done |
| **12** | Performance optimisations (O(1) ParseName, session-level temp dirs, pre-cached file set) | ✅ Done |
| **13** | GUI modularisation (mixins, AppState, components) | ✅ Done |

---

## 20. Out of Scope (do not implement)

- Cloud backup
- Parallel copying (MTP is single-threaded)
- Android support
- macOS / Linux support
- Auto-launch on iPhone connection

---

## 21. Implemented: GUI (`src/gui/`)

The GUI is implemented using `customtkinter`. Entry point: `src/gui/main.py` → `app.py`.

### GUI Components

- MTP device selection with background thread scanning (`MTPDeviceRegistry`)
- Source folder selection on the iPhone (source_folders) via `DeviceFolderBrowser` dialog
- Destination folder selection (dest_root) via system dialog
- Interface language selection (UA/EN) with instant UI update via listener pattern
- Progress bar displaying file count, bytes (in X.X GB / Y.Y GB format), and current folder
- Log window with RobCo styling and colour-coded output (INFO / WARNING / ERROR)
- Start / Stop buttons with Fallout aesthetic
- Support Project button with animation and a pop-up window (`SayThanksWindow`)
- **Share button** (`btn_share`) in the header — copies the GitHub URL to clipboard with 2-second visual confirmation
- **Update Indicator button** (`btn_update_indicator`) in the header — hidden by default; appears (inverted `T_GREEN` bg / `T_BG` text) when a newer version is detected; clicking reopens `UpdateDialog`
- Animations: typewriter signature effect, pulsing `>` cursor, support button highlight
- `.AAE` skip checkbox with tooltip
- Auto-update check on startup (`UpdateDialog` if newer version found)
- Graceful window close handling (`WM_DELETE_WINDOW`)

### GUI Architecture

| File | Role |
|---|---|
| `app.py` | Main `App` class (inherits `AnimationMixin`, `TooltipMixin`) |
| `state.py` | `AppState` dataclass — all mutable UI state in one place |
| `mixins.py` | `AnimationMixin` (animations), `TooltipMixin` (hover tooltips) |
| `constants.py` | Colour constants, font name, `APP_VERSION`, `GITHUB_REPO` |
| `components/folder_browser.py` | MTP device folder tree browser |
| `components/say_thanks.py` | "Support the project" modal |
| `components/update_dialog.py` | Update available notification |
| `components/modal.py` | Base frameless modal window helper |

### Integration with `CopierRunner`

`CopierRunner` (in `core_runner.py`) runs in a background thread. The GUI receives updates via callbacks:

```python
runner.on_log            = lambda level, msg, msg_type: ...
runner.on_scan_progress  = lambda cur, total, found, aae: ...
runner.on_progress       = lambda info: ...  # Uses the ProgressInfo dataclass
runner.on_finish         = lambda files, bytes_copied, skipped: ...
runner.on_error          = lambda e: ...
runner.on_cancel         = lambda: ...
```

---

## 22. Localisation (i18n)

The system is implemented in `src/i18n/i18n.py` with YAML locale files in `src/i18n/locales/`.

### Core Principles:
- Support for two languages: **Ukrainian (uk)** and **English (en)**.
- Automatic detection of the system language on first launch (`language: auto`).
- YAML files contain all interface and log strings — one key per translatable string.
- The `t(key, **kwargs)` function for retrieving translations with placeholder support.
- A subscription mechanism (`add_listener`) allows UI components to update instantly when the user changes the language.
- Language preference is saved to `config/defaults.yaml` on change.

---

## 23. Auto-Update System

The application automatically checks for updates via GitHub Releases on startup.
- Uses `urllib.request` to query the GitHub API without adding external dependencies.
- Handles `404 Not Found` silently (e.g., if the repository does not exist or has no releases yet).
- When a newer version is found, `UpdateDialog` (styled in Fallout aesthetic) appears.
- The user can choose to skip the update or be redirected to `html_url` via their default web browser.
- Version and repo are defined in `src/gui/constants.py` (`APP_VERSION`, `GITHUB_REPO`).

---

## 24. Packaging & Build

The application is packaged into a standalone Windows executable using `PyInstaller`.

### Build Requirements:
```bash
pip install -e ".[dev]"   # installs all deps including pyinstaller
```

### Build Command:
```bash
pyinstaller --noconfirm --onefile --windowed --name "media-icopy" \
            --icon "assets/logo_256x256.ico" \
            --add-data "src/i18n/locales;src/i18n/locales" \
            --add-data "assets;assets" \
            --add-data "config;config" \
            src/gui/main.py
```

> **Note on paths:** `resource_path()` resolves bundled assets from `sys._MEIPASS` in frozen mode.  
> `user_data_path()` resolves writable files (DB, logs, user config) next to the `.exe` — never inside `_MEIPASS`.

---

## 25. MTP Performance Architecture

Key optimisations implemented in `mtp_adapter.py`:

| Optimisation | Description |
|---|---|
| `ParseName()` O(1) lookup | Shell `ParseName()` used as fast path for folder/file navigation; linear iteration as fallback |
| Pre-cached existing files set | `_pre_cache_dest_files()` builds a `set[str]` of local files before scanning; passed into `list_files()` to skip MTP metadata fetch for known files |
| Session-level temp directories | `_temp_dirs: dict[str, Path]` reused per parent folder; avoids per-file `mkdtemp` overhead |
| `os.stat()` polling | File completion checked via `os.stat().st_size` (not `open()`), avoiding Windows file-lock conflicts |
| Folder object cache | `_folder_cache: dict[str, Any]` stores resolved Shell folder objects to avoid repeated traversal |
| Stable-size fallback | For files with unknown size (size=0), waits for N=3 consecutive stable `stat()` reads |
