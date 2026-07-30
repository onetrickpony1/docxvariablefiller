"""Small helpers for preserving Word run formatting."""

from __future__ import annotations

from copy import deepcopy

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.run import Run


_FONT_PROPERTY_TAGS = ("w:rFonts", "w:sz", "w:szCs")


def insert_formatted_run_after(
    reference_run: Run,
    text: str,
    *,
    formatting_source: Run | None = None,
    copy_formatting: bool = True,
) -> Run:
    """Insert a run after *reference_run*, copying source run properties."""

    source = formatting_source or reference_run
    run_element = OxmlElement("w:r")
    if copy_formatting and source._r.rPr is not None:
        run_element.append(deepcopy(source._r.rPr))

    reference_run._r.addnext(run_element)
    inserted_run = Run(run_element, reference_run._parent)
    inserted_run.text = text
    return inserted_run


def copy_font_family_and_size(source: Run, target: Run) -> None:
    """Copy only the effective font family and size XML to *target*.

    Direct run formatting takes precedence, followed by character-style and
    paragraph-style formatting. Other properties are deliberately excluded so
    rich-editor bold, italic, and underline choices remain authoritative.
    """

    target_properties = target._r.get_or_add_rPr()
    for tag in _FONT_PROPERTY_TAGS:
        qualified_tag = qn(tag)
        for existing in tuple(target_properties.findall(qualified_tag)):
            target_properties.remove(existing)
        source_property = _find_effective_run_property(source, qualified_tag)
        if source_property is not None:
            target_properties.append(deepcopy(source_property))


def _find_effective_run_property(
    run: Run,
    qualified_tag: str,
) -> object | None:
    direct_properties = run._r.rPr
    if direct_properties is not None:
        direct_value = direct_properties.find(qualified_tag)
        if direct_value is not None:
            return direct_value

    for style in (run.style, run._parent.style):
        current_style = style
        while current_style is not None:
            style_properties = current_style.element.rPr
            if style_properties is not None:
                style_value = style_properties.find(qualified_tag)
                if style_value is not None:
                    return style_value
            current_style = current_style.base_style
    return None
