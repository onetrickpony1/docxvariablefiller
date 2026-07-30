"""Map validated Company Profiles to generic template replacement values."""

from __future__ import annotations

from collections.abc import Iterable

from .company_profile import CompanyProfile


COMPANY_PLACEHOLDER_NAMES = (
    "Company Name",
    "Company Registration Number",
    "Company Address Line 1",
    "Company Address Line 2",
    "Company Postcode",
    "Company Country",
    "Company Director 1",
    "Company Director 2",
    "Company Director 3",
    "Company Director",
)
_COMPANY_PLACEHOLDER_NAME_SET = frozenset(COMPANY_PLACEHOLDER_NAMES)


def company_placeholder_values(profile: CompanyProfile) -> dict[str, str]:
    """Return generic placeholder/value pairs for a validated company."""

    return {
        "Company Name": profile.company_name,
        "Company Registration Number": profile.company_registration_number,
        "Company Address Line 1": profile.company_address_line_1,
        "Company Address Line 2": profile.company_address_line_2,
        "Company Postcode": profile.company_postcode,
        "Company Country": profile.company_country,
        "Company Director 1": profile.company_director_1,
        "Company Director 2": profile.company_director_2,
        "Company Director 3": profile.company_director_3,
        "Company Director": profile.company_director_1,
    }


def detected_company_placeholder_names(
    variable_names: Iterable[str],
) -> tuple[str, ...]:
    """Return detected company placeholders in stable company-field order."""

    detected_names = set(variable_names)
    return tuple(
        placeholder_name
        for placeholder_name in COMPANY_PLACEHOLDER_NAMES
        if placeholder_name in detected_names
    )
