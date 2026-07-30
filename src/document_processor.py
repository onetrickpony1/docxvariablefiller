"""Scan and replace variables in supported Microsoft Word document locations."""

from __future__ import annotations

from collections.abc import Collection, Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile

from docx import Document
from docx.document import Document as DocumentObject
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from .exceptions import (
    DocumentAccessError,
    DocumentProcessingError,
    DocxVariableFillerError,
    InvalidDocumentError,
    OriginalOverwriteError,
    OutputFileExistsError,
)
from .filename_processor import remove_filename_notes, split_docx_filename
from .formatting import copy_font_family_and_size, insert_formatted_run_after
from .rich_text import RichTextParagraph, RichTextRun, RichTextValue
from .word_numbering import apply_list_numbering
from .variable_parser import (
    TemplateVariable,
    VariableOccurrence,
    detect_variables,
    find_variable_occurrences,
)


@dataclass(frozen=True)
class DocumentReplacementResult:
    """Counts produced by a document replacement operation."""

    replaced_variables: tuple[str, ...]
    total_replacements: int
    review_highlighting_enabled: bool = False

    @property
    def unique_variables_replaced(self) -> int:
        """Return the number of different variables replaced."""

        return len(self.replaced_variables)


@dataclass(frozen=True)
class GenerationSummary:
    """In-memory summary of a completed document generation operation."""

    output_filename: str
    save_location: Path
    replaced_variables: tuple[str, ...]
    total_replacements: int
    review_highlighting_enabled: bool
    sanitized_filename_characters: tuple[str, ...] = ()

    @property
    def unique_variables_replaced(self) -> int:
        """Return the number of different document variables replaced."""

        return len(self.replaced_variables)


def _iter_container_paragraphs(container: object) -> Iterator[Paragraph]:
    """Yield paragraphs from a block container and all nested table cells."""

    iter_inner_content = getattr(container, "iter_inner_content", None)
    if iter_inner_content is None:
        return

    for item in iter_inner_content():
        if isinstance(item, Paragraph):
            yield item
        elif isinstance(item, Table):
            yield from _iter_table_paragraphs(item)


def _iter_table_paragraphs(table: Table) -> Iterator[Paragraph]:
    """Yield paragraphs from a table, recursively including nested tables."""

    visited_cells: set[int] = set()
    for row in table.rows:
        for cell in row.cells:
            cell_identity = id(cell._tc)
            if cell_identity in visited_cells:
                continue
            visited_cells.add(cell_identity)
            yield from _iter_container_paragraphs(cell)


def iter_document_paragraphs(document: DocumentObject) -> Iterator[Paragraph]:
    """Yield paragraphs in the body, tables, headers, and footers.

    Header and footer parts shared between sections are yielded only once.
    This function is the extension point for adding future document locations.
    """

    yield from _iter_container_paragraphs(document)

    visited_story_parts: set[int] = set()
    for section in document.sections:
        stories = (
            section.header,
            section.first_page_header,
            section.even_page_header,
            section.footer,
            section.first_page_footer,
            section.even_page_footer,
        )
        for story in stories:
            existing_story = _find_existing_header_footer(story)
            if existing_story is None:
                continue
            story_part_identity = id(existing_story._definition)
            if story_part_identity in visited_story_parts:
                continue
            visited_story_parts.add(story_part_identity)
            yield from _iter_container_paragraphs(existing_story)


def detect_document_variables(
    document: DocumentObject,
    *,
    filename: str = "",
) -> tuple[TemplateVariable, ...]:
    """Detect variables in supported document locations and an optional filename."""

    filename_stem = ""
    if filename:
        filename_stem, _extension = split_docx_filename(filename)
        filename_stem, _notes_removed = remove_filename_notes(filename_stem)
    document_texts = (
        paragraph.text for paragraph in iter_document_paragraphs(document)
    )
    return detect_variables(document_texts, filename_stem)


def replace_document_variables(
    document: DocumentObject,
    replacements: Mapping[str, str | RichTextValue],
    *,
    highlight_changes: bool = False,
    highlight_unchanged_variables: Collection[str] = (),
) -> DocumentReplacementResult:
    """Replace variables throughout all supported document locations.

    Strings are treated as plain text. Rich values can add bold, italic,
    underline, paragraphs, bullets, and numbering. A block rich value requires
    its placeholder to be the only visible content in its Word paragraph.
    Plain text inherits formatting from the first non-whitespace character
    inside the braces. Rich text inherits the placeholder font family and size;
    its bold, italic, and underline choices come from the rich editor.
    When *highlight_changes* is true, inserted runs are highlighted yellow.
    """

    replaced_names: dict[str, None] = {}
    total_replacements = 0

    for paragraph in tuple(iter_document_paragraphs(document)):
        paragraph_replacements = _replace_variables_in_paragraph(
            paragraph,
            replacements,
            highlight_changes=highlight_changes,
        )
        total_replacements += len(paragraph_replacements)
        for canonical_name in paragraph_replacements:
            replaced_names.setdefault(canonical_name, None)
        if highlight_changes and highlight_unchanged_variables:
            _highlight_unchanged_variables_in_paragraph(
                paragraph,
                highlight_unchanged_variables,
            )

    return DocumentReplacementResult(
        replaced_variables=tuple(replaced_names),
        total_replacements=total_replacements,
        review_highlighting_enabled=highlight_changes,
    )


def _replace_variables_in_paragraph(
    paragraph: Paragraph,
    replacements: Mapping[str, str | RichTextValue],
    *,
    highlight_changes: bool,
) -> tuple[str, ...]:
    """Replace all matching variables in one paragraph from right to left."""

    runs = paragraph.runs
    run_spans = _build_run_spans(runs)
    combined_text = "".join(run.text for run in runs)
    occurrences = tuple(
        occurrence
        for occurrence in find_variable_occurrences(combined_text)
        if occurrence.canonical_name in replacements
    )

    for occurrence in reversed(occurrences):
        first_index, first_offset = _locate_character(run_spans, occurrence.start)
        last_index, last_offset = _locate_character(run_spans, occurrence.end - 1)
        first_run = runs[first_index]
        last_run = runs[last_index]
        replacement = replacements[occurrence.canonical_name]
        formatting_source_index, _source_offset = _locate_character(
            run_spans,
            _inner_variable_formatting_position(occurrence),
        )
        formatting_source = runs[formatting_source_index]

        if isinstance(replacement, RichTextValue):
            if replacement.requires_block_replacement:
                if (
                    len(occurrences) != 1
                    or combined_text.strip() != occurrence.original_token
                ):
                    raise DocumentProcessingError(
                        "Bullets, numbering, and multi-paragraph rich text require "
                        "the variable to be the only content in its Word paragraph."
                    )
                _replace_paragraph_with_rich_value(
                    paragraph,
                    runs,
                    replacement,
                    formatting_source=formatting_source,
                    highlight_changes=highlight_changes,
                )
                continue
            _replace_occurrence_with_rich_text(
                runs,
                first_index=first_index,
                first_offset=first_offset,
                last_index=last_index,
                last_offset=last_offset,
                replacement=replacement,
                formatting_source=formatting_source,
                highlight_changes=highlight_changes,
            )
            continue

        if highlight_changes:
            _replace_occurrence_with_highlight(
                runs,
                first_index=first_index,
                first_offset=first_offset,
                last_index=last_index,
                last_offset=last_offset,
                replacement=replacement,
                formatting_source=formatting_source,
            )
            continue

        if first_index == last_index:
            first_run.text = (
                first_run.text[:first_offset]
                + replacement
                + first_run.text[last_offset + 1 :]
            )
            continue

        if formatting_source_index == first_index:
            first_run.text = first_run.text[:first_offset] + replacement
        else:
            first_run.text = first_run.text[:first_offset]
            insert_formatted_run_after(
                first_run,
                replacement,
                formatting_source=formatting_source,
            )
        for run_index in range(first_index + 1, last_index):
            runs[run_index].text = ""
        last_run.text = last_run.text[last_offset + 1 :]

    return tuple(occurrence.canonical_name for occurrence in occurrences)


def _highlight_unchanged_variables_in_paragraph(
    paragraph: Paragraph,
    variable_names: Collection[str],
) -> None:
    """Highlight retained placeholder text without affecting surrounding text."""

    runs = paragraph.runs
    run_spans = _build_run_spans(runs)
    combined_text = "".join(run.text for run in runs)
    occurrences = tuple(
        occurrence
        for occurrence in find_variable_occurrences(combined_text)
        if occurrence.canonical_name in variable_names
    )
    for occurrence in reversed(occurrences):
        first_index, _first_offset = _locate_character(
            run_spans,
            occurrence.start,
        )
        last_index, _last_offset = _locate_character(
            run_spans,
            occurrence.end - 1,
        )
        for run_index in range(last_index, first_index - 1, -1):
            run_start, run_end = run_spans[run_index]
            local_start = max(0, occurrence.start - run_start)
            local_end = min(run_end, occurrence.end) - run_start
            if local_end <= local_start:
                continue
            _highlight_run_slice(
                runs[run_index],
                local_start,
                local_end,
            )


def _highlight_run_slice(
    run: Run,
    start: int,
    end: int,
) -> None:
    """Isolate and highlight one non-empty slice of a run."""

    original_text = run.text
    prefix = original_text[:start]
    highlighted_text = original_text[start:end]
    suffix = original_text[end:]
    run.text = prefix
    highlighted_run = insert_formatted_run_after(run, highlighted_text)
    highlighted_run.font.highlight_color = WD_COLOR_INDEX.YELLOW
    if suffix:
        insert_formatted_run_after(
            highlighted_run,
            suffix,
            formatting_source=run,
        )


def _replace_occurrence_with_rich_text(
    runs: Sequence[Run],
    *,
    first_index: int,
    first_offset: int,
    last_index: int,
    last_offset: int,
    replacement: RichTextValue,
    formatting_source: Run,
    highlight_changes: bool,
) -> None:
    """Replace one inline occurrence with formatted runs."""

    first_run = runs[first_index]
    last_run = runs[last_index]
    suffix = (
        first_run.text[last_offset + 1 :]
        if first_index == last_index
        else last_run.text[last_offset + 1 :]
    )
    first_run.text = first_run.text[:first_offset]
    reference_run = first_run
    for rich_run in replacement.paragraphs[0].runs:
        reference_run = _insert_rich_run_after(
            reference_run,
            rich_run,
            formatting_source=formatting_source,
            highlight_changes=highlight_changes,
        )

    if first_index == last_index:
        if suffix:
            insert_formatted_run_after(
                reference_run,
                suffix,
                formatting_source=first_run,
            )
        return

    for run_index in range(first_index + 1, last_index):
        runs[run_index].text = ""
    last_run.text = suffix


def _replace_paragraph_with_rich_value(
    paragraph: Paragraph,
    existing_runs: Sequence[Run],
    replacement: RichTextValue,
    *,
    formatting_source: Run,
    highlight_changes: bool,
) -> None:
    """Replace an entire placeholder paragraph with rich paragraphs."""

    for run in existing_runs:
        run.text = ""

    target_paragraphs = [paragraph]
    for _rich_paragraph in replacement.paragraphs[1:]:
        target_paragraphs.append(
            _insert_paragraph_after(target_paragraphs[-1], paragraph)
        )

    numbering_ids: dict[str, int] = {}
    for target_paragraph, rich_paragraph in zip(
        target_paragraphs,
        replacement.paragraphs,
        strict=True,
    ):
        _apply_list_format(
            target_paragraph,
            rich_paragraph,
            numbering_ids,
        )
        reference_run = target_paragraph.add_run()
        for rich_run in rich_paragraph.runs:
            reference_run = _insert_rich_run_after(
                reference_run,
                rich_run,
                formatting_source=formatting_source,
                highlight_changes=highlight_changes,
            )


def _insert_paragraph_after(
    reference_paragraph: Paragraph,
    formatting_source: Paragraph,
) -> Paragraph:
    """Insert a paragraph after another, copying its paragraph properties."""

    paragraph_element = OxmlElement("w:p")
    if formatting_source._p.pPr is not None:
        paragraph_element.append(deepcopy(formatting_source._p.pPr))
    reference_paragraph._p.addnext(paragraph_element)
    return Paragraph(paragraph_element, reference_paragraph._parent)


def _apply_list_format(
    paragraph: Paragraph,
    rich_paragraph: RichTextParagraph,
    numbering_ids: dict[str, int],
) -> None:
    if rich_paragraph.list_style is None:
        return
    apply_list_numbering(
        paragraph,
        rich_paragraph.list_style,
        numbering_ids,
    )


def _insert_rich_run_after(
    reference_run: Run,
    rich_run: RichTextRun,
    *,
    formatting_source: Run,
    highlight_changes: bool,
) -> Run:
    inserted_run = insert_formatted_run_after(
        reference_run,
        rich_run.text,
        copy_formatting=False,
    )
    copy_font_family_and_size(formatting_source, inserted_run)
    inserted_run.bold = rich_run.bold
    inserted_run.italic = rich_run.italic
    inserted_run.underline = rich_run.underline
    if highlight_changes:
        inserted_run.font.highlight_color = WD_COLOR_INDEX.YELLOW
    return inserted_run


def _replace_occurrence_with_highlight(
    runs: Sequence[Run],
    *,
    first_index: int,
    first_offset: int,
    last_index: int,
    last_offset: int,
    replacement: str,
    formatting_source: Run,
) -> None:
    """Replace one occurrence and highlight only the newly inserted text."""

    first_run = runs[first_index]
    last_run = runs[last_index]
    suffix = (
        first_run.text[last_offset + 1 :]
        if first_index == last_index
        else last_run.text[last_offset + 1 :]
    )

    first_run.text = first_run.text[:first_offset]
    replacement_run = insert_formatted_run_after(
        first_run,
        replacement,
        formatting_source=formatting_source,
    )
    replacement_run.font.highlight_color = WD_COLOR_INDEX.YELLOW

    if first_index == last_index:
        if suffix:
            insert_formatted_run_after(
                replacement_run,
                suffix,
                formatting_source=first_run,
            )
        return

    for run_index in range(first_index + 1, last_index):
        runs[run_index].text = ""
    last_run.text = suffix


def _build_run_spans(runs: Sequence[Run]) -> tuple[tuple[int, int], ...]:
    """Map each run to its half-open range in the combined paragraph text."""

    spans: list[tuple[int, int]] = []
    position = 0
    for run in runs:
        next_position = position + len(run.text)
        spans.append((position, next_position))
        position = next_position
    return tuple(spans)


def _locate_character(
    run_spans: tuple[tuple[int, int], ...],
    character_position: int,
) -> tuple[int, int]:
    """Return the run index and run-local offset for a paragraph character."""

    for run_index, (start, end) in enumerate(run_spans):
        if start <= character_position < end:
            return run_index, character_position - start
    raise ValueError("Variable character position is outside the paragraph runs.")


def _inner_variable_formatting_position(
    occurrence: VariableOccurrence,
) -> int:
    """Return the first non-whitespace position inside a variable token."""

    inner_text = occurrence.original_token[2:-2]
    leading_whitespace = len(inner_text) - len(inner_text.lstrip())
    return occurrence.start + 2 + leading_whitespace


def load_document(template_path: str | Path) -> DocumentObject:
    """Load a DOCX template and translate expected file errors."""

    path = Path(template_path)
    split_docx_filename(path.name)
    try:
        if not path.exists() or not path.is_file():
            raise DocumentAccessError(
                "The selected document could not be found."
            )
    except OSError as error:
        raise DocumentAccessError(
            "The selected document could not be accessed."
        ) from error

    try:
        return Document(path)
    except (PermissionError, OSError) as error:
        raise DocumentAccessError(
            "The selected document could not be opened. Check that it is accessible "
            "and not locked by another application."
        ) from error
    except (PackageNotFoundError, BadZipFile, KeyError, ValueError) as error:
        raise InvalidDocumentError(
            "The selected file is not a valid Microsoft Word .docx document."
        ) from error
    except Exception as error:
        raise InvalidDocumentError(
            "The selected DOCX document is corrupted or contains unsupported "
            "package data."
        ) from error


def scan_template(template_path: str | Path) -> tuple[TemplateVariable, ...]:
    """Load a template and detect variables in its contents and filename."""

    path = Path(template_path)
    document = load_document(path)
    try:
        return detect_document_variables(document, filename=path.name)
    except DocxVariableFillerError:
        raise
    except Exception as error:
        raise DocumentProcessingError(
            "The document contains content that could not be scanned safely."
        ) from error


def save_document(
    document: DocumentObject,
    output_path: str | Path,
    *,
    template_path: str | Path | None = None,
    allow_overwrite: bool = False,
) -> None:
    """Save a document while protecting the template and existing output files."""

    destination = Path(output_path)
    split_docx_filename(destination.name)

    if template_path is not None and _paths_refer_to_same_file(
        Path(template_path), destination
    ):
        raise OriginalOverwriteError(
            "Choose a different output filename. The original template is protected."
        )
    temporary_path: Path | None = None
    try:
        if not destination.parent.exists() or not destination.parent.is_dir():
            raise DocumentAccessError(
                "The selected output folder does not exist or is not accessible."
            )
        if destination.exists() and not allow_overwrite:
            raise OutputFileExistsError(
                "A file with that name already exists. Confirm overwrite or "
                "choose another name."
            )

        with NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.stem}-",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        document.save(temporary_path)

        if destination.exists() and not allow_overwrite:
            raise OutputFileExistsError(
                "A file with that name appeared before saving completed. "
                "Confirm overwrite and try again."
            )
        os.replace(temporary_path, destination)
        temporary_path = None
    except DocxVariableFillerError:
        raise
    except (PermissionError, OSError) as error:
        raise DocumentAccessError(
            "The completed document could not be saved to the selected location."
        ) from error
    except Exception as error:
        raise DocumentProcessingError(
            "The completed document could not be created safely."
        ) from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def process_template(
    template_path: str | Path,
    output_path: str | Path,
    replacements: Mapping[str, str | RichTextValue],
    *,
    allow_overwrite: bool = False,
    highlight_changes: bool = False,
    highlight_unchanged_variables: Collection[str] = (),
    sanitized_filename_characters: tuple[str, ...] = (),
) -> GenerationSummary:
    """Load, replace, and save a template without modifying the original."""

    document = load_document(template_path)
    try:
        detected_variables = detect_document_variables(
            document,
            filename=Path(template_path).name,
        )
        replaced_template_variables = tuple(
            variable.canonical_name
            for variable in detected_variables
            if variable.canonical_name in replacements
        )
        result = replace_document_variables(
            document,
            replacements,
            highlight_changes=highlight_changes,
            highlight_unchanged_variables=highlight_unchanged_variables,
        )
    except DocxVariableFillerError:
        raise
    except Exception as error:
        raise DocumentProcessingError(
            "The document contains content that could not be processed safely."
        ) from error
    save_document(
        document,
        output_path,
        template_path=template_path,
        allow_overwrite=allow_overwrite,
    )
    destination = Path(output_path)
    return GenerationSummary(
        output_filename=destination.name,
        save_location=destination.parent,
        replaced_variables=replaced_template_variables,
        total_replacements=result.total_replacements,
        review_highlighting_enabled=result.review_highlighting_enabled,
        sanitized_filename_characters=sanitized_filename_characters,
    )


def _paths_refer_to_same_file(first: Path, second: Path) -> bool:
    """Compare paths safely even when the destination does not yet exist."""

    try:
        return first.samefile(second)
    except (FileNotFoundError, OSError):
        first_normalized = os.path.normcase(str(first.resolve(strict=False)))
        second_normalized = os.path.normcase(str(second.resolve(strict=False)))
        return first_normalized == second_normalized


def _find_existing_header_footer(story: object) -> object | None:
    """Find an explicit or inherited header/footer without creating a new part.

    ``python-docx`` creates a blank part when the public content API is accessed
    and no definition exists. These private read-only attributes are used here
    narrowly to avoid changing a body-only document merely by scanning it.
    """

    current_story = story
    while current_story is not None:
        if current_story._has_definition:
            return current_story
        current_story = current_story._prior_headerfooter
    return None
