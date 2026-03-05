"""Context-aware input validation for MCP execute_action tool.

Rejects actions that are nonsensical for the current game mode and
returns descriptive error messages to guide Claude's decision-making.
"""

from __future__ import annotations

from src.state_parser.models import GameMode

VALID_DIRECTIONS: frozenset[str] = frozenset({"up", "down", "left", "right"})
VALID_BUTTONS: frozenset[str] = frozenset({"A", "B", "Start", "Select"})
VALID_ACTION_TYPES: frozenset[str] = frozenset(
    {"move", "button", "menu_navigate", "text_advance", "wait"}
)
MAX_DURATION_FRAMES = 120


def validate_action(
    action_type: str,
    game_mode: GameMode,
    direction: str | None = None,
    button: str | None = None,
    menu_path: list[str] | None = None,
    duration_frames: int = 2,
) -> list[str]:
    """Validate an action against the current game mode and parameters.

    Returns a list of error strings. An empty list means the action is valid.
    """
    errors: list[str] = []

    if action_type not in VALID_ACTION_TYPES:
        errors.append(
            f"Invalid action_type '{action_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_ACTION_TYPES))}."
        )
        return errors  # Can't validate further without a valid type

    if duration_frames < 1:
        errors.append("duration_frames must be at least 1.")
    if duration_frames > MAX_DURATION_FRAMES:
        errors.append(
            f"duration_frames {duration_frames} exceeds maximum {MAX_DURATION_FRAMES} "
            f"(2 seconds at 60fps). Use a smaller value."
        )

    if action_type == "move":
        if game_mode == GameMode.BATTLE:
            errors.append(
                "Cannot use 'move' during battle. "
                "Use 'button' (A=BASH) or 'menu_navigate' for battle actions."
            )
        if direction is None:
            errors.append("'move' requires a 'direction' parameter (up/down/left/right).")
        elif direction not in VALID_DIRECTIONS:
            errors.append(
                f"Invalid direction '{direction}'. "
                f"Must be one of: {', '.join(sorted(VALID_DIRECTIONS))}."
            )

    elif action_type == "button":
        if button is None:
            errors.append("'button' requires a 'button' parameter (A/B/Start/Select).")
        elif button not in VALID_BUTTONS:
            errors.append(
                f"Invalid button '{button}'. "
                f"Must be one of: {', '.join(sorted(VALID_BUTTONS))}."
            )

    elif action_type == "menu_navigate":
        if not menu_path:
            errors.append("'menu_navigate' requires a non-empty 'menu_path' list.")
        if game_mode == GameMode.OVERWORLD:
            errors.append(
                "No menu is open (game_mode is 'overworld'). "
                "Press Start to open the menu before navigating."
            )

    elif action_type == "text_advance":
        if game_mode not in (GameMode.DIALOG, GameMode.BATTLE):
            errors.append(
                f"'text_advance' is only valid during dialog or battle, "
                f"not '{game_mode.value}'. Check game_mode before using this action."
            )

    # 'wait' is valid in any mode — no extra checks needed

    return errors
