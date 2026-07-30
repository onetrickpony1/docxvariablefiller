"""Detection and normalization of double-curly-brace template variables."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping


_VARIABLE_PATTERN = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)


@dataclass(frozen=True)
class TemplateVariable:
    """A unique template variable and the locations where it was found."""

    canonical_name: str
    original_tokens: tuple[str, ...]
    found_in_document: bool
    found_in_filename: bool


@dataclass(frozen=True)
class VariableOccurrence:
    """One variable occurrence and its character range in source text."""

    canonical_name: str
    original_token: str
    start: int
    end: int


def canonicalize_variable_name(name: str) -> str:
    """Return the variable name used for matching and de-duplication."""

    return name.strip()


def find_variable_occurrences(text: str) -> tuple[VariableOccurrence, ...]:
    """Return valid variable occurrences and their source character ranges."""

    occurrences: list[VariableOccurrence] = []
    for match in _VARIABLE_PATTERN.finditer(text):
        canonical_name = canonicalize_variable_name(match.group(1))
        if not canonical_name:
            continue
        occurrences.append(
            VariableOccurrence(
                canonical_name=canonical_name,
                original_token=match.group(0),
                start=match.start(),
                end=match.end(),
            )
        )
    return tuple(occurrences)


def extract_variable_tokens(text: str) -> tuple[tuple[str, str], ...]:
    """Return ``(canonical_name, original_token)`` pairs found in *text*.

    Empty and whitespace-only variables are ignored. The original token is
    retained so later processing can replace the exact source spelling.
    """

    return tuple(
        (occurrence.canonical_name, occurrence.original_token)
        for occurrence in find_variable_occurrences(text)
    )


def detect_variables(
    document_texts: Iterable[str] = (),
    filename_text: str = "",
) -> tuple[TemplateVariable, ...]:
    """Detect and combine unique variables from document and filename text.

    Variables are returned in first-seen order: document content first, then
    filename text. Names are case-sensitive and surrounding whitespace inside
    the braces is ignored when determining equivalence.
    """

    records: dict[str, dict[str, object]] = {}

    def record(text: str, location: str) -> None:
        for canonical_name, original_token in extract_variable_tokens(text):
            item = records.setdefault(
                canonical_name,
                {
                    "tokens": [],
                    "found_in_document": False,
                    "found_in_filename": False,
                },
            )
            item["found_in_document"] = bool(item["found_in_document"]) or (
                location == "document"
            )
            item["found_in_filename"] = bool(item["found_in_filename"]) or (
                location == "filename"
            )
            tokens = item["tokens"]
            assert isinstance(tokens, list)
            if original_token not in tokens:
                tokens.append(original_token)

    for document_text in document_texts:
        record(document_text, "document")
    record(filename_text, "filename")

    return tuple(
        TemplateVariable(
            canonical_name=name,
            original_tokens=tuple(item["tokens"]),
            found_in_document=bool(item["found_in_document"]),
            found_in_filename=bool(item["found_in_filename"]),
        )
        for name, item in records.items()
    )


def replace_variables_in_text(
    text: str,
    replacements: Mapping[str, str],
    *,
    leave_missing_unchanged: bool = True,
) -> str:
    """Replace variables in plain text using canonical variable names.

    Replacement values are inserted literally. They are never interpreted as
    regular expressions, markup, code, or additional template expressions.
    """

    def replace_match(match: re.Match[str]) -> str:
        canonical_name = canonicalize_variable_name(match.group(1))
        if not canonical_name:
            return match.group(0)
        if canonical_name in replacements:
            return replacements[canonical_name]
        return match.group(0) if leave_missing_unchanged else ""

    return _VARIABLE_PATTERN.sub(replace_match, text)
