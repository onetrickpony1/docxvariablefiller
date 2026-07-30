"""Validated data model for persistent Company Profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Mapping, Sequence

from .exceptions import CompanyProfileValidationError


MAX_COMPANY_PROFILES = 100
REGISTRATION_NUMBER_PATTERN = re.compile(r"^C [0-9]{5,8}$")

_FIELD_LIMITS = {
    "display_name": 200,
    "company_name": 200,
    "company_registration_number": 32,
    "company_address_line_1": 300,
    "company_address_line_2": 300,
    "company_postcode": 32,
    "company_country": 100,
    "company_director_1": 200,
    "company_director_2": 200,
    "company_director_3": 200,
}
_OPTIONAL_FIELDS = frozenset(
    {
        "company_director_2",
        "company_director_3",
    }
)
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class CompanyProfile:
    """One normalized and validated company record."""

    display_name: str
    company_name: str
    company_registration_number: str
    company_address_line_1: str
    company_address_line_2: str
    company_postcode: str
    company_country: str
    company_director_1: str
    company_director_2: str
    company_director_3: str

    def __post_init__(self) -> None:
        for field_name, maximum_length in _FIELD_LIMITS.items():
            raw_value = getattr(self, field_name)
            if not isinstance(raw_value, str):
                raise CompanyProfileValidationError(
                    f"{_field_label(field_name)} must be text."
                )
            normalized_value = raw_value.strip()
            object.__setattr__(self, field_name, normalized_value)
            if not normalized_value and field_name not in _OPTIONAL_FIELDS:
                raise CompanyProfileValidationError(
                    f"{_field_label(field_name)} is required."
                )
            if len(normalized_value) > maximum_length:
                raise CompanyProfileValidationError(
                    f"{_field_label(field_name)} is too long."
                )
            if _CONTROL_CHARACTER_PATTERN.search(normalized_value):
                raise CompanyProfileValidationError(
                    f"{_field_label(field_name)} contains unsupported "
                    "control characters."
                )

        if not REGISTRATION_NUMBER_PATTERN.fullmatch(
            self.company_registration_number
        ):
            raise CompanyProfileValidationError(
                "Company Registration Number must use the format C 12345 "
                "(C, one space, and 5 to 8 digits)."
            )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> CompanyProfile:
        """Create a profile from untrusted mapping data using a strict schema."""

        expected_fields = set(_FIELD_LIMITS)
        supplied_fields = set(data)
        missing_fields = expected_fields - supplied_fields
        unexpected_fields = supplied_fields - expected_fields
        if missing_fields:
            raise CompanyProfileValidationError(
                "Company profile is missing required fields."
            )
        if unexpected_fields:
            raise CompanyProfileValidationError(
                "Company profile contains unsupported fields."
            )
        return cls(**{field_name: data[field_name] for field_name in _FIELD_LIMITS})

    def to_mapping(self) -> dict[str, str]:
        """Return the validated profile as JSON-compatible data."""

        return asdict(self)


def validate_company_profiles(
    profiles: Sequence[CompanyProfile],
) -> tuple[CompanyProfile, ...]:
    """Validate collection size, item types, and unique display names."""

    if len(profiles) > MAX_COMPANY_PROFILES:
        raise CompanyProfileValidationError(
            f"No more than {MAX_COMPANY_PROFILES} company profiles are allowed."
        )

    validated: list[CompanyProfile] = []
    display_names: set[str] = set()
    for profile in profiles:
        if not isinstance(profile, CompanyProfile):
            raise CompanyProfileValidationError(
                "Company profile collection contains an invalid item."
            )
        normalized_name = profile.display_name.casefold()
        if normalized_name in display_names:
            raise CompanyProfileValidationError(
                "Company profile display names must be unique."
            )
        display_names.add(normalized_name)
        validated.append(profile)
    return tuple(validated)


def _field_label(field_name: str) -> str:
    return field_name.replace("_", " ").title()
