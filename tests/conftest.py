"""Shared test setup: make the version2 modules importable and fix the codes."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "version2"))

from engine import GameEngine  # noqa: E402

DRAWER_CODE = "392"
DOOR_CODE = "7146"


@pytest.fixture
def game() -> GameEngine:
    """A new game with known codes, so the tests are repeatable."""
    return GameEngine(codes={"drawer_code": DRAWER_CODE, "door_code": DOOR_CODE})


def act(game: GameEngine, action: str, target: str = "", item: str = "", code: str = "") -> dict:
    return game.perform({"action": action, "target": target, "item": item, "code": code})


def play_to_flashlight(game: GameEngine) -> None:
    """Solve the first two puzzles the legitimate way."""
    act(game, "enter_code", "drawer", code=DRAWER_CODE)
    act(game, "take", "brass key")
    act(game, "use", "cabinet", item="brass key")
    act(game, "take", "flashlight")
