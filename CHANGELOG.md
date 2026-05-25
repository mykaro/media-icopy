# Changelog

All notable changes to this project will be documented in this file.

## v1.0.0 (2026-04-30)
- Initial public release of Media iCopy.
- **Core Features:**
    - Reliable iPhone media transfer via MTP.
    - Incremental copying (skips existing files).
    - Preservation of original folder structure.
    - Support for Apple Adjustment files (.AAE) skipping.
    - Portable single executable - no installation required.
- **Privacy & Security:**
    - 100% local transfers with zero telemetry.
- **Technical Highlights:**
    - High-performance MTP access via Windows Shell API (pywin32).
    - SQLite-backed session tracking and retry queue.
    - Atomic file operations (.tmp then rename).
    - Multi-threaded scanning and copying for a responsive UI.
- **User Interface:**
    - Retro "RobCo" Fallout-inspired terminal aesthetic.
    - Multi-language support: Ukrainian and English.
    - Real-time progress tracking with ETA and speed metrics.
    - Integrated auto-update system.
