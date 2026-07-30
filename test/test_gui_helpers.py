"""Headless tests for GUI-independent validation and summary helpers."""

from pathlib import Path

from docx import Document

from src.document_processor import GenerationSummary, process_template
from src.date_placeholders import detect_date_placeholder_groups
from src.filename_processor import build_output_filename
from src.gui import (
    blank_variables_to_highlight,
    collapse_blank_field_names,
    collect_replacement_values,
    collect_sanitized_characters,
    format_filename_notice,
    format_compact_generation_status,
    format_generation_summary,
)


def test_blank_variables_highlight_only_when_both_options_are_enabled() -> None:
    blank_names = ("Job Title", "Start Date")

    assert blank_variables_to_highlight(
        blank_names,
        highlight_changes=True,
        leave_blanks_unchanged=True,
    ) == blank_names
    assert blank_variables_to_highlight(
        blank_names,
        highlight_changes=True,
        leave_blanks_unchanged=False,
    ) == ()
    assert blank_variables_to_highlight(
        blank_names,
        highlight_changes=False,
        leave_blanks_unchanged=True,
    ) == ()


def test_collect_replacement_values_reports_blank_names() -> None:
    replacements, blanks = collect_replacement_values(
        {
            "Employee Name": "Alex",
            "Job Title": "",
            "Company": "   ",
        }
    )

    assert replacements == {"Employee Name": "Alex"}
    assert blanks == ("Job Title", "Company")


def test_collect_replacement_values_preserves_literal_value_whitespace() -> None:
    replacements, blanks = collect_replacement_values({"Name": "  Alex  "})

    assert replacements == {"Name": "  Alex  "}
    assert blanks == ()


def test_collapses_related_blank_date_variables_into_one_field_name() -> None:
    groups = detect_date_placeholder_groups(
        (
            "Day of Original in Digits",
            "Month of Original",
            "Start Date",
        )
    )

    display_names = collapse_blank_field_names(
        (
            "Day of Original in Digits",
            "Month of Original",
            "Start Date",
            "Employee Name",
        ),
        groups,
    )

    assert display_names == (
        "Original date",
        "Start date",
        "Employee Name",
    )


def test_collects_distinct_sanitized_filename_characters() -> None:
    result = build_output_filename(
        "{{Name}} - {{Role}}.docx",
        {"Name": "A/B?", "Role": "C/D."},
    )

    assert collect_sanitized_characters(result) == ("/", "?", ".")


def test_filename_notice_reports_removed_notes_and_sanitization() -> None:
    result = build_output_filename(
        "Offer ~~internal note~~ - {{Name}}.docx",
        {"Name": "A/B"},
    )

    notice = format_filename_notice(result)

    assert "1 template filename note" in notice
    assert "Windows compatibility" in notice


def test_generation_summary_is_non_sensitive() -> None:
    summary = GenerationSummary(
        output_filename="Completed.docx",
        save_location=Path("C:/Documents"),
        replaced_variables=("Name", "Role"),
        total_replacements=3,
        review_highlighting_enabled=True,
        sanitized_filename_characters=("/", " "),
    )

    text = format_generation_summary(summary)

    assert "Completed.docx" in text
    assert "Unique variables replaced: 2" in text
    assert "Document replacements: 3" in text
    assert "Enabled" in text
    assert "[space]" in text
    assert "Alex" not in text

    compact_text = format_compact_generation_status(summary)
    assert "\n" not in compact_text
    assert "Completed.docx" in compact_text
    assert "Variables: 2" in compact_text
    assert "Replacements: 3" in compact_text
    assert "Alex" not in compact_text


def test_process_summary_counts_filename_only_variables(tmp_path: Path) -> None:
    template_path = tmp_path / "Offer - {{Employee Name}}.docx"
    output_path = tmp_path / "Offer - Alex.docx"
    document = Document()
    document.add_paragraph("Role: {{Job Title}}")
    document.save(template_path)

    summary = process_template(
        template_path,
        output_path,
        {"Employee Name": "Alex", "Job Title": "Analyst"},
    )

    assert summary.replaced_variables == ("Job Title", "Employee Name")
    assert summary.unique_variables_replaced == 2
    assert summary.total_replacements == 1
