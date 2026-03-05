"""Autonomous gameplay session runner for EarthBound Zero.

Runs the observe -> Claude API (tool_use) -> execute action loop.
Connects to the Anthropic API directly (not via MCP protocol) for simplicity
and low latency.

Usage:
    python scripts/run_session.py <rom_path> [--max-steps 500] [--session-name test1]
    python scripts/run_session.py <rom_path> --max-steps 100 --no-screenshot

Environment:
    ANTHROPIC_API_KEY  — required for Anthropic API access
    ANTHROPIC_MODEL    — optional, defaults to claude-sonnet-4-20250514
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import anthropic

from src.bridge.auto_checkpoint import AutoCheckpoint
from src.bridge.emulator_bridge import (
    BridgeTimeoutError,
    EmulatorBridge,
    EmulatorCrashedError,
    StaleStateError,
)
from src.knowledge_base.kb import KnowledgeBase
from src.mcp_server.validation import validate_action
from src.state_parser.models import GameMode
from src.state_parser.parser import GameStateParser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Anthropic tool definitions (mirror of docs/MCP_TOOLS.md)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_game_state",
        "description": (
            "Returns current game state: player HP/PP/level, location, game mode "
            "(overworld/battle/menu/dialog), and optionally a screenshot."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include_screenshot": {
                    "type": "boolean",
                    "description": "Include a base64 PNG screenshot. Default true.",
                    "default": True,
                }
            },
        },
    },
    {
        "name": "execute_action",
        "description": (
            "Send a controller action to the emulator. "
            "action_type: move, button, menu_navigate, text_advance, wait."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": ["move", "button", "menu_navigate", "text_advance", "wait"],
                },
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "left", "right"],
                    "description": "Required for action_type=move.",
                },
                "button": {
                    "type": "string",
                    "enum": ["A", "B", "Start", "Select"],
                    "description": "Required for action_type=button.",
                },
                "menu_path": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Required for action_type=menu_navigate.",
                },
                "duration_frames": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 120,
                    "description": "Frames to hold input (default 2 for button, 10 for move).",
                },
                "include_screenshot": {
                    "type": "boolean",
                    "description": "Include screenshot in returned state. Default false.",
                    "default": False,
                },
            },
            "required": ["action_type"],
        },
    },
    {
        "name": "create_save_state",
        "description": "Create an emulator save state checkpoint with a descriptive label.",
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Short descriptive label, e.g. 'before_boss_fight'.",
                }
            },
            "required": ["label"],
        },
    },
    {
        "name": "restore_save_state",
        "description": "Restore the emulator to a previously created save state checkpoint.",
        "input_schema": {
            "type": "object",
            "properties": {
                "save_state_id": {
                    "type": "string",
                    "description": "The save_state_id returned by create_save_state.",
                }
            },
            "required": ["save_state_id"],
        },
    },
    {
        "name": "update_knowledge_base",
        "description": (
            "Read, write, delete, or list entries in Claude's persistent knowledge base. "
            "Sections: map_data, npc_notes, battle_strategies, inventory, objectives, death_log."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["read", "write", "delete", "list_sections"],
                },
                "section": {"type": "string"},
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["operation"],
        },
    },
]

# ---------------------------------------------------------------------------
# Session runner
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-20250514"
SUMMARIZATION_WARNING_THRESHOLD = 40  # Warn before Phase 4 implements full summarization


class SessionRunner:
    """Orchestrates the observe → Claude API → execute action loop."""

    def __init__(
        self,
        rom_path: str,
        session_name: str = "default",
        model: str | None = None,
    ) -> None:
        config = self._load_config()

        self.bridge = EmulatorBridge(config)
        self.parser = GameStateParser()
        self.kb = KnowledgeBase(config["knowledge_base"]["save_path"])
        self.auto_cp = AutoCheckpoint(
            self.bridge,
            interval_minutes=config["gameplay"].get("auto_checkpoint_interval_minutes", 5.0),
        )
        self.client = anthropic.Anthropic()
        self.model = model or DEFAULT_MODEL
        self.rom_path = rom_path
        self.session_name = session_name
        self.config = config

        # Conversation history (grows until Phase 4 adds summarization)
        self.messages: list[dict[str, Any]] = []
        self.tool_call_count = 0
        self.step_count = 0

        # Decision log
        self.log_dir = PROJECT_ROOT / "data" / "sessions" / session_name
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.decision_log: list[dict[str, Any]] = []

        self.system_prompt = self._load_system_prompt()

    # -- Public ---------------------------------------------------------------

    def run(self, max_steps: int = 500) -> None:
        """Start FCEUX and run the session loop."""
        logger.info("Starting session '%s' (max %d steps)", self.session_name, max_steps)
        self.bridge.start(self.rom_path)

        try:
            self.messages.append({
                "role": "user",
                "content": (
                    "You are now connected to EarthBound Zero. "
                    "Begin by observing the current game state."
                ),
            })

            while self.step_count < max_steps:
                if self.tool_call_count >= SUMMARIZATION_WARNING_THRESHOLD:
                    logger.warning(
                        "Tool call count (%d) approaching context limit. "
                        "Progressive summarization (Phase 4) is not yet implemented.",
                        self.tool_call_count,
                    )

                response = self._call_claude()
                has_tool_calls = self._process_response(response)
                self.step_count += 1

                if not has_tool_calls and response.stop_reason == "end_turn":
                    # Claude finished without a tool call — nudge it to continue
                    self.messages.append({
                        "role": "user",
                        "content": (
                            "Continue playing. Call get_game_state to observe the current state."
                        ),
                    })

        except KeyboardInterrupt:
            logger.info("Session interrupted by user.")
        finally:
            self._save_decision_log()
            if self.bridge.is_alive():
                self.bridge.stop()
            logger.info(
                "Session complete. Steps: %d, Tool calls: %d. Log: %s",
                self.step_count,
                self.tool_call_count,
                self.log_dir / "decisions.json",
            )

    # -- Claude API -----------------------------------------------------------

    def _call_claude(self) -> anthropic.types.Message:
        return self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=self.system_prompt,
            tools=TOOL_DEFINITIONS,
            messages=self.messages,
        )

    def _process_response(self, response: anthropic.types.Message) -> bool:
        """Append assistant turn and execute any tool calls. Returns True if tools were called."""
        self.messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "text":
                logger.info("Claude: %s", block.text[:300])
            elif block.type == "tool_use":
                logger.info("Tool call: %s(%s)", block.name, json.dumps(block.input)[:200])
                result = self._execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })
                self.tool_call_count += 1
                self._log_decision(block.name, block.input, result)

        if tool_results:
            self.messages.append({"role": "user", "content": tool_results})
            return True
        return False

    # -- Tool dispatch --------------------------------------------------------

    def _execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "get_game_state":
                return self._tool_get_game_state(args)
            if name == "execute_action":
                return self._tool_execute_action(args)
            if name == "create_save_state":
                return self._tool_create_save_state(args)
            if name == "restore_save_state":
                return self._tool_restore_save_state(args)
            if name == "update_knowledge_base":
                return self._tool_update_knowledge_base(args)
            return {"error": f"Unknown tool: {name}"}
        except (EmulatorCrashedError, BridgeTimeoutError, StaleStateError) as exc:
            logger.error("Bridge error in %s: %s", name, exc)
            return {"error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error in %s: %s", name, exc)
            return {"error": f"Unexpected error: {exc}"}

    def _tool_get_game_state(self, args: dict[str, Any]) -> dict[str, Any]:
        include_ss = args.get("include_screenshot", True)
        raw = self.bridge.get_state()
        screenshot_b64 = self.bridge.capture_screenshot() if include_ss else None
        state = self.parser.build_state(raw, screenshot_b64)

        # Auto-checkpoint checks
        self.auto_cp.check_and_save(
            map_id=state.location.map_id,
            hp=state.player.hp,
            max_hp=state.player.max_hp,
        )
        if state.player.hp <= 0:
            self.auto_cp.check_game_over(state.player.hp)

        return state.model_dump(mode="json", exclude_none=True)

    def _tool_execute_action(self, args: dict[str, Any]) -> dict[str, Any]:
        action_type = args.get("action_type", "")
        direction = args.get("direction")
        button = args.get("button")
        menu_path = args.get("menu_path")
        duration_frames = args.get("duration_frames", 2)
        include_ss = args.get("include_screenshot", False)

        # Get current game mode for validation
        raw = self.bridge.get_state()
        current_state = self.parser.build_state(raw)
        game_mode = current_state.game_mode

        # Validate
        errors = validate_action(
            action_type,
            game_mode,
            direction=direction,
            button=button,
            menu_path=menu_path,
            duration_frames=duration_frames,
        )
        if errors:
            return {"success": False, "action_performed": action_type, "errors": errors}

        # Dispatch
        if action_type == "move":
            self.bridge.send_input(
                command="move",
                direction=direction,
                duration_frames=duration_frames,
            )
            desc = f"move {direction} for {duration_frames} frames"
        elif action_type == "button":
            self.bridge.send_input(
                command="button",
                button=button,
                duration_frames=duration_frames,
            )
            desc = f"press {button}"
        elif action_type == "text_advance":
            self.bridge.send_input(command="button", button="A", duration_frames=2)
            desc = "advance text (A)"
        elif action_type == "menu_navigate":
            # Phase 2 stub: press A once per menu entry
            for entry in (menu_path or []):
                self.bridge.send_input(command="button", button="A", duration_frames=4)
            desc = f"menu_navigate {menu_path}"
        elif action_type == "wait":
            self.bridge.send_input(command="wait", duration_frames=duration_frames)
            desc = f"wait {duration_frames} frames"
        else:
            return {"success": False, "action_performed": action_type, "errors": ["Unknown action"]}

        # Return resulting state
        raw_after = self.bridge.get_state()
        ss_after = self.bridge.capture_screenshot() if include_ss else None
        new_state = self.parser.build_state(raw_after, ss_after)

        return {
            "success": True,
            "action_performed": desc,
            "game_state": new_state.model_dump(mode="json", exclude_none=True),
        }

    def _tool_create_save_state(self, args: dict[str, Any]) -> dict[str, Any]:
        label = args.get("label", "checkpoint")
        save_id = self.bridge.create_save_state(label)
        raw = self.bridge.get_state()
        state = self.parser.build_state(raw)
        summary = (
            f"Ninten Lv{state.player.level} HP:{state.player.hp}/{state.player.max_hp} "
            f"at {state.location.map_name} ({state.location.x},{state.location.y})"
        )
        return {
            "save_state_id": save_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "game_state_summary": summary,
        }

    def _tool_restore_save_state(self, args: dict[str, Any]) -> dict[str, Any]:
        save_state_id = args.get("save_state_id", "")
        self.bridge.restore_save_state(save_state_id)
        time.sleep(0.3)  # Let emulator settle after load
        raw = self.bridge.get_state()
        state = self.parser.build_state(raw)
        return {
            "success": True,
            "restored_state": state.model_dump(mode="json", exclude_none=True),
        }

    def _tool_update_knowledge_base(self, args: dict[str, Any]) -> dict[str, Any]:
        op = args.get("operation", "")
        section = args.get("section")
        key = args.get("key")
        value = args.get("value")

        try:
            if op == "list_sections":
                return {"sections": self.kb.list_sections()}
            if op == "read":
                val = self.kb.read(section, key)
                return {"section": section, "key": key, "value": val}
            if op == "write":
                self.kb.write(section, key, value)
                return {"section": section, "key": key, "value": value}
            if op == "delete":
                self.kb.delete(section, key)
                return {"section": section, "key": key}
            return {"error": f"Unknown operation: {op}"}
        except ValueError as exc:
            return {"error": str(exc)}

    # -- Logging / persistence ------------------------------------------------

    def _log_decision(self, tool: str, args: dict, result: dict) -> None:
        self.decision_log.append({
            "step": self.step_count,
            "tool_call": self.tool_call_count,
            "timestamp": time.time(),
            "tool": tool,
            "args": args,
            "result_summary": str(result)[:500],
        })

    def _save_decision_log(self) -> None:
        log_path = self.log_dir / "decisions.json"
        with open(log_path, "w") as f:
            json.dump(self.decision_log, f, indent=2)
        logger.info("Decision log saved: %s", log_path)

    # -- Helpers --------------------------------------------------------------

    @staticmethod
    def _load_config() -> dict[str, Any]:
        config_path = PROJECT_ROOT / "config.json"
        with open(config_path) as f:
            return json.load(f)

    @staticmethod
    def _load_system_prompt() -> str:
        prompt_path = PROJECT_ROOT / "docs" / "system_prompt.md"
        with open(prompt_path) as f:
            return f.read()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Run an autonomous EarthBound Zero gameplay session.")
    parser.add_argument("rom_path", help="Path to the EarthBound Zero ROM file.")
    parser.add_argument("--max-steps", type=int, default=500, help="Max session steps (default 500).")
    parser.add_argument("--session-name", default="default", help="Session name for log directory.")
    parser.add_argument("--model", default=None, help=f"Anthropic model ID (default {DEFAULT_MODEL}).")
    args = parser.parse_args()

    runner = SessionRunner(
        rom_path=args.rom_path,
        session_name=args.session_name,
        model=args.model,
    )
    runner.run(max_steps=args.max_steps)


if __name__ == "__main__":
    main()
