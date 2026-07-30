"""Validated, application-local model for user-authored rich replacement text."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ListStyle = Literal["bullet", "number"]
MAX_RICH_TEXT_CHARACTERS = 100_000


@dataclass(frozen=True)
class RichTextRun:
    """One text span with optional character formatting."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("Rich text content must be text.")
        if "\n" in self.text or "\r" in self.text:
            raise ValueError("Rich text runs cannot contain line breaks.")
        for value in (self.bold, self.italic, self.underline):
            if type(value) is not bool:
                raise TypeError("Rich text formatting flags must be Boolean.")


@dataclass(frozen=True)
class RichTextParagraph:
    """One paragraph containing formatted runs and an optional list style."""

    runs: tuple[RichTextRun, ...]
    list_style: ListStyle | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.runs, tuple) or not all(
            isinstance(run, RichTextRun) for run in self.runs
        ):
            raise TypeError("Rich text paragraph runs are invalid.")
        if self.list_style not in {None, "bullet", "number"}:
            raise ValueError("Rich text list style is invalid.")

    @property
    def text(self) -> str:
        """Return this paragraph's unformatted text."""

        return "".join(run.text for run in self.runs)


@dataclass(frozen=True)
class RichTextValue:
    """A bounded sequence of rich paragraphs supplied to the document engine."""

    paragraphs: tuple[RichTextParagraph, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.paragraphs, tuple) or not all(
            isinstance(paragraph, RichTextParagraph)
            for paragraph in self.paragraphs
        ):
            raise TypeError("Rich text paragraphs are invalid.")
        if not self.paragraphs:
            raise ValueError("Rich text must contain at least one paragraph.")
        if sum(len(paragraph.text) for paragraph in self.paragraphs) > (
            MAX_RICH_TEXT_CHARACTERS
        ):
            raise ValueError("Rich text value is too large.")

    @property
    def is_blank(self) -> bool:
        """Return whether the value contains no non-whitespace characters."""

        return not any(paragraph.text.strip() for paragraph in self.paragraphs)

    def filename_text(self) -> str:
        """Return formatting-free text suitable for filename sanitization."""

        return " - ".join(
            paragraph.text.strip()
            for paragraph in self.paragraphs
            if paragraph.text.strip()
        )

    @property
    def requires_block_replacement(self) -> bool:
        """Return whether insertion requires one or more Word paragraphs."""

        return len(self.paragraphs) > 1 or any(
            paragraph.list_style is not None for paragraph in self.paragraphs
        )

