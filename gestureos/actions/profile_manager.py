"""ProfileManager — load, validate, save, and resolve gesture-to-action profiles.

Implements TRD §3.14 (ProfileManager). Each profile is a JSON file
containing gesture-to-action mappings alongside metadata (id, name,
is_default).

CP-5: the manager reads profiles from a configurable directory,
validates structure on load, and provides access to the current
(default or active) profile.

Thread safety: the manager is safe for read operations after
construction. Writes (save) are not concurrent-safe.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from models.data_models import Profile


logger = logging.getLogger('gestureos')

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

#: Default subdirectory name under the project root.
DEFAULT_PROFILES_DIR: str = 'profiles'

#: Required keys in every profile JSON file.
_PROFILE_REQUIRED_KEYS: set[str] = {'id', 'name', 'mappings'}

#: Required keys in every mapping entry within a profile.
_MAPPING_REQUIRED_KEYS: set[str] = {'gesture', 'action_type', 'params'}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ProfileError(Exception):
    """Base exception for profile-related errors."""


class ProfileValidationError(ProfileError):
    """Raised when a profile fails structural validation."""


class ProfileNotFoundError(ProfileError):
    """Raised when a requested profile does not exist."""


# ---------------------------------------------------------------------------
# ProfileManager
# ---------------------------------------------------------------------------

class ProfileManager:
    """Load, validate, save, and resolve gesture-to-action profiles.

    Usage::

        mgr = ProfileManager(profiles_dir='./profiles')
        profiles = mgr.load_all()
        default = mgr.get_default()
        if default:
            action_mapping = mgr.resolve(gesture_name, default)
    """

    def __init__(self, profiles_dir: str | None = None) -> None:
        """Initialise the profile manager.

        Args:
            profiles_dir: Path to the directory containing profile JSON
                files.  When ``None``, defaults to ``profiles/`` relative
                to the current working directory.
        """
        self._profiles_dir: str = profiles_dir or DEFAULT_PROFILES_DIR
        self._cache: dict[str, Profile] | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def profiles_dir(self) -> str:
        """The directory from which profiles are loaded."""
        return self._profiles_dir

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load_all(self) -> list[Profile]:
        """Load every profile JSON file in ``profiles_dir``.

        Returns:
            A list of validated ``Profile`` objects.  Malformed files
            are logged and skipped (the method never raises).
        """
        profiles: list[Profile] = []
        if not os.path.isdir(self._profiles_dir):
            logger.info(
                'profile_manager',
                extra={'extras': {
                    'event': 'profiles_dir_not_found',
                    'path': self._profiles_dir,
                    'message': 'No profiles directory — returning empty list',
                }},
            )
            self._cache = {}
            return profiles

        for filename in sorted(os.listdir(self._profiles_dir)):
            if not filename.endswith('.json'):
                continue
            filepath = os.path.join(self._profiles_dir, filename)
            try:
                profile = self._load_single(filepath)
                if profile is not None:
                    profiles.append(profile)
            except ProfileValidationError as exc:
                logger.warning(
                    'profile_manager',
                    extra={'extras': {
                        'event': 'profile_validation_failed',
                        'file': filename,
                        'error': str(exc),
                    }},
                )

        self._cache = {p.id: p for p in profiles}
        return profiles

    def load(self, profile_id: str) -> Profile | None:
        """Load a specific profile by its ``id`` field.

        Scans ``profiles_dir`` for a JSON file whose ``id`` matches.
        Results are cached after the first call to ``load_all()``.

        Args:
            profile_id: The profile identifier to look up.

        Returns:
            The matching ``Profile``, or ``None``.
        """
        if self._cache is None:
            self.load_all()
        if self._cache is None:
            return None
        return self._cache.get(profile_id)

    # ------------------------------------------------------------------
    # Default profile
    # ------------------------------------------------------------------

    def get_default(self) -> Profile | None:
        """Return the profile marked ``is_default=True``.

        If no profile is explicitly marked default, the first profile
        alphabetically is returned as a fallback.  Returns ``None``
        when no profiles exist.
        """
        if self._cache is None:
            self.load_all()
        if not self._cache:
            return None
        for profile in self._cache.values():
            if profile.is_default:
                return profile
        # Fallback: return the first profile (sorted by id).
        return next(iter(self._cache.values()))

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self, profile: Profile) -> bool:
        """Save a profile to a JSON file in ``profiles_dir``.

        The filename is derived from the profile's ``id``:
        ``{profiles_dir}/{id}.json``.

        Args:
            profile: The ``Profile`` to persist.

        Returns:
            ``True`` on success, ``False`` on failure (logged).
        """
        errors = self.validate(profile)
        if errors:
            logger.error(
                'profile_manager',
                extra={'extras': {
                    'event': 'save_validation_failed',
                    'profile_id': profile.id,
                    'errors': errors,
                }},
            )
            return False

        filepath = os.path.join(self._profiles_dir, f"{profile.id}.json")
        try:
            os.makedirs(self._profiles_dir, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(
                    {
                        'id': profile.id,
                        'name': profile.name,
                        'is_default': profile.is_default,
                        'mappings': profile.mappings,
                    },
                    f,
                    indent=2,
                )
        except OSError as exc:
            logger.error(
                'profile_manager',
                extra={'extras': {
                    'event': 'save_io_error',
                    'filepath': filepath,
                    'error': str(exc),
                }},
            )
            return False

        # Update in-memory cache.
        if self._cache is None:
            self._cache = {}
        self._cache[profile.id] = profile
        return True

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate(profile: Profile) -> list[str]:
        """Validate a ``Profile`` object's structure.

        Returns:
            A list of human-readable error strings.  An empty list
            means the profile is valid.
        """
        errors: list[str] = []

        if not profile.id or not isinstance(profile.id, str):
            errors.append('Profile id must be a non-empty string')
        if not profile.name or not isinstance(profile.name, str):
            errors.append('Profile name must be a non-empty string')
        if not isinstance(profile.mappings, list):
            errors.append('Profile mappings must be a list')
            return errors

        for i, mapping in enumerate(profile.mappings):
            if not isinstance(mapping, dict):
                errors.append(f'Mapping at index {i} must be a dict')
                continue
            missing = _MAPPING_REQUIRED_KEYS - set(mapping.keys())
            if missing:
                errors.append(
                    f'Mapping at index {i} missing keys: '
                    f'{sorted(missing)}'
                )
            if not isinstance(mapping.get('params'), dict):
                errors.append(
                    f'Mapping at index {i}: params must be a dict'
                )

        return errors

    # ------------------------------------------------------------------
    # Resolve
    # ------------------------------------------------------------------

    @staticmethod
    def resolve(gesture_name: str, profile: Profile) -> dict[str, Any] | None:
        """Find the mapping entry for ``gesture_name`` within a profile.

        Args:
            gesture_name: The gesture name to look up.
            profile: The ``Profile`` to search.

        Returns:
            The matching mapping dict, or ``None``.
        """
        for mapping in profile.mappings:
            if mapping.get('gesture') == gesture_name:
                return mapping
        return None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @staticmethod
    def create_default(
        name: str = 'Default Profile',
    ) -> Profile:
        """Create a ``Profile`` populated with the built-in default
        gesture-to-action mappings."""
        from actions.router import DEFAULT_MAPPINGS

        return Profile(
            id='default',
            name=name,
            is_default=True,
            mappings=list(DEFAULT_MAPPINGS),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_single(self, filepath: str) -> Profile | None:
        """Load and validate a single profile JSON file.

        Raises ``ProfileValidationError`` when the file content is
        structurally invalid.
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data: dict[str, Any] = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                'profile_manager',
                extra={'extras': {
                    'event': 'profile_load_failed',
                    'filepath': filepath,
                    'error': str(exc),
                }},
            )
            return None

        # Validate top-level keys.
        missing = _PROFILE_REQUIRED_KEYS - set(data.keys())
        if missing:
            raise ProfileValidationError(
                f"Missing required keys: {sorted(missing)}"
            )

        if not isinstance(data['id'], str) or not data['id']:
            raise ProfileValidationError("'id' must be a non-empty string")
        if not isinstance(data['name'], str) or not data['name']:
            raise ProfileValidationError("'name' must be a non-empty string")
        if not isinstance(data['mappings'], list):
            raise ProfileValidationError("'mappings' must be a list")

        # Validate each mapping entry.
        for i, mapping in enumerate(data['mappings']):
            if not isinstance(mapping, dict):
                raise ProfileValidationError(
                    f"Mapping at index {i} must be a dict"
                )
            m_missing = _MAPPING_REQUIRED_KEYS - set(mapping.keys())
            if m_missing:
                raise ProfileValidationError(
                    f"Mapping at index {i} missing keys: "
                    f"{sorted(m_missing)}"
                )
            if not isinstance(mapping.get('params'), dict):
                raise ProfileValidationError(
                    f"Mapping at index {i}: 'params' must be a dict"
                )

        return Profile(
            id=data['id'],
            name=data['name'],
            is_default=bool(data.get('is_default', False)),
            mappings=list(data['mappings']),
        )
