"""Tests for the validated rich replacement value model."""

import pytest

from src.rich_text import RichTextParagraph, RichTextRun, RichTextValue


def test_filename_text_discards_formatting_and_joins_paragraphs() -> None:
    value = RichTextValue(
        (
            RichTextParagraph((RichTextRun(" First ", bold=True),)),
            RichTextParagraph(
                (RichTextRun("Second", italic=True),),
                list_style="bullet",
            ),
        )
    )

    assert value.filename_text() == "First - Second"


def test_blank_rich_text_is_detected() -> None:
    value = RichTextValue(
        (RichTextParagraph((RichTextRun("   "),)),)
    )

    assert value.is_blank


def test_line_break_inside_a_run_is_rejected() -> None:
    with pytest.raises(ValueError, match="line breaks"):
        RichTextRun("First\nSecond")


def test_lists_require_block_replacement() -> None:
    value = RichTextValue(
        (
            RichTextParagraph(
                (RichTextRun("Item"),),
                list_style="number",
            ),
        )
    )

    assert value.requires_block_replacement
