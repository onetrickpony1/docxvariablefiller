"""Pure collection operations for Company Profile management."""

from __future__ import annotations

from collections.abc import Sequence

from .company_profile import CompanyProfile, validate_company_profiles
from .exceptions import CompanyProfileValidationError


def add_company_profile(
    profiles: Sequence[CompanyProfile],
    profile: CompanyProfile,
) -> tuple[CompanyProfile, ...]:
    """Return a validated collection containing *profile*."""

    return validate_company_profiles((*profiles, profile))


def edit_company_profile(
    profiles: Sequence[CompanyProfile],
    index: int,
    replacement: CompanyProfile,
) -> tuple[CompanyProfile, ...]:
    """Return a validated collection with one profile replaced."""

    _validate_index(profiles, index)
    updated = list(profiles)
    updated[index] = replacement
    return validate_company_profiles(updated)


def delete_company_profile(
    profiles: Sequence[CompanyProfile],
    index: int,
) -> tuple[CompanyProfile, ...]:
    """Return a validated collection without the selected profile."""

    _validate_index(profiles, index)
    updated = list(profiles)
    del updated[index]
    return validate_company_profiles(updated)


def merge_company_profiles(
    existing_profiles: Sequence[CompanyProfile],
    imported_profiles: Sequence[CompanyProfile],
) -> tuple[CompanyProfile, ...]:
    """Return one validated collection containing existing and imported profiles.

    Duplicate display names, invalid objects, and collection-size violations
    reject the complete merge. Existing profiles are never silently replaced.
    """

    return validate_company_profiles(
        (*existing_profiles, *imported_profiles)
    )


def _validate_index(
    profiles: Sequence[CompanyProfile],
    index: int,
) -> None:
    if type(index) is not int or not 0 <= index < len(profiles):
        raise CompanyProfileValidationError(
            "Select a valid company profile and try again."
        )
