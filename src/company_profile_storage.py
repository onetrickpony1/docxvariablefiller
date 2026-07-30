"""Versioned, defensive JSON persistence for Company Profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import secrets
from tempfile import NamedTemporaryFile
from datetime import datetime, timezone
from typing import Any

from .company_profile import CompanyProfile, validate_company_profiles
from .exceptions import (
    CompanyConfigurationError,
    CompanyProfileValidationError,
)


COMPANY_CONFIGURATION_VERSION = 2
APPLICATION_DATA_DIRECTORY = "DocumentTemplateFiller"
COMPANY_CONFIGURATION_FILENAME = "companies.json"
MAX_CONFIGURATION_BYTES = 1_048_576


@dataclass(frozen=True)
class CompanyConfigurationIssue:
    """A safe load warning plus session-only technical context."""

    code: str
    user_message: str
    technical_error: Exception | None = field(
        default=None,
        repr=False,
        compare=False,
    )


@dataclass(frozen=True)
class CompanyProfilesLoadResult:
    """Validated profiles and any issue encountered while loading them."""

    profiles: tuple[CompanyProfile, ...]
    issue: CompanyConfigurationIssue | None = None


class _DuplicateJsonKeyError(ValueError):
    """Raised when untrusted JSON contains duplicate object keys."""


def company_configuration_path() -> Path:
    """Return the fixed per-user Company Profiles configuration path."""

    roaming_app_data = os.environ.get("APPDATA")
    if roaming_app_data:
        base_directory = Path(roaming_app_data)
    else:
        base_directory = Path.home() / "AppData" / "Roaming"
    return (
        base_directory
        / APPLICATION_DATA_DIRECTORY
        / COMPANY_CONFIGURATION_FILENAME
    )


def load_company_profiles(
    path: Path | None = None,
) -> CompanyProfilesLoadResult:
    """Load and validate profiles, safely recovering to an empty collection.

    The optional path is intended for tests and controlled deployments. Runtime
    GUI code uses the fixed path returned by :func:`company_configuration_path`.
    Corrupted data is never executed, used partially, or silently accepted.
    """

    configuration_path = path or company_configuration_path()
    try:
        if not configuration_path.exists():
            return CompanyProfilesLoadResult(())
        if configuration_path.is_symlink() or not configuration_path.is_file():
            return _load_issue(
                "unsafe_file",
                "The Company Profiles file is not a safe regular file.",
            )
        if configuration_path.stat().st_size > MAX_CONFIGURATION_BYTES:
            return _load_issue(
                "file_too_large",
                "The Company Profiles file is too large and was not loaded.",
            )

        raw_text = configuration_path.read_text(encoding="utf-8")
        raw_data = json.loads(
            raw_text,
            object_pairs_hook=_reject_duplicate_keys,
        )
        profiles = _parse_configuration(raw_data)
        return CompanyProfilesLoadResult(profiles)
    except OSError as error:
        return _load_issue(
            "inaccessible",
            "Company Profiles could not be read. No saved companies were loaded.",
            error,
        )
    except (UnicodeError, json.JSONDecodeError, _DuplicateJsonKeyError) as error:
        return _load_issue(
            "corrupted",
            "The Company Profiles file is corrupted. No saved companies were loaded.",
            error,
        )
    except CompanyProfileValidationError as error:
        return _load_issue(
            "invalid_data",
            "The Company Profiles file contains invalid data. "
            "No saved companies were loaded.",
            error,
        )


def save_company_profiles(
    profiles: tuple[CompanyProfile, ...],
    path: Path | None = None,
) -> None:
    """Validate and atomically save Company Profiles as versioned UTF-8 JSON."""

    validated_profiles = validate_company_profiles(profiles)
    configuration_path = path or company_configuration_path()
    payload = {
        "version": COMPANY_CONFIGURATION_VERSION,
        "profiles": [profile.to_mapping() for profile in validated_profiles],
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    if len(serialized.encode("utf-8")) > MAX_CONFIGURATION_BYTES:
        raise CompanyConfigurationError(
            "Company Profiles data is too large to save safely."
        )

    temporary_path: Path | None = None
    try:
        configuration_path.parent.mkdir(parents=True, exist_ok=True)
        if configuration_path.exists() and configuration_path.is_symlink():
            raise CompanyConfigurationError(
                "The Company Profiles file is not a safe regular file."
            )
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{configuration_path.stem}-",
            suffix=".tmp",
            dir=configuration_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, configuration_path)
        temporary_path = None
    except CompanyConfigurationError:
        raise
    except OSError as error:
        raise CompanyConfigurationError(
            "Company Profiles could not be saved safely."
        ) from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def quarantine_company_configuration(
    path: Path | None = None,
) -> str | None:
    """Move an invalid configuration to a uniquely named recovery copy.

    This operation is intended only after explicit user confirmation. The
    returned value is the backup filename, not an internal absolute path.
    """

    configuration_path = path or company_configuration_path()
    try:
        if not configuration_path.exists():
            return None
        if configuration_path.is_symlink() or not configuration_path.is_file():
            raise CompanyConfigurationError(
                "The Company Profiles file is not a safe regular file."
            )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for _attempt in range(10):
            token = secrets.token_hex(4)
            backup_name = (
                f"{configuration_path.stem}.corrupt-{timestamp}-{token}"
                f"{configuration_path.suffix}"
            )
            backup_path = configuration_path.with_name(backup_name)
            if backup_path.exists():
                continue
            configuration_path.rename(backup_path)
            return backup_name
        raise CompanyConfigurationError(
            "A unique Company Profiles recovery filename could not be created."
        )
    except CompanyConfigurationError:
        raise
    except OSError as error:
        raise CompanyConfigurationError(
            "The corrupted Company Profiles file could not be preserved safely."
        ) from error


def _parse_configuration(raw_data: Any) -> tuple[CompanyProfile, ...]:
    if not isinstance(raw_data, dict):
        raise CompanyProfileValidationError(
            "Company Profiles configuration must be an object."
        )
    if set(raw_data) != {"version", "profiles"}:
        raise CompanyProfileValidationError(
            "Company Profiles configuration has an invalid schema."
        )
    if type(raw_data["version"]) is not int:
        raise CompanyProfileValidationError(
            "Company Profiles configuration version is invalid."
        )
    version = raw_data["version"]
    if version not in {1, COMPANY_CONFIGURATION_VERSION}:
        raise CompanyProfileValidationError(
            "Company Profiles configuration version is not supported."
        )
    raw_profiles = raw_data["profiles"]
    if not isinstance(raw_profiles, list):
        raise CompanyProfileValidationError(
            "Company Profiles configuration list is invalid."
        )

    profiles: list[CompanyProfile] = []
    for raw_profile in raw_profiles:
        if not isinstance(raw_profile, dict):
            raise CompanyProfileValidationError(
                "Company Profiles configuration contains an invalid profile."
            )
        profile_data = (
            _migrate_version_one_profile(raw_profile)
            if version == 1
            else raw_profile
        )
        profiles.append(CompanyProfile.from_mapping(profile_data))
    return validate_company_profiles(profiles)


def _migrate_version_one_profile(
    raw_profile: dict[str, Any],
) -> dict[str, Any]:
    """Convert one validated-schema candidate from version 1 to version 2."""

    expected_fields = {
        "display_name",
        "company_name",
        "company_registration_number",
        "company_address_line_1",
        "company_address_line_2",
        "company_postcode",
        "company_country",
        "company_director",
    }
    if set(raw_profile) != expected_fields:
        raise CompanyProfileValidationError(
            "Legacy Company Profile configuration has an invalid schema."
        )
    migrated = dict(raw_profile)
    first_director = migrated.pop("company_director")
    migrated["company_director_1"] = first_director
    migrated["company_director_2"] = ""
    migrated["company_director_3"] = ""
    return migrated


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_issue(
    code: str,
    user_message: str,
    technical_error: Exception | None = None,
) -> CompanyProfilesLoadResult:
    return CompanyProfilesLoadResult(
        (),
        CompanyConfigurationIssue(
            code=code,
            user_message=user_message,
            technical_error=technical_error,
        ),
    )
