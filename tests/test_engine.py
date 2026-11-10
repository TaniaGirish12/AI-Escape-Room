"""Tests for the Version 2 game engine (no LLM needed).

Run from the project root:  pytest
"""

import copy
import random

from conftest import DOOR_CODE, DRAWER_CODE, act, play_to_flashlight
from engine import ACTIONS, GameEngine


# ------------------------------------------------------------ normal play

def test_new_game_starts_locked_and_empty(game):
    state = game.state
    assert state["inventory"] == []
    assert not any(state["puzzles"].values())
    assert state["objects"]["drawer"]["locked"]
    assert state["objects"]["cabinet"]["locked"]
    assert state["objects"]["door"]["locked"]
    assert not state["escaped"]
    assert game.check_invariants() == []


def test_full_solution_escapes(game):
    assert act(game, "examine", "desk")["success"]
    shelf = act(game, "examine", "bookshelf")
    assert "Vol. 3" in shelf["message"] and "Vol. 9" in shelf["message"] and "Vol. 2" in shelf["message"]

    assert act(game, "enter_code", "drawer", code=DRAWER_CODE)["reason"] == "unlocked"
    assert act(game, "take", "key")["success"]
    assert act(game, "use", "cabinet", item="key")["reason"] == "unlocked"
    assert act(game, "take", "torch")["success"]

    reveal = act(game, "use", "painting", item="flashlight")
    assert reveal["reason"] == "revealed" and DOOR_CODE in reveal["message"]

    final = act(game, "enter_code", "door", code=DOOR_CODE)
    assert final["reason"] == "escaped"
    assert game.state["escaped"]
    assert all(game.state["puzzles"].values())
    assert game.check_invariants() == []


def test_codes_are_different_in_every_game():
    codes = {(g.secrets["drawer_code"], g.secrets["door_code"])
             for g in (GameEngine(seed=s) for s in range(20))}
    assert len(codes) > 15


def test_bookshelf_clue_matches_generated_code():
    game = GameEngine(seed=7)
    red, green, blue = game.secrets["drawer_code"]
    message = act(game, "examine", "bookshelf")["message"]
    assert f'red book marked "Vol. {red}"' in message
    assert f'green book marked "Vol. {green}"' in message
    assert f'blue book marked "Vol. {blue}"' in message


# ------------------------------------------------------------ action validation

def test_key_cannot_be_used_before_it_is_collected(game):
    result = act(game, "use", "cabinet", item="brass key")
    assert not result["success"] and result["reason"] == "item_not_in_inventory"
    assert game.state["objects"]["cabinet"]["locked"]


def test_replies_do_not_name_items_the_player_has_not_found(game):
    for result in (act(game, "use", "cabinet", item="brass_key"), act(game, "examine", "brass_key"),
                   act(game, "take", "brass key"), act(game, "use", "painting", item="uv_flashlight")):
        assert not result["success"]
        assert "brass" not in result["message"].lower() and "uv" not in result["message"].lower()
        assert "_" not in result["message"]


def test_key_in_open_drawer_must_still_be_picked_up(game):
    act(game, "enter_code", "drawer", code=DRAWER_CODE)
    result = act(game, "use", "cabinet", item="brass key")   # seen, but not taken
    assert result["reason"] == "item_not_in_inventory"
    assert game.state["objects"]["cabinet"]["locked"]


def test_wrong_drawer_code_is_rejected_and_counted(game):
    result = act(game, "enter_code", "drawer", code="111")
    assert not result["success"] and result["reason"] == "code_rejected"
    assert game.state["log"][-1]["reason"] == "wrong_code"
    assert game.state["objects"]["drawer"]["locked"]
    assert game.state["failed_code_attempts"]["drawer"] == 1
    assert act(game, "take", "brass key")["reason"] == "not_available"


def test_code_with_wrong_number_of_digits(game):
    assert act(game, "enter_code", "drawer", code="39")["reason"] == "bad_code_format"
    assert act(game, "enter_code", "door", code="71460")["reason"] == "bad_code_format"


def test_opening_locked_things_without_code_or_key_fails(game):
    assert act(game, "open", "drawer")["reason"] == "locked_needs_code"
    assert act(game, "open", "cabinet")["reason"] == "locked_needs_key"
    assert act(game, "open", "door")["reason"] == "locked_needs_code"
    assert not game.state["escaped"]


def test_flashlight_behind_glass_cannot_be_taken(game):
    result = act(game, "take", "flashlight")
    assert result["reason"] == "container_locked"
    assert "uv_flashlight" not in game.state["inventory"]


def test_items_cannot_be_collected_twice(game):
    act(game, "enter_code", "drawer", code=DRAWER_CODE)
    assert act(game, "take", "key")["success"]
    assert act(game, "take", "key")["reason"] == "already_have"
    assert game.state["inventory"] == ["brass_key"]


def test_wrong_item_on_wrong_object_has_no_effect(game):
    act(game, "enter_code", "drawer", code=DRAWER_CODE)
    act(game, "take", "key")
    assert act(game, "use", "painting", item="key")["reason"] == "no_effect"
    assert act(game, "use", "door", item="key")["reason"] == "no_effect"
    assert not game.state["objects"]["painting"]["revealed"]


def test_nonexistent_objects_and_items(game):
    assert act(game, "examine", "window")["reason"] == "unknown_object"
    assert act(game, "open", "trapdoor")["reason"] == "unknown_object"
    assert act(game, "take", "crowbar")["reason"] == "unknown_object"
    assert act(game, "use", "door", item="crowbar")["reason"] == "item_not_in_inventory"
    assert act(game, "take", "painting")["reason"] == "not_takeable"
    assert game.state["inventory"] == []


# ------------------------------------------------------------ the exit

def test_door_rejects_wrong_code(game):
    assert act(game, "enter_code", "door", code="0000")["reason"] == "code_rejected"
    assert not game.state["escaped"]


def test_correct_door_code_is_not_enough_without_the_puzzles(game):
    """A lucky guess (or a leaked code) must not skip the game."""
    result = act(game, "enter_code", "door", code=DOOR_CODE)
    assert not result["success"]
    assert game.state["log"][-1]["reason"] == "prerequisites_missing"   # known only internally
    assert not game.state["escaped"]
    # what the player and the LLM see must be identical to a wrong code
    wrong = act(game, "enter_code", "door", code="1111")
    wrong["message"] = wrong["message"].replace("1111", DOOR_CODE)
    assert result == wrong


def test_solved_puzzles_stay_solved(game):
    play_to_flashlight(game)
    before = copy.deepcopy(game.state["puzzles"])
    for _ in range(3):
        act(game, "enter_code", "drawer", code="000")
        act(game, "open", "drawer")
        act(game, "use", "cabinet", item="key")
        act(game, "examine", "cabinet")
    assert game.state["puzzles"] == before
    assert not game.state["objects"]["drawer"]["locked"]
    assert game.state["inventory"] == ["brass_key", "uv_flashlight"]


def test_nothing_happens_after_escape(game):
    play_to_flashlight(game)
    act(game, "use", "painting", item="flashlight")
    act(game, "enter_code", "door", code=DOOR_CODE)
    snapshot = copy.deepcopy({k: v for k, v in game.state.items() if k not in ("moves", "log")})
    assert act(game, "take", "painting")["reason"] == "game_over"
    assert {k: v for k, v in game.state.items() if k not in ("moves", "log")} == snapshot


# ------------------------------------------------------------ secrets and hints

def test_public_state_never_contains_the_codes(game):
    assert DRAWER_CODE not in str(game.public_state())
    assert DOOR_CODE not in str(game.public_state())
    play_to_flashlight(game)
    assert DOOR_CODE not in str(game.public_state())


def test_no_reply_contains_the_door_code_before_it_is_revealed(game):
    play_to_flashlight(game)
    for target in list(game.objects) + ["flashlight", "key", "window"]:
        for action in ("examine", "open", "take"):
            assert DOOR_CODE not in act(game, action, target)["message"]
    assert DOOR_CODE in game.protected_secrets()


def test_hints_never_contain_a_code(game):
    steps = [
        ("enter_code", "drawer", "", DRAWER_CODE), ("take", "key", "", ""),
        ("use", "cabinet", "key", ""), ("take", "flashlight", "", ""),
        ("use", "painting", "flashlight", ""),
    ]
    hints = [act(game, "hint")["message"]]
    for action, target, item, code in steps:
        act(game, action, target, item, code)
        hints.append(act(game, "hint")["message"])
    assert len(set(hints)) == len(hints)              # the hint follows the progress
    for hint in hints:
        assert DRAWER_CODE not in hint and DOOR_CODE not in hint


def test_unknown_or_malformed_actions_change_nothing(game):
    before = copy.deepcopy(game.state)
    for action in ({"action": "teleport"}, {"action": "other"}, {}, {"action": "unlock_everything", "target": "door"},
                   {"action": "use", "item": None, "target": None}, {"action": "enter_code", "code": None}):
        result = game.perform(action)
        assert not result["success"]
    for key in ("objects", "inventory", "puzzles", "escaped", "item_locations"):
        assert game.state[key] == before[key]


# ------------------------------------------------------------ fuzzing

def test_random_actions_never_corrupt_the_state_or_open_the_door():
    """10,000 random actions with wrong codes: the state stays consistent and the door stays shut."""
    rng = random.Random(2026)
    words = ["desk", "drawer", "bookshelf", "painting", "cabinet", "clock", "door", "key",
             "brass key", "flashlight", "torch", "window", "crowbar", "admin panel", "", "exit"]
    for round_number in range(20):
        game = GameEngine(codes={"drawer_code": DRAWER_CODE, "door_code": DOOR_CODE})
        for _ in range(500):
            code = "".join(rng.choice("0123456789") for _ in range(rng.choice([2, 3, 4, 5])))
            if code in (DRAWER_CODE, DOOR_CODE):
                continue
            game.perform({"action": rng.choice(ACTIONS + ("cheat",)), "target": rng.choice(words),
                          "item": rng.choice(words), "code": code})
            assert game.check_invariants() == []
        assert not game.state["escaped"]
        assert game.state["inventory"] == []          # nothing can be collected without the drawer code


def test_random_actions_with_correct_codes_keep_the_state_consistent():
    """Even when the right codes are mixed in, every reachable state obeys the rules."""
    rng = random.Random(11)
    words = ["drawer", "painting", "cabinet", "door", "key", "flashlight", "desk", ""]
    escapes = 0
    for _ in range(30):
        game = GameEngine(codes={"drawer_code": DRAWER_CODE, "door_code": DOOR_CODE})
        for _ in range(5000):
            game.perform({"action": rng.choice(ACTIONS), "target": rng.choice(words),
                          "item": rng.choice(words), "code": rng.choice([DRAWER_CODE, DOOR_CODE, "123"])})
            assert game.check_invariants() == []
        escapes += game.state["escaped"]
    assert escapes > 0                                # the game is still winnable by valid moves
