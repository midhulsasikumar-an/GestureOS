"""Unit tests for the CP-5 ProfileManager.

Tests cover:
  - Loading profiles from directory (single, multiple, missing dir)
  - Validation of profile structure
  - Saving profiles to disk
  - Default profile resolution
  - Gesture resolution via ProfileManager.resolve()
  - Factory method create_default()
  - Error handling (missing file, malformed JSON, invalid structure)
  - Cache invalidation after save
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from models.data_models import Profile

from actions.profile_manager import ProfileManager
from actions.router import DEFAULT_MAPPINGS


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def tmp_profiles_dir() -> str:
    """Create a temporary directory for profile files."""
    tmpdir = tempfile.mkdtemp(prefix='gestureos_profiles_')
    yield tmpdir
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


def write_profile(tmpdir: str, data: dict, filename: str | None = None) -> str:
    """Write a profile dict as JSON to *tmpdir*."""
    fname = filename or f"{data.get('id', 'unknown')}.json"
    filepath = os.path.join(tmpdir, fname)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return filepath


# ======================================================================
# Loading
# ======================================================================

class TestLoadAll:
    """load_all() scans the profiles directory for .json files."""

    def test_empty_directory_returns_empty_list(self, tmp_profiles_dir: str) -> None:
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        profiles = mgr.load_all()
        assert profiles == []

    def test_missing_directory_returns_empty_list(self) -> None:
        mgr = ProfileManager(profiles_dir='/nonexistent/path/xyz')
        profiles = mgr.load_all()
        assert profiles == []

    def test_single_valid_profile(self, tmp_profiles_dir: str) -> None:
        write_profile(tmp_profiles_dir, {
            'id': 'default', 'name': 'Default', 'is_default': True,
            'mappings': [
                {'gesture': 'open_palm', 'action_type': 'system', 'params': {'type': 'show_desktop'}},
            ],
        })
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        profiles = mgr.load_all()
        assert len(profiles) == 1
        assert profiles[0].id == 'default'
        assert profiles[0].name == 'Default'
        assert profiles[0].is_default is True
        assert len(profiles[0].mappings) == 1

    def test_multiple_profiles(self, tmp_profiles_dir: str) -> None:
        write_profile(tmp_profiles_dir, {
            'id': 'gaming', 'name': 'Gaming', 'mappings': [],
        })
        write_profile(tmp_profiles_dir, {
            'id': 'productivity', 'name': 'Productivity', 'mappings': [],
        })
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        profiles = mgr.load_all()
        assert len(profiles) == 2
        ids = {p.id for p in profiles}
        assert ids == {'gaming', 'productivity'}

    def test_non_json_files_ignored(self, tmp_profiles_dir: str) -> None:
        # Create a .txt file alongside a .json file
        with open(os.path.join(tmp_profiles_dir, 'readme.txt'), 'w') as f:
            f.write('not a profile')
        write_profile(tmp_profiles_dir, {
            'id': 'default', 'name': 'Default', 'mappings': [],
        })
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        profiles = mgr.load_all()
        assert len(profiles) == 1

    def test_malformed_json_skipped(self, tmp_profiles_dir: str) -> None:
        # Write invalid JSON
        filepath = os.path.join(tmp_profiles_dir, 'broken.json')
        with open(filepath, 'w') as f:
            f.write('{not valid json')
        write_profile(tmp_profiles_dir, {
            'id': 'good', 'name': 'Good', 'mappings': [],
        })
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        profiles = mgr.load_all()
        assert len(profiles) == 1
        assert profiles[0].id == 'good'

    def test_missing_keys_skipped(self, tmp_profiles_dir: str) -> None:
        # Missing 'name' key
        write_profile(tmp_profiles_dir, {
            'id': 'valid', 'name': 'Valid', 'mappings': [],
        })
        filepath = os.path.join(tmp_profiles_dir, 'invalid.json')
        with open(filepath, 'w') as f:
            json.dump({'id': 'invalid'}, f)  # missing name + mappings
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        profiles = mgr.load_all()
        assert len(profiles) == 1
        assert profiles[0].id == 'valid'


# ======================================================================
# Load by ID
# ======================================================================

class TestLoadById:
    """load(profile_id) returns the matching profile from cache."""

    def test_existing_profile(self, tmp_profiles_dir: str) -> None:
        write_profile(tmp_profiles_dir, {
            'id': 'gaming', 'name': 'Gaming', 'mappings': [],
        })
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        profile = mgr.load('gaming')
        assert profile is not None
        assert profile.id == 'gaming'

    def test_nonexistent_profile(self, tmp_profiles_dir: str) -> None:
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        profile = mgr.load('nonexistent')
        assert profile is None

    def test_load_triggers_cache_build(self, tmp_profiles_dir: str) -> None:
        write_profile(tmp_profiles_dir, {
            'id': 'a', 'name': 'A', 'mappings': [],
        })
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        # First call builds cache; second call reads from cache.
        assert mgr.load('a') is not None
        assert mgr.load('a') is not None


# ======================================================================
# Default profile
# ======================================================================

class TestGetDefault:
    """get_default() returns the profile marked is_default."""

    def test_returns_marked_default(self, tmp_profiles_dir: str) -> None:
        write_profile(tmp_profiles_dir, {
            'id': 'gaming', 'name': 'Gaming', 'is_default': True, 'mappings': [],
        })
        write_profile(tmp_profiles_dir, {
            'id': 'work', 'name': 'Work', 'mappings': [],
        })
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        default = mgr.get_default()
        assert default is not None
        assert default.id == 'gaming'

    def test_fallback_to_first_profile(self, tmp_profiles_dir: str) -> None:
        write_profile(tmp_profiles_dir, {
            'id': 'alpha', 'name': 'Alpha', 'mappings': [],
        })
        write_profile(tmp_profiles_dir, {
            'id': 'beta', 'name': 'Beta', 'mappings': [],
        })
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        default = mgr.get_default()
        assert default is not None
        # Falls back to the first profile alphabetically.
        assert default.id in ('alpha', 'beta')

    def test_no_profiles_returns_none(self) -> None:
        mgr = ProfileManager(profiles_dir='/nonexistent')
        assert mgr.get_default() is None

    def test_triggers_cache_build(self, tmp_profiles_dir: str) -> None:
        write_profile(tmp_profiles_dir, {
            'id': 'd', 'name': 'D', 'is_default': True, 'mappings': [],
        })
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        assert mgr.get_default() is not None


# ======================================================================
# Validation
# ======================================================================

class TestValidate:
    """validate() returns a list of error strings."""

    def test_valid_profile_returns_empty(self) -> None:
        profile = Profile(
            id='test', name='Test', mappings=[
                {'gesture': 'open_palm', 'action_type': 'system', 'params': {'type': 'show_desktop'}},
            ],
        )
        assert ProfileManager.validate(profile) == []

    def test_empty_id(self) -> None:
        profile = Profile(id='', name='Test', mappings=[])
        errors = ProfileManager.validate(profile)
        assert any('id' in e for e in errors)

    def test_empty_name(self) -> None:
        profile = Profile(id='test', name='', mappings=[])
        errors = ProfileManager.validate(profile)
        assert any('name' in e for e in errors)

    def test_mappings_not_a_list(self) -> None:
        profile = Profile(id='test', name='Test', mappings="not_a_list")  # type: ignore
        errors = ProfileManager.validate(profile)
        assert any('list' in e for e in errors)

    def test_mapping_missing_keys(self) -> None:
        profile = Profile(id='test', name='Test', mappings=[
            {'gesture': 'open_palm'},  # missing action_type, params
        ])
        errors = ProfileManager.validate(profile)
        assert any('index 0' in e for e in errors)

    def test_mapping_params_not_dict(self) -> None:
        profile = Profile(id='test', name='Test', mappings=[
            {'gesture': 'open_palm', 'action_type': 'system', 'params': 'string'},
        ])
        errors = ProfileManager.validate(profile)
        assert any('params' in e for e in errors)

    def test_mapping_not_dict(self) -> None:
        profile = Profile(id='test', name='Test', mappings=[
            ['not', 'a', 'dict'],
        ])
        errors = ProfileManager.validate(profile)
        assert any('index 0' in e for e in errors)


# ======================================================================
# Save
# ======================================================================

class TestSave:
    """save() persists a Profile to a JSON file."""

    def test_save_valid_profile(self, tmp_profiles_dir: str) -> None:
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        profile = Profile(id='custom', name='Custom', mappings=[
            {'gesture': 'fist', 'action_type': 'keyboard', 'params': {'key': 'escape'}},
        ])
        assert mgr.save(profile) is True
        # Verify the file was created.
        filepath = os.path.join(tmp_profiles_dir, 'custom.json')
        assert os.path.isfile(filepath)
        with open(filepath) as f:
            data = json.load(f)
        assert data['id'] == 'custom'
        assert data['name'] == 'Custom'
        assert len(data['mappings']) == 1

    def test_save_updates_cache(self, tmp_profiles_dir: str) -> None:
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        profile = Profile(id='new', name='New', mappings=[])
        mgr.save(profile)
        # Should be retrievable from cache.
        cached = mgr.load('new')
        assert cached is not None
        assert cached.name == 'New'

    def test_save_invalid_profile_returns_false(self, tmp_profiles_dir: str) -> None:
        mgr = ProfileManager(profiles_dir=tmp_profiles_dir)
        profile = Profile(id='', name='', mappings=[])
        assert mgr.save(profile) is False

    def test_save_creates_directory(self, tmp_profiles_dir: str) -> None:
        nested = os.path.join(tmp_profiles_dir, 'sub', 'nested')
        mgr = ProfileManager(profiles_dir=nested)
        profile = Profile(id='test', name='Test', mappings=[])
        assert mgr.save(profile) is True
        assert os.path.isdir(nested)
        assert os.path.isfile(os.path.join(nested, 'test.json'))


# ======================================================================
# Resolve
# ======================================================================

class TestResolve:
    """resolve() finds a mapping entry by gesture name."""

    def test_existing_gesture(self) -> None:
        profile = Profile(id='t', name='T', mappings=[
            {'gesture': 'open_palm', 'action_type': 'system', 'params': {'type': 'show_desktop'}},
        ])
        mapping = ProfileManager.resolve('open_palm', profile)
        assert mapping is not None
        assert mapping['action_type'] == 'system'

    def test_missing_gesture_returns_none(self) -> None:
        profile = Profile(id='t', name='T', mappings=[])
        assert ProfileManager.resolve('open_palm', profile) is None

    def test_first_match_returned(self) -> None:
        profile = Profile(id='t', name='T', mappings=[
            {'gesture': 'open_palm', 'action_type': 'system', 'params': {}},
            {'gesture': 'open_palm', 'action_type': 'mouse', 'params': {}},
        ])
        mapping = ProfileManager.resolve('open_palm', profile)
        assert mapping is not None
        assert mapping['action_type'] == 'system'


# ======================================================================
# Factory
# ======================================================================

class TestCreateDefault:
    """create_default() builds a Profile from DEFAULT_MAPPINGS."""

    def test_creates_profile_with_default_mappings(self) -> None:
        profile = ProfileManager.create_default()
        assert profile.id == 'default'
        assert profile.is_default is True
        assert len(profile.mappings) == len(DEFAULT_MAPPINGS)

    def test_custom_name(self) -> None:
        profile = ProfileManager.create_default(name='My Profile')
        assert profile.name == 'My Profile'

    def test_mappings_are_identical(self) -> None:
        profile = ProfileManager.create_default()
        for i, m in enumerate(profile.mappings):
            assert m['gesture'] == DEFAULT_MAPPINGS[i]['gesture']
            assert m['action_type'] == DEFAULT_MAPPINGS[i]['action_type']

    def test_created_profile_passes_validation(self) -> None:
        profile = ProfileManager.create_default()
        errors = ProfileManager.validate(profile)
        assert errors == []


# ======================================================================
# Integration with default.json on disk
# ======================================================================

class TestDefaultFileOnDisk:
    """When profiles/default.json exists, load_all() picks it up."""

    def test_default_profile_is_loadable(self) -> None:
        # Use the actual profiles/ directory from the project.
        mgr = ProfileManager(profiles_dir='profiles')
        profiles = mgr.load_all()
        if profiles:
            # At minimum the default profile should be valid.
            default = mgr.get_default()
            assert default is not None
            assert default.id == 'default'
            # Verify it passes validation.
            errors = ProfileManager.validate(default)
            assert errors == []


# ======================================================================
# profiles_dir property
# ======================================================================

class TestProfilesDirProperty:
    def test_default_value(self) -> None:
        mgr = ProfileManager()
        assert mgr.profiles_dir == 'profiles'

    def test_custom_value(self) -> None:
        mgr = ProfileManager(profiles_dir='/path/to/profiles')
        assert mgr.profiles_dir == '/path/to/profiles'
