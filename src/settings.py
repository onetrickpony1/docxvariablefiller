"""Minimal per-user preference storage for the desktop interface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


APPLICATION_DIRECTORY_NAME = "DocumentTemplateFiller"
SETTINGS_FILENAME = "settings.json"
LEGACY_APPLICATION_DIRECTORY_NAME = "DocxVariableFiller"
_MAX_SETTINGS_BYTES = 65_536


@dataclass(frozen=True)
class AppSettings:
    """Non-sensitive interface preferences retained between sessions."""

    last_template_path: str | None = None
    highlight_changes: bool = False
    leave_blanks_unchanged: bool = False
    rich_text_variable_indices: tuple[int, ...] = ()


def settings_file_path() -> Path:
    """Return the per-user settings path without creating it."""

    roaming_app_data = os.environ.get("APPDATA")
    base_directory = (
        Path(roaming_app_data)
        if roaming_app_data
        else Path.home() / "AppData" / "Roaming"
    )
    return base_directory / APPLICATION_DIRECTORY_NAME / SETTINGS_FILENAME


def legacy_settings_file_path() -> Path:
    """Return the former Local AppData settings path used before migration."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    base_directory = (
        Path(local_app_data)
        if local_app_data
        else Path.home() / "AppData" / "Local"
    )
    return (
        base_directory
        / LEGACY_APPLICATION_DIRECTORY_NAME
        / SETTINGS_FILENAME
    )


def load_settings(path: Path | None = None) -> AppSettings:
    """Load preferences, returning safe defaults for missing or invalid data."""

    settings_path = path or settings_file_path()
    loaded_settings = _read_settings_file(settings_path)
    if loaded_settings is not None:
        return loaded_settings
    if path is not None:
        return AppSettings()
    try:
        current_path_exists = settings_path.exists()
    except OSError:
        return AppSettings()
    if current_path_exists:
        return AppSettings()

    legacy_path = legacy_settings_file_path()
    legacy_settings = _read_settings_file(legacy_path)
    if legacy_settings is None:
        return AppSettings()
    try:
        save_settings(legacy_settings, settings_path)
        legacy_path.unlink(missing_ok=True)
    except OSError:
        pass
    return legacy_settings


def _read_settings_file(settings_path: Path) -> AppSettings | None:
    try:
        if (
            not settings_path.exists()
            or settings_path.stat().st_size > _MAX_SETTINGS_BYTES
        ):
            return None
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    template_path = data.get("last_template_path")
    highlight_changes = data.get("highlight_changes")
    leave_blanks_unchanged = data.get("leave_blanks_unchanged")
    rich_text_variable_indices = data.get("rich_text_variable_indices")
    validated_rich_indices: tuple[int, ...] = ()
    if (
        isinstance(rich_text_variable_indices, list)
        and len(rich_text_variable_indices) <= 1_000
        and all(
            type(index) is int and 0 <= index < 1_000
            for index in rich_text_variable_indices
        )
        and len(set(rich_text_variable_indices))
        == len(rich_text_variable_indices)
    ):
        validated_rich_indices = tuple(rich_text_variable_indices)
    return AppSettings(
        last_template_path=template_path if isinstance(template_path, str) else None,
        highlight_changes=(
            highlight_changes if isinstance(highlight_changes, bool) else False
        ),
        leave_blanks_unchanged=(
            leave_blanks_unchanged
            if isinstance(leave_blanks_unchanged, bool)
            else False
        ),
        rich_text_variable_indices=validated_rich_indices,
    )


def save_settings(
    settings: AppSettings,
    path: Path | None = None,
) -> None:
    """Atomically save only the approved non-sensitive preference fields."""

    settings_path = path or settings_file_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{settings_path.stem}-",
            suffix=".tmp",
            dir=settings_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(asdict(settings), temporary_file, indent=2, sort_keys=True)
            temporary_file.write("\n")

        os.replace(temporary_path, settings_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
