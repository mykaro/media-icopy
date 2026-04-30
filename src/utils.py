def format_size(size_bytes: int) -> str:
    """Formats bytes into a human-readable string (GB/MB/KB).

    Args:
        size_bytes: The size in bytes to format.

    Returns:
        A formatted string like '1.5 MB' or '500 B'.
    """
    if size_bytes >= 1024**3:
        return f"{size_bytes / (1024**3):.2f} GB"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / (1024**2):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def format_elapsed(seconds: int) -> str:
    """Formats seconds into MM:SS."""
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def calculate_eta(current: int, total: int, elapsed_seconds: float) -> int:
    """Calculates ETA in seconds."""
    if current <= 0 or elapsed_seconds <= 0:
        return 0
    speed = current / elapsed_seconds
    if speed <= 0:
        return 0
    return int((total - current) / speed)


import json
import urllib.request
from urllib.error import URLError, HTTPError
import logging


def check_for_updates(
    current_version: str, repo: str, api_url: str | None = None
) -> dict | None:
    """
    Checks GitHub for a newer version of the application.
    Fails silently if the repository is not found or network is down.

    Args:
        current_version: The current semantic version string (e.g., '0.1.0').
        repo: The GitHub repository in the format 'username/repo'.
        api_url: Optional full API URL. If None, constructed from repo.

    Returns:
        A dict with 'version' and 'url' if an update is found, else None.
    """
    url = api_url or f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "Media-iCopy-Updater"})

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                latest_version = data.get("tag_name", "").lstrip("v")

                if _is_newer(current_version, latest_version):
                    return {"version": latest_version, "url": data.get("html_url", "")}
    except HTTPError as e:
        if e.code != 404:
            logging.warning(f"Update checker HTTP error: {e.code}")
    except URLError as e:
        logging.warning(f"Update checker network error: {e.reason}")
    except Exception as e:
        logging.error(f"Update checker error: {e}")

    return None


def _is_newer(current: str, latest: str) -> bool:
    """Compares semantic versions (e.g. '0.1.0' vs '0.1.1').

    Args:
        current: The current version string.
        latest: The latest version string to compare against.

    Returns:
        True if latest is greater than current, False otherwise.
    """
    try:
        curr_parts = [int(p) for p in current.split(".")]
        lat_parts = [int(p) for p in latest.split(".")]

        for c, l in zip(curr_parts, lat_parts):
            if l > c:
                return True
            elif l < c:
                return False

        if len(lat_parts) > len(curr_parts):
            return any(p > 0 for p in lat_parts[len(curr_parts) :])

    except ValueError:
        return latest > current

    return False
