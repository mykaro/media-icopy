import sys
import os

def get_base_dir() -> str:
    """Returns the base directory for bundled resources.
    
    In a PyInstaller bundle, resources are extracted to sys._MEIPASS.
    In development, uses the project root directory.
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        return sys._MEIPASS
    # In dev mode, go up one directory from src/ (to project root)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def resource_path(*parts: str) -> str:
    """Constructs an absolute path to a bundled resource file."""
    return os.path.join(get_base_dir(), *parts)

def get_user_data_dir() -> str:
    """Returns the directory for user-writable files (db, config, logs).
    
    In frozen mode (PyInstaller): next to the .exe file.
    In dev mode: project root.
    """
    if getattr(sys, 'frozen', False):
        # sys.executable is the path to the .exe file
        return os.path.dirname(sys.executable)
    # In dev mode, project root
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def user_data_path(*parts: str) -> str:
    """Constructs an absolute path to a user-writable file."""
    path = os.path.join(get_user_data_dir(), *parts)
    # Ensure parent directories exist
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path
