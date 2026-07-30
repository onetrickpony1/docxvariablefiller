"""Tests for minimal, non-sensitive preference persistence."""

import json
from pathlib import Path

import pytest

from src.company_profile_storage import company_configuration_path
from src.settings import AppSettings, load_settings, save_settings
from src.settings import legacy_settings_file_path, settings_file_path


def test_settings_round_trip(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    expected = AppSettings(
        last_template_path=r"C:\Templates\Offer.docx",
        highlight_changes=True,
        leave_blanks_unchanged=True,
        rich_text_variable_indices=(0, 2),
    )

    save_settings(expected, settings_path)

    assert load_settings(settings_path) == expected


def test_settings_file_contains_only_approved_fields(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    save_settings(
        AppSettings(
            last_template_path=r"C:\Templates\Offer.docx",
            highlight_changes=True,
            leave_blanks_unchanged=False,
            rich_text_variable_indices=(1,),
        ),
        settings_path,
    )

    stored_data = json.loads(settings_path.read_text(encoding="utf-8"))

    assert set(stored_data) == {
        "last_template_path",
        "highlight_changes",
        "leave_blanks_unchanged",
        "rich_text_variable_indices",
    }
    assert "replacement" not in settings_path.read_text(encoding="utf-8").lower()
    assert "document_content" not in stored_data


def test_missing_settings_return_defaults(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "missing.json") == AppSettings()


def test_invalid_settings_return_defaults(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{not valid json", encoding="utf-8")

    assert load_settings(settings_path) == AppSettings()


def test_wrong_setting_types_are_ignored(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "last_template_path": 123,
                "highlight_changes": "yes",
                "leave_blanks_unchanged": None,
                "rich_text_variable_indices": ["zero", -1, True],
            }
        ),
        encoding="utf-8",
    )

    assert load_settings(settings_path) == AppSettings()


def test_valid_rich_text_indices_are_loaded(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "rich_text_variable_indices": [0, 3],
            }
        ),
        encoding="utf-8",
    )

    assert load_settings(settings_path).rich_text_variable_indices == (0, 3)


def test_atomic_save_leaves_no_temporary_file(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"

    save_settings(AppSettings(highlight_changes=True), settings_path)

    assert settings_path.exists()
    assert list(tmp_path.glob(".settings-*.tmp")) == []


def test_settings_and_companies_share_application_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))

    assert settings_file_path().parent == company_configuration_path().parent
    assert settings_file_path().parent.name == "DocumentTemplateFiller"


def test_legacy_local_settings_are_migrated_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roaming_directory = tmp_path / "Roaming"
    local_directory = tmp_path / "Local"
    monkeypatch.setenv("APPDATA", str(roaming_directory))
    monkeypatch.setenv("LOCALAPPDATA", str(local_directory))
    expected = AppSettings(
        last_template_path=r"C:\Templates\Offer.docx",
        highlight_changes=True,
        rich_text_variable_indices=(1,),
    )
    legacy_path = legacy_settings_file_path()
    save_settings(expected, legacy_path)

    loaded = load_settings()

    assert loaded == expected
    assert settings_file_path().exists()
    assert not legacy_path.exists()
    assert load_settings() == expected
