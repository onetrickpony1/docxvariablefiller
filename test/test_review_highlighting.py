"""Tests for optional yellow highlighting of inserted replacement text."""

from pathlib import Path

from docx import Document
from docx.enum.text import WD_COLOR_INDEX

from src.document_processor import (
    load_document,
    process_template,
    replace_document_variables,
)


def _run_with_text(paragraph: object, text: str) -> object:
    return next(run for run in paragraph.runs if run.text == text)


def test_review_mode_disabled_does_not_add_highlighting() -> None:
    document = Document()
    run = document.add_paragraph().add_run("{{Name}}")

    result = replace_document_variables(document, {"Name": "Alex"})

    assert run.text == "Alex"
    assert run.font.highlight_color is None
    assert result.review_highlighting_enabled is False


def test_review_mode_disabled_preserves_existing_placeholder_highlight() -> None:
    document = Document()
    run = document.add_paragraph().add_run("{{Name}}")
    run.font.highlight_color = WD_COLOR_INDEX.TURQUOISE

    replace_document_variables(document, {"Name": "Alex"})

    assert run.text == "Alex"
    assert run.font.highlight_color == WD_COLOR_INDEX.TURQUOISE


def test_review_mode_highlights_inserted_text_yellow() -> None:
    document = Document()
    paragraph = document.add_paragraph("{{Name}}")

    result = replace_document_variables(
        document,
        {"Name": "Alex"},
        highlight_changes=True,
    )

    inserted = _run_with_text(paragraph, "Alex")
    assert inserted.font.highlight_color == WD_COLOR_INDEX.YELLOW
    assert result.review_highlighting_enabled is True


def test_only_inserted_text_is_highlighted() -> None:
    document = Document()
    paragraph = document.add_paragraph("Before {{Name}} after")

    replace_document_variables(
        document,
        {"Name": "Alex"},
        highlight_changes=True,
    )

    assert paragraph.text == "Before Alex after"
    before = _run_with_text(paragraph, "Before ")
    inserted = _run_with_text(paragraph, "Alex")
    after = _run_with_text(paragraph, " after")
    assert before.font.highlight_color is None
    assert inserted.font.highlight_color == WD_COLOR_INDEX.YELLOW
    assert after.font.highlight_color is None


def test_review_mode_overrides_placeholder_highlight_only_for_inserted_text() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    original = paragraph.add_run("Before {{Name}} after")
    original.font.highlight_color = WD_COLOR_INDEX.PINK

    replace_document_variables(
        document,
        {"Name": "Alex"},
        highlight_changes=True,
    )

    before = _run_with_text(paragraph, "Before ")
    inserted = _run_with_text(paragraph, "Alex")
    after = _run_with_text(paragraph, " after")
    assert before.font.highlight_color == WD_COLOR_INDEX.PINK
    assert inserted.font.highlight_color == WD_COLOR_INDEX.YELLOW
    assert after.font.highlight_color == WD_COLOR_INDEX.PINK


def test_split_run_replacement_highlights_only_inserted_text() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    first = paragraph.add_run("Before {{")
    first.font.highlight_color = WD_COLOR_INDEX.TURQUOISE
    variable_name = paragraph.add_run("Employee Name")
    variable_name.bold = True
    variable_name.italic = True
    last = paragraph.add_run("}} after")
    last.italic = True
    last.font.highlight_color = WD_COLOR_INDEX.BRIGHT_GREEN

    replace_document_variables(
        document,
        {"Employee Name": "Jamie"},
        highlight_changes=True,
    )

    inserted = _run_with_text(paragraph, "Jamie")
    assert paragraph.text == "Before Jamie after"
    assert first.text == "Before "
    assert first.font.highlight_color == WD_COLOR_INDEX.TURQUOISE
    assert inserted.bold is True
    assert inserted.italic is True
    assert inserted.font.highlight_color == WD_COLOR_INDEX.YELLOW
    assert last.text == " after"
    assert last.font.highlight_color == WD_COLOR_INDEX.BRIGHT_GREEN


def test_all_repeated_replacements_are_highlighted() -> None:
    document = Document()
    first_paragraph = document.add_paragraph("{{Name}}")
    second_paragraph = document.add_paragraph("Welcome, {{Name}}.")

    result = replace_document_variables(
        document,
        {"Name": "Alex"},
        highlight_changes=True,
    )

    inserted_runs = [
        _run_with_text(first_paragraph, "Alex"),
        _run_with_text(second_paragraph, "Alex"),
    ]
    assert all(
        run.font.highlight_color == WD_COLOR_INDEX.YELLOW for run in inserted_runs
    )
    assert result.total_replacements == 2


def test_multiple_variables_from_one_run_are_individually_highlighted() -> None:
    document = Document()
    paragraph = document.add_paragraph("{{Name}} works as {{Role}}.")

    replace_document_variables(
        document,
        {"Name": "Alex", "Role": "Analyst"},
        highlight_changes=True,
    )

    assert paragraph.text == "Alex works as Analyst."
    assert _run_with_text(
        paragraph, "Alex"
    ).font.highlight_color == WD_COLOR_INDEX.YELLOW
    assert _run_with_text(
        paragraph, "Analyst"
    ).font.highlight_color == WD_COLOR_INDEX.YELLOW
    assert _run_with_text(paragraph, " works as ").font.highlight_color is None
    assert _run_with_text(paragraph, ".").font.highlight_color is None


def test_highlights_replacements_in_table_header_and_footer() -> None:
    document = Document()
    table_paragraph = document.add_table(rows=1, cols=1).cell(0, 0).paragraphs[0]
    table_paragraph.add_run("{{Table Value}}")
    section = document.sections[0]
    header_paragraph = section.header.paragraphs[0]
    header_paragraph.add_run("{{Header Value}}")
    footer_paragraph = section.footer.paragraphs[0]
    footer_paragraph.add_run("{{Footer Value}}")

    result = replace_document_variables(
        document,
        {
            "Table Value": "Table",
            "Header Value": "Header",
            "Footer Value": "Footer",
        },
        highlight_changes=True,
    )

    assert _run_with_text(
        table_paragraph, "Table"
    ).font.highlight_color == WD_COLOR_INDEX.YELLOW
    assert _run_with_text(
        header_paragraph, "Header"
    ).font.highlight_color == WD_COLOR_INDEX.YELLOW
    assert _run_with_text(
        footer_paragraph, "Footer"
    ).font.highlight_color == WD_COLOR_INDEX.YELLOW
    assert result.total_replacements == 3


def test_existing_unrelated_highlight_remains_unchanged() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    unrelated = paragraph.add_run("Important: ")
    unrelated.font.highlight_color = WD_COLOR_INDEX.RED
    paragraph.add_run("{{Name}}")

    replace_document_variables(
        document,
        {"Name": "Alex"},
        highlight_changes=True,
    )

    assert unrelated.text == "Important: "
    assert unrelated.font.highlight_color == WD_COLOR_INDEX.RED


def test_blank_unchanged_variable_is_highlighted_for_review() -> None:
    document = Document()
    paragraph = document.add_paragraph("Before {{Blank Value}} after")

    result = replace_document_variables(
        document,
        {},
        highlight_changes=True,
        highlight_unchanged_variables=("Blank Value",),
    )

    assert paragraph.text == "Before {{Blank Value}} after"
    assert _run_with_text(
        paragraph,
        "{{Blank Value}}",
    ).font.highlight_color == WD_COLOR_INDEX.YELLOW
    assert _run_with_text(paragraph, "Before ").font.highlight_color is None
    assert _run_with_text(paragraph, " after").font.highlight_color is None
    assert result.total_replacements == 0
    assert result.replaced_variables == ()


def test_split_blank_variable_preserves_formatting_and_highlights_all_parts() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    before = paragraph.add_run("Before ")
    opening = paragraph.add_run("{{")
    opening.bold = True
    name = paragraph.add_run("Blank Value")
    name.italic = True
    closing = paragraph.add_run("}}")
    closing.underline = True
    after = paragraph.add_run(" after")

    replace_document_variables(
        document,
        {},
        highlight_changes=True,
        highlight_unchanged_variables=("Blank Value",),
    )

    assert paragraph.text == "Before {{Blank Value}} after"
    highlighted_runs = [
        run
        for run in paragraph.runs
        if run.text in {"{{", "Blank Value", "}}"}
    ]
    assert len(highlighted_runs) == 3
    assert all(
        run.font.highlight_color == WD_COLOR_INDEX.YELLOW
        for run in highlighted_runs
    )
    assert _run_with_text(paragraph, "{{").bold is True
    assert _run_with_text(paragraph, "Blank Value").italic is True
    assert _run_with_text(paragraph, "}}").underline is True
    assert before.font.highlight_color is None
    assert after.font.highlight_color is None


def test_blank_variable_is_not_highlighted_when_review_mode_is_off() -> None:
    document = Document()
    paragraph = document.add_paragraph("{{Blank Value}}")

    replace_document_variables(
        document,
        {},
        highlight_changes=False,
        highlight_unchanged_variables=("Blank Value",),
    )

    assert paragraph.runs[0].font.highlight_color is None


def test_process_template_returns_review_summary(tmp_path: Path) -> None:
    template_path = tmp_path / "Template.docx"
    output_path = tmp_path / "Completed.docx"
    document = Document()
    document.add_paragraph("{{Name}} / {{Role}} / {{Name}}")
    document.save(template_path)

    summary = process_template(
        template_path,
        output_path,
        {"Name": "Alex", "Role": "Analyst"},
        highlight_changes=True,
        sanitized_filename_characters=("/",),
    )

    assert summary.output_filename == "Completed.docx"
    assert summary.save_location == tmp_path
    assert summary.unique_variables_replaced == 2
    assert summary.total_replacements == 3
    assert summary.review_highlighting_enabled is True
    assert summary.sanitized_filename_characters == ("/",)

    saved_document = load_document(output_path)
    saved_runs = saved_document.paragraphs[0].runs
    assert [
        run.text
        for run in saved_runs
        if run.font.highlight_color == WD_COLOR_INDEX.YELLOW
    ] == ["Alex", "Analyst", "Alex"]
