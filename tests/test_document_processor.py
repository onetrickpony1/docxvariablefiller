"""Tests for scanning and formatting-preserving DOCX replacement."""

from pathlib import Path

from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.shared import Pt
import pytest

from src.document_processor import (
    detect_document_variables,
    load_document,
    process_template,
    replace_document_variables,
    save_document,
    scan_template,
)
from src.exceptions import (
    DocumentAccessError,
    DocumentProcessingError,
    InvalidDocumentError,
    OriginalOverwriteError,
    OutputFileExistsError,
)
from src.rich_text import RichTextParagraph, RichTextRun, RichTextValue


def test_detects_and_replaces_variable_in_normal_paragraph() -> None:
    document = Document()
    paragraph = document.add_paragraph("Dear {{Employee Name}},")

    variables = detect_document_variables(document)
    result = replace_document_variables(document, {"Employee Name": "Jane Smith"})

    assert [variable.canonical_name for variable in variables] == ["Employee Name"]
    assert paragraph.text == "Dear Jane Smith,"
    assert result.replaced_variables == ("Employee Name",)
    assert result.total_replacements == 1


def test_replaces_variable_inside_table() -> None:
    document = Document()
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).paragraphs[0].add_run("Role: {{Job Title}}")

    result = replace_document_variables(document, {"Job Title": "Data Analyst"})

    assert table.cell(0, 0).text == "Role: Data Analyst"
    assert result.total_replacements == 1


def test_replaces_variable_inside_nested_table() -> None:
    document = Document()
    outer_table = document.add_table(rows=1, cols=1)
    nested_table = outer_table.cell(0, 0).add_table(rows=1, cols=1)
    nested_table.cell(0, 0).paragraphs[0].add_run("ID: {{Serial Number}}")

    result = replace_document_variables(document, {"Serial Number": "ABC-123"})

    assert nested_table.cell(0, 0).text == "ID: ABC-123"
    assert result.total_replacements == 1


def test_replaces_variables_inside_header_and_footer() -> None:
    document = Document()
    section = document.sections[0]
    section.header.paragraphs[0].add_run("Company: {{Company}}")
    section.footer.paragraphs[0].add_run("Prepared for {{Employee Name}}")

    result = replace_document_variables(
        document,
        {"Company": "Example Ltd", "Employee Name": "Sam Lee"},
    )

    assert section.header.paragraphs[0].text == "Company: Example Ltd"
    assert section.footer.paragraphs[0].text == "Prepared for Sam Lee"
    assert result.total_replacements == 2


def test_replaces_repeated_variables() -> None:
    document = Document()
    document.add_paragraph("{{Employee Name}}")
    document.add_paragraph("Welcome, {{Employee Name}}.")

    result = replace_document_variables(document, {"Employee Name": "Alex Morgan"})

    assert [paragraph.text for paragraph in document.paragraphs] == [
        "Alex Morgan",
        "Welcome, Alex Morgan.",
    ]
    assert result.unique_variables_replaced == 1
    assert result.total_replacements == 2


def test_replaces_multiple_variables_in_one_run() -> None:
    document = Document()
    paragraph = document.add_paragraph(
        "{{Employee Name}} starts as {{Job Title}} at {{Company}}."
    )

    result = replace_document_variables(
        document,
        {
            "Employee Name": "Chris",
            "Job Title": "Analyst",
            "Company": "Example Ltd",
        },
    )

    assert paragraph.text == "Chris starts as Analyst at Example Ltd."
    assert result.total_replacements == 3


def test_does_not_modify_unrelated_text_or_runs() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    before = paragraph.add_run("Before ")
    variable = paragraph.add_run("{{Name}}")
    after = paragraph.add_run(" after")

    replace_document_variables(document, {"Name": "Taylor"})

    assert before.text == "Before "
    assert variable.text == "Taylor"
    assert after.text == " after"


def test_rich_inline_replacement_formats_only_inserted_text() -> None:
    document = Document()
    paragraph = document.add_paragraph("Before {{Details}} after")
    replacement = RichTextValue(
        (
            RichTextParagraph(
                (
                    RichTextRun("Bold", bold=True),
                    RichTextRun(" and "),
                    RichTextRun(
                        "styled",
                        italic=True,
                        underline=True,
                    ),
                )
            ),
        )
    )

    result = replace_document_variables(
        document,
        {"Details": replacement},
    )

    assert paragraph.text == "Before Bold and styled after"
    bold_run = next(run for run in paragraph.runs if run.text == "Bold")
    styled_run = next(run for run in paragraph.runs if run.text == "styled")
    assert bold_run.bold is True
    assert styled_run.italic is True
    assert styled_run.underline is True
    assert result.total_replacements == 1


def test_rich_block_replacement_creates_bullets_and_numbering() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    placeholder = paragraph.add_run("{{Responsibilities}}")
    placeholder.font.name = "Arial"
    placeholder.font.size = Pt(14)
    replacement = RichTextValue(
        (
            RichTextParagraph(
                (RichTextRun("First bullet", bold=True),),
                list_style="bullet",
            ),
            RichTextParagraph(
                (RichTextRun("Second item", italic=True),),
                list_style="number",
            ),
        )
    )

    replace_document_variables(
        document,
        {"Responsibilities": replacement},
    )

    assert [item.text for item in document.paragraphs] == [
        "First bullet",
        "Second item",
    ]
    assert _list_format(document.paragraphs[0]) == "bullet"
    assert _list_format(document.paragraphs[1]) == "decimal"
    assert next(
        run for run in document.paragraphs[0].runs if run.text
    ).bold is True
    assert next(
        run for run in document.paragraphs[1].runs if run.text
    ).italic is True
    inserted_runs = [
        run
        for item in document.paragraphs
        for run in item.runs
        if run.text
    ]
    assert all(run.font.name == "Arial" for run in inserted_runs)
    assert all(run.font.size == Pt(14) for run in inserted_runs)


def test_rich_block_replacement_rejects_inline_placeholder() -> None:
    document = Document()
    document.add_paragraph("Responsibilities: {{Responsibilities}}")
    replacement = RichTextValue(
        (
            RichTextParagraph(
                (RichTextRun("Item"),),
                list_style="bullet",
            ),
        )
    )

    with pytest.raises(DocumentProcessingError, match="only content"):
        replace_document_variables(
            document,
            {"Responsibilities": replacement},
        )


def test_rich_replacement_supports_review_highlighting() -> None:
    document = Document()
    paragraph = document.add_paragraph("Before {{Details}} after")
    replacement = RichTextValue(
        (
            RichTextParagraph(
                (
                    RichTextRun("Bold", bold=True),
                    RichTextRun(" italic", italic=True),
                )
            ),
        )
    )

    replace_document_variables(
        document,
        {"Details": replacement},
        highlight_changes=True,
    )

    inserted_runs = [
        run for run in paragraph.runs if run.text in {"Bold", " italic"}
    ]
    surrounding_runs = [
        run for run in paragraph.runs if run.text in {"Before ", " after"}
    ]
    assert all(
        run.font.highlight_color == WD_COLOR_INDEX.YELLOW
        for run in inserted_runs
    )
    assert all(run.font.highlight_color is None for run in surrounding_runs)


def test_rich_block_replacement_survives_docx_save_and_reload(
    tmp_path: Path,
) -> None:
    template_path = tmp_path / "Template.docx"
    output_path = tmp_path / "Completed.docx"
    document = Document()
    document.add_paragraph("{{Responsibilities}}")
    document.save(template_path)
    replacement = RichTextValue(
        (
            RichTextParagraph(
                (RichTextRun("Review contracts", bold=True),),
                list_style="bullet",
            ),
            RichTextParagraph(
                (RichTextRun("Prepare reports", italic=True),),
                list_style="bullet",
            ),
        )
    )

    process_template(
        template_path,
        output_path,
        {"Responsibilities": replacement},
    )
    completed = load_document(output_path)

    assert [paragraph.text for paragraph in completed.paragraphs] == [
        "Review contracts",
        "Prepare reports",
    ]
    assert all(
        _list_format(paragraph) == "bullet"
        for paragraph in completed.paragraphs
    )
    assert next(
        run for run in completed.paragraphs[0].runs if run.text
    ).bold is True
    assert next(
        run for run in completed.paragraphs[1].runs if run.text
    ).italic is True


def test_generic_rich_list_does_not_require_template_list_styles() -> None:
    document = Document()
    for style_id in ("ListBullet", "ListNumber"):
        for style_element in document.styles.element.xpath(
            f'./w:style[@w:styleId="{style_id}"]'
        ):
            document.styles.element.remove(style_element)
    document.add_paragraph("{{variable}}")
    replacement = RichTextValue(
        (
            RichTextParagraph(
                (RichTextRun("First item"),),
                list_style="bullet",
            ),
            RichTextParagraph(
                (RichTextRun("Second item"),),
                list_style="bullet",
            ),
        )
    )

    replace_document_variables(document, {"variable": replacement})

    assert [paragraph.text for paragraph in document.paragraphs] == [
        "First item",
        "Second item",
    ]
    assert all(_list_format(paragraph) == "bullet" for paragraph in document.paragraphs)


def test_rich_list_creates_missing_numbering_part(tmp_path: Path) -> None:
    document = Document()
    numbering_relationship_ids = [
        relationship_id
        for relationship_id, relationship in document.part.rels.items()
        if relationship.reltype == RT.NUMBERING
    ]
    for relationship_id in numbering_relationship_ids:
        document.part.drop_rel(relationship_id)
    document.add_paragraph("{{variable}}")
    replacement = RichTextValue(
        (
            RichTextParagraph(
                (RichTextRun("First item"),),
                list_style="number",
            ),
        )
    )

    replace_document_variables(document, {"variable": replacement})
    output_path = tmp_path / "Completed.docx"
    document.save(output_path)
    completed = load_document(output_path)

    assert completed.paragraphs[0].text == "First item"
    assert _list_format(completed.paragraphs[0]) == "decimal"


def test_replaces_variable_split_across_two_runs() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("{{Employee")
    paragraph.add_run(" Name}}")

    variables = detect_document_variables(document)
    result = replace_document_variables(document, {"Employee Name": "Jordan"})

    assert [variable.canonical_name for variable in variables] == ["Employee Name"]
    assert paragraph.text == "Jordan"
    assert paragraph.runs[0].text == "Jordan"
    assert paragraph.runs[1].text == ""
    assert result.total_replacements == 1


def test_scanning_does_not_create_undefined_header_or_footer_parts() -> None:
    document = Document()
    document.add_paragraph("Hello {{Name}}")
    relationships_before = tuple(document.part.rels)

    detect_document_variables(document)

    assert tuple(document.part.rels) == relationships_before


def test_scan_template_combines_document_and_filename_variables(
    tmp_path: Path,
) -> None:
    template_path = tmp_path / "Offer - {{Employee Name}}.docx"
    document = Document()
    document.add_paragraph("Role: {{Job Title}}")
    document.save(template_path)

    variables = scan_template(template_path)

    assert [variable.canonical_name for variable in variables] == [
        "Job Title",
        "Employee Name",
    ]


def test_scan_template_ignores_variables_inside_filename_notes(
    tmp_path: Path,
) -> None:
    template_path = (
        tmp_path
        / "Offer ~~Ignore {{Internal Note}}~~ - {{Employee Name}}.docx"
    )
    document = Document()
    document.add_paragraph("Role: {{Job Title}}")
    document.save(template_path)

    variables = scan_template(template_path)

    assert [variable.canonical_name for variable in variables] == [
        "Job Title",
        "Employee Name",
    ]


def test_process_template_saves_new_file_without_modifying_original(
    tmp_path: Path,
) -> None:
    template_path = tmp_path / "Template.docx"
    output_path = tmp_path / "Completed.docx"
    document = Document()
    document.add_paragraph("Hello {{Name}}")
    document.save(template_path)
    original_bytes = template_path.read_bytes()

    result = process_template(template_path, output_path, {"Name": "Robin"})

    assert result.total_replacements == 1
    assert template_path.read_bytes() == original_bytes
    assert load_document(output_path).paragraphs[0].text == "Hello Robin"


def test_refuses_to_overwrite_original_template(tmp_path: Path) -> None:
    template_path = tmp_path / "Template.docx"
    document = Document()
    document.save(template_path)

    with pytest.raises(OriginalOverwriteError):
        process_template(template_path, template_path, {})


def test_refuses_existing_output_without_confirmation(tmp_path: Path) -> None:
    output_path = tmp_path / "Existing.docx"
    first_document = Document()
    first_document.add_paragraph("Original output")
    first_document.save(output_path)
    second_document = Document()
    second_document.add_paragraph("Replacement output")

    with pytest.raises(OutputFileExistsError):
        save_document(second_document, output_path)

    assert load_document(output_path).paragraphs[0].text == "Original output"


def test_allows_existing_output_after_explicit_confirmation(tmp_path: Path) -> None:
    output_path = tmp_path / "Existing.docx"
    Document().save(output_path)
    replacement_document = Document()
    replacement_document.add_paragraph("Approved replacement")

    save_document(replacement_document, output_path, allow_overwrite=True)

    assert load_document(output_path).paragraphs[0].text == "Approved replacement"


def test_reports_missing_template_as_access_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "Missing.docx"

    with pytest.raises(DocumentAccessError, match="could not be found"):
        load_document(missing_path)


def test_reports_corrupted_docx_without_raw_details(tmp_path: Path) -> None:
    corrupted_path = tmp_path / "Corrupted.docx"
    corrupted_path.write_text("not a Word package", encoding="utf-8")

    with pytest.raises(InvalidDocumentError, match="not a valid"):
        load_document(corrupted_path)


def test_reports_inaccessible_output_location(tmp_path: Path) -> None:
    output_path = tmp_path / "missing-folder" / "Completed.docx"

    with pytest.raises(DocumentAccessError, match="output folder"):
        save_document(Document(), output_path)


def test_failed_save_removes_temporary_file_and_preserves_existing_output(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "Existing.docx"
    original_document = Document()
    original_document.add_paragraph("Existing content")
    original_document.save(output_path)
    original_bytes = output_path.read_bytes()

    class FailingDocument:
        def save(self, path: Path) -> None:
            Path(path).write_bytes(b"partial package")
            raise OSError("simulated write failure")

    with pytest.raises(DocumentAccessError):
        save_document(
            FailingDocument(),  # type: ignore[arg-type]
            output_path,
            allow_overwrite=True,
        )

    assert output_path.read_bytes() == original_bytes
    assert list(tmp_path.glob(".Existing-*.tmp")) == []


def _list_format(paragraph: object) -> str:
    paragraph_properties = paragraph._p.pPr
    assert paragraph_properties is not None
    numbering_properties = paragraph_properties.numPr
    assert numbering_properties is not None
    num_id = numbering_properties.numId.val
    numbering = paragraph.part.package.main_document_part.numbering_part.element
    concrete_numbering = numbering.num_having_numId(num_id)
    abstract_num_id = concrete_numbering.abstractNumId.val
    formats = numbering.xpath(
        './w:abstractNum[@w:abstractNumId="'
        f'{abstract_num_id}"]/w:lvl[@w:ilvl=\"0\"]/w:numFmt/@w:val'
    )
    assert len(formats) == 1
    return formats[0]
