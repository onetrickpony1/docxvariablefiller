"""Tests for generic smart-date recognition, grouping, and resolution."""

from datetime import date
from pathlib import Path

from docx import Document
import pytest

from src.date_placeholders import (
    DateInputError,
    cardinal_words,
    collect_date_replacements,
    detect_date_placeholder_groups,
    format_date_interpretation,
    ordinal_digits,
    ordinal_words,
    parse_date_input,
    recognize_date_placeholder,
    resolve_date_group,
)
from src.document_processor import process_template
from src.filename_processor import build_output_filename


ORIGINAL_VARIABLES = (
    "Ordinal Day in Words of Original",
    "Day of Original in Digits",
    "Month of Original",
    "Year of Original in Words",
    "Year of Original in Digits",
)


def test_groups_all_original_date_components() -> None:
    groups = detect_date_placeholder_groups(ORIGINAL_VARIABLES)

    assert len(groups) == 1
    assert groups[0].display_name == "Original"
    assert tuple(
        placeholder.variable_name
        for placeholder in groups[0].placeholders
    ) == ORIGINAL_VARIABLES


def test_groups_arbitrary_shared_text_without_hardcoding() -> None:
    groups = detect_date_placeholder_groups(
        (
            "Day of Bob in Words",
            "Month of Bob",
            "Year of Bob in Digits",
            "Day of Commencement in Digits",
            "Month of Commencement",
        )
    )

    assert tuple(group.display_name for group in groups) == (
        "Bob",
        "Commencement",
    )
    assert len(groups[0].placeholders) == 3
    assert len(groups[1].placeholders) == 2


def test_group_matching_normalizes_case_and_whitespace() -> None:
    groups = detect_date_placeholder_groups(
        ("Day of Contract Signing", "Month of  contract   signing")
    )

    assert len(groups) == 1
    assert groups[0].display_name == "Contract Signing"


@pytest.mark.parametrize(
    "variable_name, group_name",
    (
        ("Start Date", "Start"),
        ("Date of Termination", "Termination"),
        ("Contract Review Date", "Contract Review"),
    ),
)
def test_recognizes_date_as_a_complete_word(
    variable_name: str,
    group_name: str,
) -> None:
    placeholder = recognize_date_placeholder(variable_name)

    assert placeholder is not None
    assert placeholder.component == "date"
    assert placeholder.group_name == group_name


@pytest.mark.parametrize(
    "variable_name",
    (
        "Update Owner",
        "Candidate Name",
        "Date",
        "Day of",
        "Year of Original in Words in Digits",
    ),
)
def test_does_not_guess_unsupported_or_ambiguous_names(
    variable_name: str,
) -> None:
    assert recognize_date_placeholder(variable_name) is None


def test_parses_day_first_input_and_expands_two_digit_year() -> None:
    assert parse_date_input("5/10/25") == date(2025, 10, 5)
    assert parse_date_input("05/10/2025") == date(2025, 10, 5)


@pytest.mark.parametrize(
    "value",
    ("", "2025-10-05", "10/05", "31/02/2025", "01/13/2025"),
)
def test_rejects_invalid_or_non_day_first_date_input(value: str) -> None:
    with pytest.raises(DateInputError):
        parse_date_input(value)


def test_formats_every_original_component_from_one_date() -> None:
    group = detect_date_placeholder_groups(ORIGINAL_VARIABLES)[0]

    replacements = resolve_date_group(group, date(2025, 10, 5))

    assert replacements == {
        "Ordinal Day in Words of Original": "fifth",
        "Day of Original in Digits": "5",
        "Month of Original": "October",
        "Year of Original in Words": "two thousand and twenty-five",
        "Year of Original in Digits": "2025",
    }


def test_supports_day_and_month_output_formats() -> None:
    group = detect_date_placeholder_groups(
        (
            "Day of Bob in Words",
            "Day of Bob in Digits",
            "Month of Bob in Words",
            "Month of Bob in Digits",
        )
    )[0]

    replacements = resolve_date_group(group, date(2025, 10, 21))

    assert replacements == {
        "Day of Bob in Words": "twenty-one",
        "Day of Bob in Digits": "21",
        "Month of Bob in Words": "October",
        "Month of Bob in Digits": "10",
    }


@pytest.mark.parametrize(
    "variable_name, day, expected",
    (
        ("Ordinal Day of Original", 1, "1st"),
        ("Ordinal Day in Words of Commencement", 15, "fifteenth"),
        ("Ordinal Day in Digits of Review", 21, "21st"),
    ),
)
def test_ordinal_component_respects_words_or_digits_format(
    variable_name: str,
    day: int,
    expected: str,
) -> None:
    group = detect_date_placeholder_groups((variable_name,))[0]

    assert resolve_date_group(group, date(2025, 1, day)) == {
        variable_name: expected
    }


def test_day_and_ordinal_day_have_distinct_cardinal_outputs() -> None:
    variables = (
        "Day of Example in Digits",
        "Day of Example in Words",
        "Ordinal Day of Example",
        "Ordinal Day in Words of Example",
    )
    group = detect_date_placeholder_groups(variables)[0]

    assert resolve_date_group(group, date(2025, 1, 5)) == {
        "Day of Example in Digits": "5",
        "Day of Example in Words": "five",
        "Ordinal Day of Example": "5th",
        "Ordinal Day in Words of Example": "fifth",
    }


def test_full_date_uses_unambiguous_four_digit_output() -> None:
    group = detect_date_placeholder_groups(("Start Date",))[0]

    assert resolve_date_group(group, date(2025, 1, 7)) == {
        "Start Date": "07/01/2025"
    }


def test_collection_reports_all_source_placeholders_for_blank_group() -> None:
    groups = detect_date_placeholder_groups(
        ("Day of Bob in Digits", "Month of Bob")
    )

    replacements, blanks = collect_date_replacements(groups, {"bob": " "})

    assert replacements == {}
    assert blanks == ("Day of Bob in Digits", "Month of Bob")


def test_collection_identifies_invalid_group_without_internal_details() -> None:
    groups = detect_date_placeholder_groups(("Start Date",))

    with pytest.raises(DateInputError, match="Start date"):
        collect_date_replacements(groups, {"start": "31/02/2025"})


def test_interpretation_preview_confirms_date_and_generated_words() -> None:
    preview = format_date_interpretation("5/10/25")

    assert "5 October 2025" in preview
    assert "fifth" in preview
    assert "5th" in preview
    assert "day: 5 / five" in preview
    assert "two thousand and twenty-five" in preview


def test_number_words_cover_day_and_year_boundaries() -> None:
    assert ordinal_words(1) == "first"
    assert ordinal_words(20) == "twentieth"
    assert ordinal_words(31) == "thirty-first"
    assert cardinal_words(2000) == "two thousand"
    assert cardinal_words(2025) == "two thousand and twenty-five"


@pytest.mark.parametrize(
    "number, expected",
    (
        (1, "1st"),
        (2, "2nd"),
        (3, "3rd"),
        (4, "4th"),
        (11, "11th"),
        (12, "12th"),
        (13, "13th"),
        (21, "21st"),
        (31, "31st"),
    ),
)
def test_ordinal_digit_suffixes(number: int, expected: str) -> None:
    assert ordinal_digits(number) == expected


def test_date_values_work_in_document_and_filename(tmp_path: Path) -> None:
    template_path = tmp_path / "Agreement - {{Start Date}}.docx"
    output_result = build_output_filename(
        template_path.name,
        {"Start Date": "05/10/2025"},
    )
    output_path = tmp_path / output_result.filename
    document = Document()
    document.add_paragraph(
        "{{Day of Start in Digits}} {{Month of Start}} "
        "{{Year of Start in Words}}"
    )
    document.save(template_path)

    groups = detect_date_placeholder_groups(
        (
            "Start Date",
            "Day of Start in Digits",
            "Month of Start",
            "Year of Start in Words",
        )
    )
    replacements, blanks = collect_date_replacements(
        groups,
        {"start": "5/10/25"},
    )
    summary = process_template(
        template_path,
        output_path,
        replacements,
    )

    assert blanks == ()
    assert output_path.name == "Agreement - 05_10_2025.docx"
    assert Document(output_path).paragraphs[0].text == (
        "5 October two thousand and twenty-five"
    )
    assert summary.total_replacements == 3
