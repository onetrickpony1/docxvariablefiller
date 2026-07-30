"""Integration tests for generic Company Profile placeholder values."""

from docx import Document

from src.company_placeholder_mapping import (
    company_placeholder_values,
    detected_company_placeholder_names,
)
from src.company_profile import CompanyProfile
from src.document_processor import replace_document_variables
from src.filename_processor import build_output_filename


def _profile() -> CompanyProfile:
    return CompanyProfile(
        display_name="Example Malta",
        company_name="Example Company Limited",
        company_registration_number="C 12345",
        company_address_line_1="1 Example Street",
        company_address_line_2="Level 2",
        company_postcode="VLT 1000",
        company_country="Malta",
        company_director_1="Alex Example",
        company_director_2="Blair Example",
        company_director_3="",
    )


def test_detects_only_supported_company_placeholder_names() -> None:
    detected = detected_company_placeholder_names(
        [
            "Employee Name",
            "Company Director 2",
            "Company Director",
            "Company Name",
            "Unknown Company Field",
        ]
    )

    assert detected == (
        "Company Name",
        "Company Director 2",
        "Company Director",
    )


def test_no_company_placeholders_returns_empty_tuple() -> None:
    assert detected_company_placeholder_names(["Employee Name", "Job Title"]) == ()


def test_generic_document_engine_accepts_company_mapping() -> None:
    document = Document()
    paragraph = document.add_paragraph(
        "{{Company Name}} / {{Company Registration Number}} / "
        "{{Company Director 1}} / {{Company Director 2}} / "
        "{{Company Director}}"
    )

    result = replace_document_variables(
        document,
        company_placeholder_values(_profile()),
    )

    assert paragraph.text == (
        "Example Company Limited / C 12345 / Alex Example / "
        "Blair Example / Alex Example"
    )
    assert result.total_replacements == 5


def test_generic_filename_engine_accepts_company_mapping() -> None:
    result = build_output_filename(
        "Agreement - {{Company Name}}.docx",
        company_placeholder_values(_profile()),
    )

    assert result.filename == "Agreement - Example Company Limited.docx"


def test_company_mapping_does_not_replace_unrelated_variables() -> None:
    document = Document()
    paragraph = document.add_paragraph(
        "{{Company Name}} employs {{Employee Name}}"
    )

    replace_document_variables(
        document,
        company_placeholder_values(_profile()),
    )

    assert paragraph.text == (
        "Example Company Limited employs {{Employee Name}}"
    )
