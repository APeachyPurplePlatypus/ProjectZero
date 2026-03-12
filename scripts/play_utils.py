"""Play utilities for EarthBound Zero: name entry navigation and overworld helpers.

Functions for navigating the name-entry letter grid, typing character names
during new-game setup, and safe overworld movement that avoids opening menus.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from src.bridge.emulator_bridge import EmulatorBridge

# ---------------------------------------------------------------------------
# Name-entry letter grid layout
# ---------------------------------------------------------------------------
# The name-entry screen shows a 14-column x 4-row grid of letters,
# with Back/End control rows below:
#
# Row 0:  A B C D E F G   H I J K L M N   (cols 0-13)
# Row 1:  O P Q R S T U   V W X Y Z . '   (cols 0-13)
# Row 2:  a b c d e f g   h i j k l m n   (cols 0-13)
# Row 3:  o p q r s t u   v w x y z - :   (cols 0-13)
# Row 4:  <Back  (col 0)    End (col 7)

LETTER_GRID: dict[str, tuple[int, int]] = {}

_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ.'"
_LOWER = "abcdefghijklmnopqrstuvwxyz-:"

for _i, _ch in enumerate(_UPPER):
    _row = _i // 14  # 0 or 1
    _col = _i % 14
    LETTER_GRID[_ch] = (_row, _col)

for _i, _ch in enumerate(_LOWER):
    _row = 2 + _i // 14  # 2 or 3
    _col = _i % 14
    LETTER_GRID[_ch] = (_row, _col)

LETTER_GRID["End"] = (4, 7)
LETTER_GRID["Back"] = (4, 0)

# Total grid rows (0-4) and columns (0-13)
_GRID_ROWS = 5
_GRID_COLS = 14

# Default character names
DEFAULT_NAMES = {
    "boy": "Ninten",   # protagonist
    "girl": "Ana",
    "boy2": "Lloyd",
    "boy3": "Teddy",
    "food": "Steak",   # favorite food (affects a PSI move's name)
}

# Type alias for the send function
SendFn = Callable[..., None]


# ---------------------------------------------------------------------------
# Cursor navigation
# ---------------------------------------------------------------------------

def _move_cursor(
    cur: tuple[int, int],
    target: tuple[int, int],
    send_fn: SendFn,
) -> None:
    """Move the name-entry cursor from cur to target using D-pad commands."""
    r0, c0 = cur
    r1, c1 = target

    # Vertical movement
    dr = r1 - r0
    if dr != 0:
        direction = "down" if dr > 0 else "up"
        for _ in range(abs(dr)):
            send_fn("move", direction=direction, duration_frames=2)
            send_fn("wait", duration_frames=4)

    # Horizontal movement
    dc = c1 - c0
    if dc != 0:
        direction = "right" if dc > 0 else "left"
        for _ in range(abs(dc)):
            send_fn("move", direction=direction, duration_frames=2)
            send_fn("wait", duration_frames=4)


def type_name(name: str, send_fn: SendFn) -> None:
    """Navigate the name-entry cursor to spell out `name` then select End.

    The cursor starts at letter 'A' (row 0, col 0). For each character in
    the name, moves the cursor to that letter's grid position and presses A.
    After all characters, navigates to End and confirms.
    """
    cur = (0, 0)  # cursor starts at 'A'

    for ch in name:
        if ch not in LETTER_GRID:
            raise ValueError(
                f"Character '{ch}' not in name-entry grid. "
                f"Valid: uppercase, lowercase, . ' - :"
            )
        target = LETTER_GRID[ch]
        _move_cursor(cur, target, send_fn)
        send_fn("button", button="A", duration_frames=3)
        send_fn("wait", duration_frames=8)
        cur = target

    # Navigate to End and confirm
    _move_cursor(cur, LETTER_GRID["End"], send_fn)
    send_fn("button", button="A", duration_frames=3)
    send_fn("wait", duration_frames=30)  # wait for screen to advance


def start_new_game(
    names: dict[str, str] | None = None,
    send_fn: SendFn | None = None,
) -> None:
    """Navigate through all 5 name-entry screens and confirm.

    Call this after the game reaches the first name-entry screen.

    Args:
        names: Dict with keys "boy", "girl", "boy2", "boy3", "food".
               Defaults to DEFAULT_NAMES if not provided.
        send_fn: Function to send commands (bridge.send_input signature).
    """
    if send_fn is None:
        raise ValueError("send_fn is required")
    if names is None:
        names = DEFAULT_NAMES

    for key in ["boy", "girl", "boy2", "boy3", "food"]:
        # Wait for name screen to settle
        send_fn("wait", duration_frames=60)
        name_val = names.get(key, DEFAULT_NAMES.get(key, ""))
        type_name(name_val, send_fn)

    # Confirmation screen: "Is this OK? Yes / No" — Yes is selected by default
    send_fn("wait", duration_frames=60)
    send_fn("button", button="A", duration_frames=5)
    send_fn("wait", duration_frames=120)  # wait for intro to start


# ---------------------------------------------------------------------------
# Overworld movement helpers
# ---------------------------------------------------------------------------

def safe_move(
    bridge: EmulatorBridge,
    send_fn: SendFn,
    direction: str,
    frames: int = 15,
) -> None:
    """Move with automatic menu-close guard.

    On the overworld, pressing A opens the Command menu which blocks movement.
    This function checks for active menus/dialogs and clears them with B
    before issuing the move command.

    Note: menu_state and dialog_active are currently hardcoded to 0 in the
    Lua state exporter (addresses TBD). Until those addresses are found,
    this guard relies on the known memory values. A post-battle B-press
    convention is also recommended.
    """
    state = bridge.get_state()
    if state.menu_state != 0 or state.dialog_active != 0:
        send_fn("button", button="B", duration_frames=3)
        send_fn("wait", duration_frames=15)

    send_fn("move", direction=direction, duration_frames=frames)


def post_battle_clear(send_fn: SendFn) -> None:
    """Press B to dismiss any lingering menu/dialog after a battle ends.

    Call this after detecting a battle-to-overworld transition before
    issuing any movement commands.
    """
    send_fn("button", button="B", duration_frames=3)
    send_fn("wait", duration_frames=15)
