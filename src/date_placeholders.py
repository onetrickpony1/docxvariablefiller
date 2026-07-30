"""Recognise and resolve grouped date placeholders without document coupling."""

from __future__ import annotations

from calendar import month_name
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
import re


_COMPONENT_PATTERN = re.compile(
    r"^(?P<component>Ordinal\s+Day|Day|Month|Year)"
    r"(?:\s+in\s+(?P<prefix_format>Words|Digits))?"
    r"\s+of\s+(?P<group>.+?)"
    r"(?:\s+in\s+(?P<suffix_format>Words|Digits))?$",
    re.IGNORECASE,
)
_DATE_WORD_PATTERN = re.compile(r"\bDate\b", re.IGNORECASE)
_DATE_INPUT_PATTERN = re.compile(
    r"^\s*(?P<day>[0-9]{1,2})/"
    r"(?P<month>[0-9]{1,2})/"
    r"(?P<year>[0-9]{2}|[0-9]{4})\s*$"
)
_WHITESPACE_PATTERN = re.compile(r"\s+")

_CARDINAL_ONES = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_CARDINAL_TENS = (
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
)
_ORDINAL_UNDER_TWENTY = (
    "zeroth",
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
    "eleventh",
    "twelfth",
    "thirteenth",
    "fourteenth",
    "fifteenth",
    "sixteenth",
    "seventeenth",
    "eighteenth",
    "nineteenth",
)
_ORDINAL_TENS = {
    20: "twentieth",
    30: "thirtieth",
}


class DateInputError(ValueError):
    """A user-correctable invalid smart-date value."""


@dataclass(frozen=True)
class DatePlaceholder:
    """One recognised template placeholder derived from a logical date."""

    variable_name: str
    group_name: str
    group_key: str
    component: str
    output_format: str


@dataclass(frozen=True)
class DatePlaceholderGroup:
    """All recognised placeholders populated from one date entry."""

    display_name: str
    key: str
    placeholders: tuple[DatePlaceholder, ...]


def recognize_date_placeholder(
    variable_name: str,
) -> DatePlaceholder | None:
    """Recognise one documented smart-date placeholder name.

    Component placeholders use ``<component> [in format] of <group>
    [in format]``. Any other placeholder containing ``Date`` as one complete
    word is treated as a full-date placeholder; the remaining text identifies
    its group.
    """

    normalized_name = _normalize_spaces(variable_name)
    component_match = _COMPONENT_PATTERN.fullmatch(normalized_name)
    if component_match:
        prefix_format = component_match.group("prefix_format")
        suffix_format = component_match.group("suffix_format")
        if (
            prefix_format
            and suffix_format
            and prefix_format.casefold() != suffix_format.casefold()
        ):
            return None
        group_name = _normalize_spaces(component_match.group("group"))
        if (
            not group_name
            or re.search(
                r"\s+in\s+(?:Words|Digits)\b",
                group_name,
                flags=re.IGNORECASE,
            )
        ):
            return None
        component = _normalize_component(component_match.group("component"))
        output_format = _normalize_output_format(
            prefix_format or suffix_format,
            component,
        )
        return DatePlaceholder(
            variable_name=variable_name,
            group_name=group_name,
            group_key=_group_key(group_name),
            component=component,
            output_format=output_format,
        )

    date_matches = tuple(_DATE_WORD_PATTERN.finditer(normalized_name))
    if len(date_matches) != 1:
        return None
    match = date_matches[0]
    group_name = _normalize_spaces(
        normalized_name[: match.start()] + " " + normalized_name[match.end() :]
    )
    group_name = re.sub(
        r"^(?:of\s+)|(?:\s+of)$",
        "",
        group_name,
        flags=re.IGNORECASE,
    ).strip()
    if not group_name:
        return None
    return DatePlaceholder(
        variable_name=variable_name,
        group_name=group_name,
        group_key=_group_key(group_name),
        component="date",
        output_format="digits",
    )


def detect_date_placeholder_groups(
    variable_names: Iterable[str],
) -> tuple[DatePlaceholderGroup, ...]:
    """Group recognised date placeholders in first-seen order."""

    grouped: dict[str, list[DatePlaceholder]] = {}
    display_names: dict[str, str] = {}
    for variable_name in variable_names:
        placeholder = recognize_date_placeholder(variable_name)
        if placeholder is None:
            continue
        grouped.setdefault(placeholder.group_key, []).append(placeholder)
        display_names.setdefault(
            placeholder.group_key,
            placeholder.group_name,
        )
    return tuple(
        DatePlaceholderGroup(
            display_name=display_names[key],
            key=key,
            placeholders=tuple(placeholders),
        )
        for key, placeholders in grouped.items()
    )


def parse_date_input(value: str) -> date:
    """Parse an explicitly day-first date in ``D/M/YY`` or ``D/M/YYYY`` form.

    Two-digit years are deliberately interpreted as 2000 through 2099.
    """

    match = _DATE_INPUT_PATTERN.fullmatch(value)
    if match is None:
        raise DateInputError("Enter the date as DD/MM/YYYY.")
    year = int(match.group("year"))
    if year < 100:
        year += 2000
    try:
        return date(
            year,
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError as error:
        raise DateInputError(
            "Enter a real calendar date as DD/MM/YYYY."
        ) from error


def resolve_date_group(
    group: DatePlaceholderGroup,
    value: date,
) -> dict[str, str]:
    """Expand one logical date into generic placeholder/value pairs."""

    return {
        placeholder.variable_name: format_date_placeholder(placeholder, value)
        for placeholder in group.placeholders
    }


def collect_date_replacements(
    groups: Iterable[DatePlaceholderGroup],
    values: Mapping[str, str],
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Resolve nonblank date entries and report blank source placeholders."""

    replacements: dict[str, str] = {}
    blank_variables: list[str] = []
    for group in groups:
        raw_value = values.get(group.key, "")
        if not raw_value.strip():
            blank_variables.extend(
                placeholder.variable_name
                for placeholder in group.placeholders
            )
            continue
        try:
            parsed = parse_date_input(raw_value)
        except DateInputError as error:
            raise DateInputError(
                f"{group.display_name} date: {error}"
            ) from error
        replacements.update(resolve_date_group(group, parsed))
    return replacements, tuple(blank_variables)


def format_date_placeholder(
    placeholder: DatePlaceholder,
    value: date,
) -> str:
    """Format one recognised placeholder from a validated date."""

    if placeholder.component == "date":
        return value.strftime("%d/%m/%Y")
    if placeholder.component == "ordinal_day":
        if placeholder.output_format == "words":
            return ordinal_words(value.day)
        return ordinal_digits(value.day)
    if placeholder.component == "day":
        if placeholder.output_format == "words":
            return cardinal_words(value.day)
        return str(value.day)
    if placeholder.component == "month":
        if placeholder.output_format == "digits":
            return str(value.month)
        return month_name[value.month]
    if placeholder.component == "year":
        if placeholder.output_format == "words":
            return cardinal_words(value.year)
        return str(value.year)
    raise ValueError("Unsupported date placeholder component.")


def format_date_interpretation(value: str) -> str:
    """Return a non-sensitive preview of one entered date."""

    if not value.strip():
        return "Enter a date as DD/MM/YYYY."
    try:
        parsed = parse_date_input(value)
    except DateInputError as error:
        return str(error)
    return (
        f"Interpreted as {parsed.day} {month_name[parsed.month]} "
        f"{parsed.year} (day: {parsed.day} / "
        f"{cardinal_words(parsed.day)}; ordinal: "
        f"{ordinal_digits(parsed.day)} / {ordinal_words(parsed.day)}; "
        f"year: {cardinal_words(parsed.year)})."
    )


def ordinal_digits(number: int) -> str:
    """Return a positive integer with its English ordinal suffix."""

    if number < 1:
        raise ValueError("Ordinal values must be positive.")
    final_two = number % 100
    suffix = "th"
    if not 11 <= final_two <= 13:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def ordinal_words(number: int) -> str:
    """Return an English ordinal word for a day of the month."""

    if not 1 <= number <= 31:
        raise ValueError("Day word values must be between 1 and 31.")
    if number < 20:
        return _ORDINAL_UNDER_TWENTY[number]
    if number in _ORDINAL_TENS:
        return _ORDINAL_TENS[number]
    tens = number - (number % 10)
    return f"{_CARDINAL_TENS[tens // 10]}-{_ORDINAL_UNDER_TWENTY[number % 10]}"


def cardinal_words(number: int) -> str:
    """Return British-style English words for an integer from 0 to 9999."""

    if not 0 <= number <= 9999:
        raise ValueError("Number word values must be between 0 and 9999.")
    if number < 20:
        return _CARDINAL_ONES[number]
    if number < 100:
        tens, remainder = divmod(number, 10)
        result = _CARDINAL_TENS[tens]
        return result if not remainder else f"{result}-{_CARDINAL_ONES[remainder]}"
    if number < 1000:
        hundreds, remainder = divmod(number, 100)
        result = f"{_CARDINAL_ONES[hundreds]} hundred"
        return result if not remainder else f"{result} and {cardinal_words(remainder)}"
    thousands, remainder = divmod(number, 1000)
    result = f"{cardinal_words(thousands)} thousand"
    if not remainder:
        return result
    conjunction = " and " if remainder < 100 else " "
    return f"{result}{conjunction}{cardinal_words(remainder)}"


def _normalize_spaces(value: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", value).strip()


def _group_key(group_name: str) -> str:
    return _normalize_spaces(group_name).casefold()


def _normalize_component(component: str) -> str:
    return component.casefold().replace(" ", "_")


def _normalize_output_format(
    requested_format: str | None,
    component: str,
) -> str:
    if requested_format is not None:
        return requested_format.casefold()
    if component == "month":
        return "words"
    return "digits"
