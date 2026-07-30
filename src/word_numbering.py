"""Create Word list numbering without relying on template paragraph styles."""

from __future__ import annotations

from typing import Literal

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import CONTENT_TYPE as CT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.parts.numbering import NumberingPart
from docx.text.paragraph import Paragraph


ListStyle = Literal["bullet", "number"]


def apply_list_numbering(
    paragraph: Paragraph,
    list_style: ListStyle,
    numbering_ids: dict[ListStyle, int],
) -> None:
    """Apply generated bullet or decimal numbering to *paragraph*.

    The definitions are stored in the document's numbering part and do not
    depend on optional styles such as ``List Bullet`` or ``List Number``.
    ``numbering_ids`` is local to one replacement and keeps adjacent items in
    the same list.
    """

    num_id = numbering_ids.get(list_style)
    if num_id is None:
        numbering = _get_or_create_numbering_part(paragraph).element
        abstract_num_id = _append_abstract_numbering(numbering, list_style)
        num_id = numbering.add_num(abstract_num_id).numId
        numbering_ids[list_style] = num_id

    paragraph_properties = paragraph._p.get_or_add_pPr()
    numbering_properties = paragraph_properties.get_or_add_numPr()
    numbering_properties.get_or_add_ilvl().val = 0
    numbering_properties.get_or_add_numId().val = num_id


def _get_or_create_numbering_part(paragraph: Paragraph) -> NumberingPart:
    document_part = paragraph.part.package.main_document_part
    try:
        return document_part.numbering_part
    except NotImplementedError:
        numbering_element = OxmlElement("w:numbering")
        numbering_part = NumberingPart(
            PackURI("/word/numbering.xml"),
            CT.WML_NUMBERING,
            numbering_element,
            document_part.package,
        )
        document_part.relate_to(numbering_part, RT.NUMBERING)
        return numbering_part


def _append_abstract_numbering(
    numbering: object,
    list_style: ListStyle,
) -> int:
    existing_ids = [
        int(value)
        for value in numbering.xpath("./w:abstractNum/@w:abstractNumId")
    ]
    abstract_num_id = max(existing_ids, default=-1) + 1
    abstract_numbering = OxmlElement("w:abstractNum")
    abstract_numbering.set(
        qn("w:abstractNumId"),
        str(abstract_num_id),
    )
    _append_value_element(
        abstract_numbering,
        "w:multiLevelType",
        "singleLevel",
    )
    level = OxmlElement("w:lvl")
    level.set(qn("w:ilvl"), "0")
    abstract_numbering.append(level)
    _append_value_element(level, "w:start", "1")
    _append_value_element(
        level,
        "w:numFmt",
        "bullet" if list_style == "bullet" else "decimal",
    )
    _append_value_element(
        level,
        "w:lvlText",
        "\u2022" if list_style == "bullet" else "%1.",
    )
    _append_value_element(level, "w:lvlJc", "left")
    paragraph_properties = OxmlElement("w:pPr")
    level.append(paragraph_properties)
    tabs = OxmlElement("w:tabs")
    paragraph_properties.append(tabs)
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "num")
    tab.set(qn("w:pos"), "720")
    tabs.append(tab)
    indentation = OxmlElement("w:ind")
    indentation.set(qn("w:left"), "720")
    indentation.set(qn("w:hanging"), "360")
    paragraph_properties.append(indentation)

    children = list(numbering)
    first_num_index = next(
        (
            index
            for index, child in enumerate(children)
            if child.tag == qn("w:num")
        ),
        len(children),
    )
    numbering.insert(first_num_index, abstract_numbering)
    return abstract_num_id


def _append_value_element(
    parent: object,
    tag_name: str,
    value: str,
) -> None:
    element = OxmlElement(tag_name)
    element.set(qn("w:val"), value)
    parent.append(element)

