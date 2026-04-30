from dataclasses import dataclass
from datetime import datetime


@dataclass
class AppState:
    is_scanning: bool = False
    is_copying: bool = False

    scan_current: int = 0
    scan_total: int = 0
    scan_files_found: int = 0
    scan_aae_skipped: int = 0

    copy_current: int = 0
    copy_total: int = 0
    copy_copied_bytes: int = 0
    copy_total_bytes: int = 0

    start_time: datetime | None = None
    copy_start_time: datetime | None = None

    last_log_was_progress: bool = False
    last_log_was_scanning: bool = False

    def reset_scan(self, total: int):
        self.is_scanning = True
        self.scan_current = 0
        self.scan_total = total
        self.scan_files_found = 0
        self.scan_aae_skipped = 0
        self.start_time = datetime.now()

    def reset_copy(self):
        self.is_scanning = False
        self.is_copying = True
        self.copy_start_time = datetime.now()

    def finish(self):
        self.is_scanning = False
        self.is_copying = False
        self.copy_start_time = None

    def error(self):
        self.is_scanning = False
        self.is_copying = False
