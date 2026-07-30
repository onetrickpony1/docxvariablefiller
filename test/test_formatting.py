"""Tests for run-level formatting preservation during replacement."""

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_COLOR_INDEX
from docx.shared import Pt, RGBColor

from src.document_processor import replace_document_variables
from src.rich_text import RichTextParagraph, RichTextRun, RichTextValue


def test_preserves_bold_formatting() -> None:
    document = Document()
    run = document.add_paragraph().add_run("{{Name}}")
    run.bold = True

    replace_document_variables(document, {"Name": "Alex"})

    assert run.text == "Alex"
    assert run.bold is True


def test_preserves_italic_formatting() -> None:
    document = Document()
    run = document.add_paragraph().add_run("{{Name}}")
    run.italic = True

    replace_document_variables(document, {"Name": "Alex"})

    assert run.text == "Alex"
    assert run.italic is True


def test_preserves_underline_formatting() -> None:
    document = Document()
    run = document.add_paragraph().add_run("{{Name}}")
    run.underline = True

    replace_document_variables(document, {"Name": "Alex"})

    assert run.text == "Alex"
    assert run.underline is True


def test_preserves_font_family_size_and_colour() -> None:
    document = Document()
    run = document.add_paragraph().add_run("{{Name}}")
    run.font.name = "Arial"
    run.font.size = Pt(14)
    run.font.color.rgb = RGBColor(12, 34, 56)

    replace_document_variables(document, {"Name": "Alex"})

    assert run.text == "Alex"
    assert run.font.name == "Arial"
    assert run.font.size == Pt(14)
    assert run.font.color.rgb == RGBColor(12, 34, 56)


def test_preserves_additional_supported_run_formatting() -> None:
    document = Document()
    run = document.add_paragraph().add_run("{{Name}}")
    run.font.strike = True
    run.font.superscript = True
    run.style = document.styles["Strong"]

    replace_document_variables(document, {"Name": "Alex"})

    assert run.font.strike is True
    assert run.font.superscript is True
    assert run.style.name == "Strong"


def test_preserves_formatting_when_only_part_of_run_is_replaced() -> None:
    document = Document()
    run = document.add_paragraph().add_run("Dear {{Name}}, welcome.")
    run.bold = True
    run.font.name = "Calibri"

    replace_document_variables(document, {"Name": "Taylor"})

    assert run.text == "Dear Taylor, welcome."
    assert run.bold is True
    assert run.font.name == "Calibri"


def test_preserves_surrounding_run_text_and_formatting() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    before = paragraph.add_run("Before ")
    before.italic = True
    variable = paragraph.add_run("{{Name}}")
    variable.bold = True
    after = paragraph.add_run(" after")
    after.underline = True

    replace_document_variables(document, {"Name": "Morgan"})

    assert before.text == "Before "
    assert before.italic is True
    assert variable.text == "Morgan"
    assert variable.bold is True
    assert after.text == " after"
    assert after.underline is True


def test_split_run_replacement_uses_first_affected_run_formatting() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    first = paragraph.add_run("Prefix {{Employ")
    first.bold = True
    first.font.name = "Arial"
    second = paragraph.add_run("ee Name}} suffix")
    second.italic = True
    second.font.name = "Times New Roman"

    replace_document_variables(document, {"Employee Name": "Jamie"})

    assert paragraph.text == "Prefix Jamie suffix"
    assert first.text == "Prefix Jamie"
    assert first.bold is True
    assert first.font.name == "Arial"
    assert second.text == " suffix"
    assert second.italic is True
    assert second.font.name == "Times New Roman"


def test_replaces_variable_split_across_several_runs() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    first = paragraph.add_run("Before {{")
    middle_one = paragraph.add_run("Employee")
    middle_two = paragraph.add_run(" Na")
    last = paragraph.add_run("me}} after")

    result = replace_document_variables(document, {"Employee Name": "Casey"})

    assert paragraph.text == "Before Casey after"
    assert first.text == "Before "
    assert middle_one.text == ""
    assert middle_two.text == ""
    assert last.text == " after"
    assert any(run.text == "Casey" for run in paragraph.runs)
    assert result.total_replacements == 1


def test_plain_replacement_uses_formatting_inside_curly_braces() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    opening = paragraph.add_run("Before {{  ")
    opening.bold = False
    opening.font.name = "Calibri"
    variable_name = paragraph.add_run("Employee Name")
    variable_name.bold = True
    variable_name.italic = True
    variable_name.underline = True
    variable_name.font.strike = True
    variable_name.font.superscript = True
    variable_name.font.name = "Arial"
    variable_name.font.size = Pt(15)
    variable_name.font.color.rgb = RGBColor(12, 34, 56)
    variable_name.font.highlight_color = WD_COLOR_INDEX.TURQUOISE
    variable_name.style = document.styles["Strong"]
    closing = paragraph.add_run("  }} after")

    replace_document_variables(
        document,
        {"Employee Name": "Jamie"},
    )

    inserted = next(run for run in paragraph.runs if run.text == "Jamie")
    assert paragraph.text == "Before Jamie after"
    assert inserted.bold is True
    assert inserted.italic is True
    assert inserted.underline is True
    assert inserted.font.strike is True
    assert inserted.font.superscript is True
    assert inserted.font.name == "Arial"
    assert inserted.font.size == Pt(15)
    assert inserted.font.color.rgb == RGBColor(12, 34, 56)
    assert inserted.font.highlight_color == WD_COLOR_INDEX.TURQUOISE
    assert inserted.style.name == "Strong"


def test_rich_replacement_inherits_only_placeholder_font_and_size() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    placeholder = paragraph.add_run("{{Description}}")
    placeholder.bold = True
    placeholder.italic = True
    placeholder.underline = True
    placeholder.font.strike = True
    placeholder.font.name = "Arial"
    placeholder.font.size = Pt(15)
    placeholder.font.color.rgb = RGBColor(12, 34, 56)
    placeholder.font.highlight_color = WD_COLOR_INDEX.TURQUOISE
    placeholder.style = document.styles["Strong"]
    replacement = RichTextValue(
        (
            RichTextParagraph(
                (RichTextRun("Editor text"),),
            ),
        )
    )

    replace_document_variables(
        document,
        {"Description": replacement},
    )

    inserted = next(run for run in paragraph.runs if run.text == "Editor text")
    assert inserted.bold is False
    assert inserted.italic is False
    assert inserted.underline is False
    assert inserted.font.strike is None
    assert inserted.font.name == "Arial"
    assert inserted.font.size == Pt(15)
    assert inserted.font.color.rgb is None
    assert inserted.font.highlight_color is None
    assert inserted.style.name == "Default Paragraph Font"


def test_rich_replacement_resolves_font_and_size_from_character_style() -> None:
    document = Document()
    character_style = document.styles.add_style(
        "Template Variable Font",
        WD_STYLE_TYPE.CHARACTER,
    )
    character_style.font.name = "Times New Roman"
    character_style.font.size = Pt(12)
    paragraph = document.add_paragraph()
    placeholder = paragraph.add_run("{{Description}}")
    placeholder.style = character_style
    replacement = RichTextValue(
        (
            RichTextParagraph(
                (RichTextRun("Editor text", italic=True),),
            ),
        )
    )

    replace_document_variables(
        document,
        {"Description": replacement},
    )

    inserted = next(run for run in paragraph.runs if run.text == "Editor text")
    assert inserted.font.name == "Times New Roman"
    assert inserted.font.size == Pt(12)
    assert inserted.italic is True
    assert inserted.style.name == "Default Paragraph Font"


def test_replaces_multiple_split_and_same_run_variables_in_one_paragraph() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("{{First")
    paragraph.add_run(" Name}} works as {{Job")
    paragraph.add_run(" Title}} for {{Company}}.")

    result = replace_document_variables(
        document,
        {
            "First Name": "Avery",
            "Job Title": "Engineer",
            "Company": "Example Ltd",
        },
    )

    assert paragraph.text == "Avery works as Engineer for Example Ltd."
    assert result.total_replacements == 3
