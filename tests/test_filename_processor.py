"""Tests for DOCX filename variable processing."""

import pytest

from src.exceptions import InvalidFilenameError
from src.filename_processor import (
    build_output_filename,
    detect_filename_variables,
    remove_filename_notes,
    sanitize_filename_value,
)


def test_detects_filename_variable_without_extension() -> None:
    variables = detect_filename_variables("Offer - {{Employee Name}}.docx")

    assert [variable.canonical_name for variable in variables] == ["Employee Name"]


def test_replaces_one_filename_variable() -> None:
    result = build_output_filename(
        "Employment Agreement - {{Employee Name}}.docx",
        {"Employee Name": "John Smith"},
    )

    assert result.filename == "Employment Agreement - John Smith.docx"


def test_replaces_multiple_filename_variables() -> None:
    result = build_output_filename(
        "Offer - {{Employee Name}} - {{Job Title}}.docx",
        {"Employee Name": "Jane Smith", "Job Title": "Data Analyst"},
    )

    assert result.filename == "Offer - Jane Smith - Data Analyst.docx"


def test_removes_complete_double_tilde_filename_note() -> None:
    result = build_output_filename(
        "Offer ~~Read before completion~~ - {{Name}}.docx",
        {"Name": "Alex"},
    )

    assert result.filename == "Offer  - Alex.docx"
    assert result.notes_removed == 1


def test_removes_multiple_and_empty_filename_notes() -> None:
    cleaned, count = remove_filename_notes(
        "Offer ~~first~~~~second~~ for ~~~~ review"
    )

    assert cleaned == "Offer  for  review"
    assert count == 3


def test_variable_inside_filename_note_is_not_detected() -> None:
    variables = detect_filename_variables(
        "Offer ~~Use {{Internal Note}}~~ - {{Employee Name}}.docx"
    )

    assert [variable.canonical_name for variable in variables] == [
        "Employee Name"
    ]


def test_unmatched_double_tilde_marker_is_left_unchanged() -> None:
    result = build_output_filename(
        "Offer ~~unfinished note - {{Name}}.docx",
        {"Name": "Alex"},
    )

    assert result.filename == "Offer ~~unfinished note - Alex.docx"
    assert result.notes_removed == 0


def test_double_tildes_in_replacement_value_remain_literal() -> None:
    result = build_output_filename(
        "Offer - {{Name}}.docx",
        {"Name": "~~Alex~~"},
    )

    assert result.filename == "Offer - ~~Alex~~.docx"


def test_preserves_docx_extension_case() -> None:
    result = build_output_filename("Letter - {{Name}}.DOCX", {"Name": "Alex"})

    assert result.filename == "Letter - Alex.DOCX"


def test_sanitizes_invalid_windows_filename_characters() -> None:
    result = build_output_filename(
        "Record - {{Serial Number}}.docx",
        {"Serial Number": 'A<B>C:D"E/F\\G|H?I*J'},
    )

    assert result.filename == "Record - A_B_C_D_E_F_G_H_I_J.docx"
    assert len(result.sanitizations) == 1
    assert result.sanitizations[0].variable_name == "Serial Number"
    assert set(result.sanitizations[0].changed_characters) == set('<>:"/\\|?*')


def test_removes_trailing_spaces_and_full_stops_from_value() -> None:
    sanitized, changed = sanitize_filename_value("Jane Smith.  ")

    assert sanitized == "Jane Smith"
    assert set(changed) == {".", " "}


@pytest.mark.parametrize("reserved_name", ["CON", "prn", "AUX", "nul", "COM1", "lpt9"])
def test_prevents_reserved_windows_device_names(reserved_name: str) -> None:
    result = build_output_filename("{{Name}}.docx", {"Name": reserved_name})

    assert result.filename == f"_{reserved_name}.docx"


def test_leaves_unrelated_filename_text_unchanged() -> None:
    result = build_output_filename(
        "HR Offer (Final) - {{Employee Name}}.docx",
        {"Employee Name": "Sam Lee"},
    )

    assert result.filename == "HR Offer (Final) - Sam Lee.docx"


def test_missing_replacement_leaves_variable_unchanged() -> None:
    result = build_output_filename("Offer - {{Name}}.docx", {})

    assert result.filename == "Offer - {{Name}}.docx"


def test_rejects_unsupported_file_type() -> None:
    with pytest.raises(InvalidFilenameError, match=r"\.docx"):
        build_output_filename("Offer - {{Name}}.doc", {"Name": "Alex"})


def test_rejects_empty_output_stem() -> None:
    with pytest.raises(InvalidFilenameError, match="empty"):
        build_output_filename("{{Name}}.docx", {"Name": " . "})
