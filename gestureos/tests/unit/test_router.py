"""Unit tests for the CP-5 CommandRouter.

Tests cover:
  - Default mappings route known gestures to expected actions.
  - Profile mappings take priority over router defaults.
  - Unmapped gestures return None.
  - Malformed mapping entries are pruned at construction.
  - Empty profile falls back to router defaults.
  - Thread safety / stateless contract.
"""

from __future__ import annotations

from models.data_models import GestureResult, Profile

from actions.router import CommandRouter, DEFAULT_MAPPINGS


# ======================================================================
# Helpers
# ======================================================================

def make_gesture(
    gesture_name: str = 'open_palm',
    confidence: float = 0.95,
    is_dynamic: bool = False,
    hand_role: str = 'HAND_A',
    timestamp: float = 1000.0,
) -> GestureResult:
    return GestureResult(
        gesture_name=gesture_name,
        confidence=confidence,
        is_dynamic=is_dynamic,
        hand_role=hand_role,
        timestamp=timestamp,
    )


def make_profile(
    mappings: list[dict] | None = None,
    profile_id: str = 'test',
    name: str = 'Test Profile',
) -> Profile:
    return Profile(
        id=profile_id,
        name=name,
        is_default=False,
        mappings=mappings or [],
    )


# ======================================================================
# Default mappings
# ======================================================================

class TestDefaultMappings:
    """When no profile is provided, the router uses its default mappings."""

    def test_open_palm_routes_to_system(self) -> None:
        router = CommandRouter()
        action = router.route(make_gesture('open_palm'))
        assert action is not None
        assert action.action_type == 'system'
        assert action.params == {'type': 'show_desktop'}
        assert action.gesture_name == 'open_palm'

    def test_fist_routes_to_toggle_gesture_control(self) -> None:
        router = CommandRouter()
        action = router.route(make_gesture('fist'))
        assert action is not None
        assert action.action_type == 'system'
        assert action.params == {'type': 'toggle_gesture_control'}

    def test_thumbs_up_routes_to_keyboard(self) -> None:
        router = CommandRouter()
        action = router.route(make_gesture('thumbs_up'))
        assert action is not None
        assert action.action_type == 'keyboard'
        assert action.params == {'key': 'volume_up'}

    def test_thumbs_down_routes_to_keyboard(self) -> None:
        router = CommandRouter()
        action = router.route(make_gesture('thumbs_down'))
        assert action is not None
        assert action.action_type == 'keyboard'
        assert action.params == {'key': 'volume_down'}

    def test_pinch_routes_to_mouse(self) -> None:
        router = CommandRouter()
        action = router.route(make_gesture('pinch'))
        assert action is not None
        assert action.action_type == 'mouse'
        assert action.params == {'action': 'click'}

    def test_peace_sign_routes_to_keyboard(self) -> None:
        router = CommandRouter()
        action = router.route(make_gesture('peace_sign'))
        assert action is not None
        assert action.action_type == 'keyboard'
        assert action.params == {'key': 'media_play_pause'}


# ======================================================================
# Unmapped gestures
# ======================================================================

class TestUnmappedGestures:
    """Gestures not present in any mapping return None."""

    def test_unknown_gesture_returns_none(self) -> None:
        router = CommandRouter()
        action = router.route(make_gesture('unknown_gesture'))
        assert action is None

    def test_three_fingers_not_in_defaults(self) -> None:
        router = CommandRouter()
        action = router.route(make_gesture('three_fingers'))
        assert action is None


# ======================================================================
# Profile priority
# ======================================================================

class TestProfilePriority:
    """When a profile is provided, its mappings take priority."""

    def test_profile_mapping_overrides_default(self) -> None:
        router = CommandRouter()
        profile = make_profile(mappings=[
            {'gesture': 'open_palm', 'action_type': 'mouse', 'params': {'action': 'click'}},
        ])
        action = router.route(make_gesture('open_palm'), profile=profile)
        assert action is not None
        # Profile takes priority over the default 'system' action.
        assert action.action_type == 'mouse'
        assert action.params == {'action': 'click'}

    def test_profile_with_no_match_falls_back(self) -> None:
        router = CommandRouter()
        profile = make_profile(mappings=[
            {'gesture': 'pinch', 'action_type': 'mouse', 'params': {'action': 'click'}},
        ])
        action = router.route(make_gesture('open_palm'), profile=profile)
        assert action is not None
        # Profile doesn't have 'open_palm' — fall back to default.
        assert action.action_type == 'system'
        assert action.params == {'type': 'show_desktop'}

    def test_profile_empty_falls_back(self) -> None:
        router = CommandRouter()
        profile = make_profile(mappings=[])
        action = router.route(make_gesture('open_palm'), profile=profile)
        assert action is not None
        assert action.action_type == 'system'

    def test_profile_missing_gesture_in_profile_only(self) -> None:
        router = CommandRouter()
        profile = make_profile(mappings=[
            {'gesture': 'pinch', 'action_type': 'mouse', 'params': {'action': 'click'}},
        ])
        # 'peace_sign' is in defaults but not in profile.
        action = router.route(make_gesture('peace_sign'), profile=profile)
        assert action is not None
        assert action.action_type == 'keyboard'

    def test_gesture_in_profile_only_not_in_defaults(self) -> None:
        router = CommandRouter()
        profile = make_profile(mappings=[
            {'gesture': 'ok_sign', 'action_type': 'system', 'params': {'type': 'confirm'}},
        ])
        action = router.route(make_gesture('ok_sign'), profile=profile)
        assert action is not None
        assert action.action_type == 'system'
        assert action.params == {'type': 'confirm'}


# ======================================================================
# Construction validation
# ======================================================================

class TestConstructionValidation:
    """Malformed mapping entries are pruned at construction time."""

    def test_missing_params_skipped(self) -> None:
        router = CommandRouter(mappings=[
            {'gesture': 'open_palm', 'action_type': 'system'},
        ])
        # The single entry is missing 'params' — no valid mappings remain.
        action = router.route(make_gesture('open_palm'))
        assert action is None

    def test_missing_gesture_skipped(self) -> None:
        router = CommandRouter(mappings=[
            {'action_type': 'system', 'params': {}},
        ])
        action = router.route(make_gesture('open_palm'))
        assert action is None

    def test_not_a_dict_skipped(self) -> None:
        router = CommandRouter(mappings=[
            ['not', 'a', 'dict'],
        ])
        action = router.route(make_gesture('open_palm'))
        assert action is None

    def test_params_not_a_dict_skipped(self) -> None:
        router = CommandRouter(mappings=[
            {'gesture': 'open_palm', 'action_type': 'system', 'params': 'not_a_dict'},
        ])
        action = router.route(make_gesture('open_palm'))
        assert action is None

    def test_valid_and_invalid_mixed(self) -> None:
        router = CommandRouter(mappings=[
            {'gesture': 'open_palm', 'action_type': 'system', 'params': {'type': 'show_desktop'}},
            {'gesture': 'fist', 'action_type': 'system'},  # missing params
            {'gesture': 'thumbs_up', 'action_type': 'keyboard', 'params': {'key': 'volume_up'}},
        ])
        # 'open_palm' and 'thumbs_up' should work; 'fist' was pruned.
        assert router.route(make_gesture('open_palm')) is not None
        assert router.route(make_gesture('thumbs_up')) is not None
        assert router.route(make_gesture('fist')) is None


# ======================================================================
# Custom mappings at construction
# ======================================================================

class TestCustomMappings:
    """Mappings can be injected at construction time."""

    def test_custom_mappings_used(self) -> None:
        router = CommandRouter(mappings=[
            {'gesture': 'three_fingers', 'action_type': 'keyboard', 'params': {'key': 'tab'}},
        ])
        action = router.route(make_gesture('three_fingers'))
        assert action is not None
        assert action.action_type == 'keyboard'
        assert action.params == {'key': 'tab'}

    def test_custom_overrides_defaults(self) -> None:
        # Providing custom mappings replaces the defaults entirely.
        router = CommandRouter(mappings=[
            {'gesture': 'open_palm', 'action_type': 'mouse', 'params': {'action': 'click'}},
        ])
        # Only 'open_palm' is mapped.
        assert router.route(make_gesture('open_palm')) is not None
        assert router.route(make_gesture('fist')) is None


# ======================================================================
# Stateless contract
# ======================================================================

class TestStateless:
    """The router must not mutate its inputs or internal state on route()."""

    def test_route_does_not_mutate_gesture(self) -> None:
        router = CommandRouter()
        gesture = make_gesture('open_palm')
        original_name = gesture.gesture_name
        router.route(gesture)
        assert gesture.gesture_name == original_name

    def test_route_does_not_mutate_profile(self) -> None:
        router = CommandRouter()
        profile = make_profile(mappings=[
            {'gesture': 'open_palm', 'action_type': 'mouse', 'params': {'action': 'click'}},
        ])
        original_count = len(profile.mappings)
        router.route(make_gesture('open_palm'), profile=profile)
        router.route(make_gesture('fist'), profile=profile)
        assert len(profile.mappings) == original_count


# ======================================================================
# Action shape
# ======================================================================

class TestActionShape:
    """Every routed action must satisfy the Action dataclass contract."""

    def test_action_has_all_fields(self) -> None:
        router = CommandRouter()
        action = router.route(make_gesture('open_palm'))
        assert action is not None
        # Required fields from data_models.Action
        assert hasattr(action, 'action_type')
        assert hasattr(action, 'params')
        assert hasattr(action, 'gesture_name')
        assert hasattr(action, 'context')

    def test_action_context_is_empty_by_default(self) -> None:
        router = CommandRouter()
        action = router.route(make_gesture('thumbs_up'))
        assert action is not None
        assert action.context == ''

    def test_action_params_is_never_none(self) -> None:
        router = CommandRouter()
        action = router.route(make_gesture('thumbs_up'))
        assert action is not None
        assert action.params is not None

    def test_default_mappings_are_sane(self) -> None:
        # Verify the module-level DEFAULT_MAPPINGS list contains only
        # valid entries (every gesture recognisable by the system).
        from actions.router import DEFAULT_MAPPINGS
        valid_gestures = {
            'open_palm', 'fist', 'pinch', 'thumbs_up', 'thumbs_down',
            'peace_sign', 'three_fingers', 'ok_sign',
        }
        for m in DEFAULT_MAPPINGS:
            assert m['gesture'] in valid_gestures, (
                f"Default mapping references unknown gesture: {m['gesture']}"
            )
