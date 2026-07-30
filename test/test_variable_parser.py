"""Tests for template variable parsing and plain-text replacement."""

from src.variable_parser import (
    detect_variables,
    extract_variable_tokens,
    replace_variables_in_text,
)


def test_detects_one_variable() -> None:
    variables = detect_variables(["Hello {{Employee Name}}"])

    assert [variable.canonical_name for variable in variables] == ["Employee Name"]


def test_detects_multiple_variables() -> None:
    variables = detect_variables(["{{Employee Name}} starts on {{Start Date}}."])

    assert [variable.canonical_name for variable in variables] == [
        "Employee Name",
        "Start Date",
    ]


def test_repeated_variables_are_returned_once() -> None:
    variables = detect_variables(
        ["{{Employee Name}}", "Welcome, {{Employee Name}}."]
    )

    assert len(variables) == 1
    assert variables[0].original_tokens == ("{{Employee Name}}",)


def test_combines_filename_and_document_variables() -> None:
    variables = detect_variables(
        ["Role: {{Job Title}}"],
        "Offer - {{Employee Name}} - {{Job Title}}",
    )

    assert [variable.canonical_name for variable in variables] == [
        "Job Title",
        "Employee Name",
    ]
    assert variables[0].found_in_document is True
    assert variables[0].found_in_filename is True
    assert variables[1].found_in_document is False
    assert variables[1].found_in_filename is True


def test_surrounding_whitespace_is_ignored_for_equivalence() -> None:
    variables = detect_variables(
        ["{{ Employee Name }} and {{Employee Name}} and {{Employee Name   }}"]
    )

    assert len(variables) == 1
    assert variables[0].canonical_name == "Employee Name"
    assert variables[0].original_tokens == (
        "{{ Employee Name }}",
        "{{Employee Name}}",
        "{{Employee Name   }}",
    )


def test_ignores_empty_and_whitespace_only_braces() -> None:
    assert extract_variable_tokens("{{}} {{   }}") == ()


def test_ignores_single_braces() -> None:
    assert extract_variable_tokens("{Employee Name}") == ()


def test_replacement_values_with_punctuation_are_literal() -> None:
    result = replace_variables_in_text(
        "{{Company}}", {"Company": r"Smith & Co. ($1)\\HQ"}
    )

    assert result == r"Smith & Co. ($1)\\HQ"


def test_replacement_values_with_braces_are_not_reprocessed() -> None:
    result = replace_variables_in_text(
        "{{Employee Name}} / {{Job Title}}",
        {
            "Employee Name": "{{Literal Name}}",
            "Job Title": "Analyst",
            "Literal Name": "Must not appear",
        },
    )

    assert result == "{{Literal Name}} / Analyst"
