"""Tests for Company Profile CRUD operations and corruption recovery."""

from pathlib import Path

import pytest

from src.company_profile import CompanyProfile
from src.company_profile_operations import (
    add_company_profile,
    delete_company_profile,
    edit_company_profile,
    merge_company_profiles,
)
from src.company_profile_storage import (
    load_company_profiles,
    quarantine_company_configuration,
    save_company_profiles,
)
from src.exceptions import CompanyProfileValidationError


def _profile(display_name: str, registration: str) -> CompanyProfile:
    return CompanyProfile(
        display_name=display_name,
        company_name=f"{display_name} Limited",
        company_registration_number=registration,
        company_address_line_1="1 Example Street",
        company_address_line_2="Level 2",
        company_postcode="VLT 1000",
        company_country="Malta",
        company_director_1="Alex Example",
        company_director_2="",
        company_director_3="",
    )


def test_add_company_profile() -> None:
    first = _profile("First", "C 12345")
    second = _profile("Second", "C 12346")

    result = add_company_profile((first,), second)

    assert result == (first, second)


def test_add_rejects_duplicate_display_name() -> None:
    first = _profile("Example", "C 12345")
    duplicate = _profile("EXAMPLE", "C 12346")

    with pytest.raises(CompanyProfileValidationError, match="unique"):
        add_company_profile((first,), duplicate)


def test_edit_company_profile() -> None:
    first = _profile("First", "C 12345")
    second = _profile("Second", "C 12346")
    replacement = _profile("Updated", "C 12347")

    result = edit_company_profile((first, second), 0, replacement)

    assert result == (replacement, second)


def test_edit_rejects_duplicate_display_name() -> None:
    first = _profile("First", "C 12345")
    second = _profile("Second", "C 12346")
    duplicate = _profile("second", "C 12347")

    with pytest.raises(CompanyProfileValidationError, match="unique"):
        edit_company_profile((first, second), 0, duplicate)


def test_delete_company_profile() -> None:
    first = _profile("First", "C 12345")
    second = _profile("Second", "C 12346")

    result = delete_company_profile((first, second), 0)

    assert result == (second,)


def test_import_merge_retains_existing_and_appends_imported_profiles() -> None:
    existing = _profile("Existing", "C 12345")
    imported = _profile("Imported", "C 12346")

    result = merge_company_profiles((existing,), (imported,))

    assert result == (existing, imported)


def test_import_merge_rejects_duplicate_display_names_atomically() -> None:
    existing = _profile("Existing", "C 12345")
    duplicate = _profile("EXISTING", "C 12346")

    with pytest.raises(CompanyProfileValidationError, match="unique"):
        merge_company_profiles((existing,), (duplicate,))


@pytest.mark.parametrize("invalid_index", [-1, 1, True])
def test_operations_reject_invalid_selection(invalid_index: int) -> None:
    with pytest.raises(CompanyProfileValidationError, match="Select"):
        delete_company_profile(
            (_profile("First", "C 12345"),),
            invalid_index,
        )


def test_quarantine_preserves_corrupted_file(tmp_path: Path) -> None:
    path = tmp_path / "companies.json"
    corrupted_bytes = b"{corrupted"
    path.write_bytes(corrupted_bytes)

    backup_name = quarantine_company_configuration(path)

    assert backup_name is not None
    assert not path.exists()
    backup_path = tmp_path / backup_name
    assert backup_path.parent == tmp_path
    assert backup_path.read_bytes() == corrupted_bytes


def test_recovery_can_create_new_empty_configuration(tmp_path: Path) -> None:
    path = tmp_path / "companies.json"
    path.write_bytes(b"{corrupted")

    quarantine_company_configuration(path)
    save_company_profiles((), path)
    result = load_company_profiles(path)

    assert result.issue is None
    assert result.profiles == ()
    assert len(tuple(tmp_path.glob("companies.corrupt-*.json"))) == 1


def test_quarantine_missing_configuration_is_safe(tmp_path: Path) -> None:
    path = tmp_path / "companies.json"

    assert quarantine_company_configuration(path) is None


def test_complete_crud_cycle_persists_across_reloads(tmp_path: Path) -> None:
    path = tmp_path / "companies.json"
    first = _profile("First", "C 12345")
    second = _profile("Second", "C 12346")

    profiles = add_company_profile((), first)
    save_company_profiles(profiles, path)
    assert load_company_profiles(path).profiles == (first,)

    profiles = add_company_profile(load_company_profiles(path).profiles, second)
    save_company_profiles(profiles, path)
    assert load_company_profiles(path).profiles == (first, second)

    updated_first = _profile("First Updated", "C 12347")
    profiles = edit_company_profile(
        load_company_profiles(path).profiles,
        0,
        updated_first,
    )
    save_company_profiles(profiles, path)
    assert load_company_profiles(path).profiles == (updated_first, second)

    profiles = delete_company_profile(load_company_profiles(path).profiles, 1)
    save_company_profiles(profiles, path)
    assert load_company_profiles(path).profiles == (updated_first,)
