"""Variable detection, replacement, and sanitization for DOCX filenames."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Mapping

from .exceptions import InvalidFilenameError
from .variable_parser import (
    TemplateVariable,
    detect_variables,
    replace_variables_in_text,
)


_INVALID_WINDOWS_CHARACTERS = frozenset('<>:"/\\|?*')
_RESERVED_WINDOWS_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f]")
_FILENAME_NOTE_PATTERN = re.compile(r"~~.*?~~")


@dataclass(frozen=True)
class FilenameSanitization:
    """A replacement value changed to make it safe in a Windows filename."""

    variable_name: str
    original_value: str
    sanitized_value: str
    changed_characters: tuple[str, ...]


@dataclass(frozen=True)
class FilenameResult:
    """The proposed output filename and any sanitization applied to values."""

    filename: str
    sanitizations: tuple[FilenameSanitization, ...]
    notes_removed: int = 0


def split_docx_filename(filename: str) -> tuple[str, str]:
    """Return the base filename stem and extension for a DOCX filename."""

    name = Path(filename).name
    path = Path(name)
    if path.suffix.lower() != ".docx":
        raise InvalidFilenameError("Please select a Microsoft Word .docx file.")
    return path.stem, path.suffix


def detect_filename_variables(filename: str) -> tuple[TemplateVariable, ...]:
    """Detect variables in the filename stem, excluding its DOCX extension."""

    stem, _extension = split_docx_filename(filename)
    cleaned_stem, _notes_removed = remove_filename_notes(stem)
    return detect_variables(filename_text=cleaned_stem)


def remove_filename_notes(text: str) -> tuple[str, int]:
    """Remove complete ``~~note~~`` regions and return the removal count.

    Unmatched markers are retained because deleting an ambiguous filename
    remainder would be unsafe.
    """

    return _FILENAME_NOTE_PATTERN.subn("", text)


def sanitize_filename_value(value: str) -> tuple[str, tuple[str, ...]]:
    """Return a Windows-safe filename component and changed characters.

    Invalid and control characters are replaced with underscores. Trailing
    spaces and full stops are removed because Windows does not support them.
    """

    changed: list[str] = []
    sanitized_characters: list[str] = []
    for character in value:
        if (
            character in _INVALID_WINDOWS_CHARACTERS
            or _CONTROL_CHARACTER_PATTERN.fullmatch(character)
        ):
            sanitized_characters.append("_")
            if character not in changed:
                changed.append(character)
        else:
            sanitized_characters.append(character)

    sanitized = "".join(sanitized_characters)
    trimmed = sanitized.rstrip(" .")
    for character in sanitized[len(trimmed) :]:
        if character not in changed:
            changed.append(character)
    return trimmed, tuple(changed)


def build_output_filename(
    template_filename: str,
    replacements: Mapping[str, str],
) -> FilenameResult:
    """Build a safe proposed DOCX filename using literal replacements."""

    stem, extension = split_docx_filename(template_filename)
    cleaned_stem, notes_removed = remove_filename_notes(stem)
    safe_replacements: dict[str, str] = {}
    sanitizations: list[FilenameSanitization] = []

    for variable in detect_filename_variables(template_filename):
        if variable.canonical_name not in replacements:
            continue
        original_value = replacements[variable.canonical_name]
        sanitized_value, changed_characters = sanitize_filename_value(original_value)
        safe_replacements[variable.canonical_name] = sanitized_value
        if sanitized_value != original_value:
            sanitizations.append(
                FilenameSanitization(
                    variable_name=variable.canonical_name,
                    original_value=original_value,
                    sanitized_value=sanitized_value,
                    changed_characters=changed_characters,
                )
            )

    output_stem = replace_variables_in_text(
        cleaned_stem,
        safe_replacements,
    ).rstrip(" .")
    if not output_stem:
        raise InvalidFilenameError("The proposed output filename is empty.")

    device_name = output_stem.split(".", maxsplit=1)[0].upper()
    if device_name in _RESERVED_WINDOWS_NAMES:
        output_stem = f"_{output_stem}"

    return FilenameResult(
        filename=f"{output_stem}{extension}",
        sanitizations=tuple(sanitizations),
        notes_removed=notes_removed,
    )
