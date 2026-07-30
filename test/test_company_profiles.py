"""Tests for Company Profile validation, mapping, and persistence."""

import json
from pathlib import Path

import pytest

from src.company_placeholder_mapping import (
    COMPANY_PLACEHOLDER_NAMES,
    company_placeholder_values,
)
from src.company_profile import CompanyProfile, validate_company_profiles
from src.company_profile_storage import (
    COMPANY_CONFIGURATION_VERSION,
    MAX_CONFIGURATION_BYTES,
    load_company_profiles,
    save_company_profiles,
)
from src.exceptions import (
    CompanyConfigurationError,
    CompanyProfileValidationError,
)


def _profile(
    *,
    display_name: str = "Example Malta",
    company_name: str = "Example Company Limited",
    registration_number: str = "C 12345",
) -> CompanyProfile:
    return CompanyProfile(
        display_name=display_name,
        company_name=company_name,
        company_registration_number=registration_number,
        company_address_line_1="1 Example Street",
        company_address_line_2="Level 2",
        company_postcode="VLT 1000",
        company_country="Malta",
        company_director_1="Alex Example",
        company_director_2="Blair Example",
        company_director_3="Casey Example",
    )


def test_profile_trims_surrounding_whitespace() -> None:
    profile = _profile(
        display_name="  Example Malta  ",
        company_name="  Example Company Limited ",
    )

    assert profile.display_name == "Example Malta"
    assert profile.company_name == "Example Company Limited"


@pytest.mark.parametrize(
    "field_name",
    [
        "display_name",
        "company_name",
        "company_registration_number",
        "company_address_line_1",
        "company_address_line_2",
        "company_postcode",
        "company_country",
        "company_director_1",
    ],
)
def test_required_profile_fields_cannot_be_empty(field_name: str) -> None:
    data = _profile().to_mapping()
    data[field_name] = "  "

    with pytest.raises(CompanyProfileValidationError, match="required"):
        CompanyProfile.from_mapping(data)


@pytest.mark.parametrize(
    "field_name",
    [
        "company_director_2",
        "company_director_3",
    ],
)
def test_optional_profile_fields_may_be_empty(field_name: str) -> None:
    data = _profile().to_mapping()
    data[field_name] = " "

    profile = CompanyProfile.from_mapping(data)

    assert getattr(profile, field_name) == ""


@pytest.mark.parametrize(
    "registration_number",
    ["12345", "C12345", "C 1234", "C 123456789", "c 12345", "C ABCDE"],
)
def test_invalid_registration_number_is_rejected(
    registration_number: str,
) -> None:
    with pytest.raises(CompanyProfileValidationError, match="format C 12345"):
        _profile(registration_number=registration_number)


def test_control_characters_are_rejected() -> None:
    data = _profile().to_mapping()
    data["company_director_1"] = "Alex\nExample"

    with pytest.raises(CompanyProfileValidationError, match="control"):
        CompanyProfile.from_mapping(data)


def test_display_names_must_be_unique_case_insensitively() -> None:
    with pytest.raises(CompanyProfileValidationError, match="unique"):
        validate_company_profiles(
            (
                _profile(display_name="Example"),
                _profile(display_name="example"),
            )
        )


def test_company_placeholder_mapping_is_complete() -> None:
    values = company_placeholder_values(_profile())

    assert tuple(values) == COMPANY_PLACEHOLDER_NAMES
    assert values == {
        "Company Name": "Example Company Limited",
        "Company Registration Number": "C 12345",
        "Company Address Line 1": "1 Example Street",
        "Company Address Line 2": "Level 2",
        "Company Postcode": "VLT 1000",
        "Company Country": "Malta",
        "Company Director 1": "Alex Example",
        "Company Director 2": "Blair Example",
        "Company Director 3": "Casey Example",
        "Company Director": "Alex Example",
    }


def test_profiles_round_trip_through_versioned_json(tmp_path: Path) -> None:
    path = tmp_path / "companies.json"
    profiles = (_profile(),)

    save_company_profiles(profiles, path)
    result = load_company_profiles(path)
    raw_data = json.loads(path.read_text(encoding="utf-8"))

    assert result.issue is None
    assert result.profiles == profiles
    assert raw_data["version"] == COMPANY_CONFIGURATION_VERSION


def test_version_one_profile_migrates_director_to_director_one(
    tmp_path: Path,
) -> None:
    path = tmp_path / "companies.json"
    legacy_profile = _profile().to_mapping()
    legacy_profile["company_director"] = legacy_profile.pop(
        "company_director_1"
    )
    legacy_profile.pop("company_director_2")
    legacy_profile.pop("company_director_3")
    path.write_text(
        json.dumps({"version": 1, "profiles": [legacy_profile]}),
        encoding="utf-8",
    )

    result = load_company_profiles(path)

    assert result.issue is None
    assert result.profiles[0].company_director_1 == "Alex Example"
    assert result.profiles[0].company_director_2 == ""
    assert result.profiles[0].company_director_3 == ""

    save_company_profiles(result.profiles, path)
    saved_data = json.loads(path.read_text(encoding="utf-8"))
    assert saved_data["version"] == COMPANY_CONFIGURATION_VERSION
    assert "company_director" not in saved_data["profiles"][0]


def test_missing_configuration_recovers_to_empty_profiles(tmp_path: Path) -> None:
    result = load_company_profiles(tmp_path / "missing.json")

    assert result.profiles == ()
    assert result.issue is None


def test_corrupted_json_is_reported_and_not_used(tmp_path: Path) -> None:
    path = tmp_path / "companies.json"
    path.write_text("{invalid json", encoding="utf-8")

    result = load_company_profiles(path)

    assert result.profiles == ()
    assert result.issue is not None
    assert result.issue.code == "corrupted"
    assert result.issue.technical_error is not None


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "companies.json"
    path.write_text(
        '{"version": 1, "version": 1, "profiles": []}',
        encoding="utf-8",
    )

    result = load_company_profiles(path)

    assert result.issue is not None
    assert result.issue.code == "corrupted"


def test_unsupported_configuration_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "companies.json"
    path.write_text(
        json.dumps({"version": 99, "profiles": []}),
        encoding="utf-8",
    )

    result = load_company_profiles(path)

    assert result.issue is not None
    assert result.issue.code == "invalid_data"


def test_unknown_profile_fields_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "companies.json"
    profile_data = _profile().to_mapping()
    profile_data["unexpected"] = "untrusted"
    path.write_text(
        json.dumps({"version": 1, "profiles": [profile_data]}),
        encoding="utf-8",
    )

    result = load_company_profiles(path)

    assert result.issue is not None
    assert result.issue.code == "invalid_data"


def test_oversized_configuration_is_rejected_before_reading(
    tmp_path: Path,
) -> None:
    path = tmp_path / "companies.json"
    path.write_bytes(b" " * (MAX_CONFIGURATION_BYTES + 1))

    result = load_company_profiles(path)

    assert result.profiles == ()
    assert result.issue is not None
    assert result.issue.code == "file_too_large"


def test_invalid_utf8_is_reported_and_not_used(tmp_path: Path) -> None:
    path = tmp_path / "companies.json"
    path.write_bytes(b"\xff\xfe\x00")

    result = load_company_profiles(path)

    assert result.profiles == ()
    assert result.issue is not None
    assert result.issue.code == "corrupted"


def test_duplicate_display_names_are_rejected_before_save(
    tmp_path: Path,
) -> None:
    path = tmp_path / "companies.json"

    with pytest.raises(CompanyProfileValidationError, match="unique"):
        save_company_profiles(
            (
                _profile(display_name="Example"),
                _profile(display_name="EXAMPLE"),
            ),
            path,
        )

    assert not path.exists()


def test_atomic_save_leaves_no_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / "companies.json"

    save_company_profiles((_profile(),), path)

    assert path.exists()
    assert list(tmp_path.glob(".companies-*.tmp")) == []


def test_failed_atomic_replace_preserves_existing_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "companies.json"
    original_profiles = (_profile(),)
    save_company_profiles(original_profiles, path)
    original_bytes = path.read_bytes()

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("simulated atomic replacement failure")

    monkeypatch.setattr(
        "src.company_profile_storage.os.replace",
        fail_replace,
    )

    with pytest.raises(CompanyConfigurationError, match="saved safely"):
        save_company_profiles(
            (
                _profile(
                    display_name="Replacement",
                    company_name="Replacement Company Limited",
                    registration_number="C 54321",
                ),
            ),
            path,
        )

    assert path.read_bytes() == original_bytes
    assert load_company_profiles(path).profiles == original_profiles
    assert list(tmp_path.glob(".companies-*.tmp")) == []
