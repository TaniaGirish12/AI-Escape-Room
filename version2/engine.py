"""Version 2 - the game engine.

This module is the single source of truth for the game. It keeps the game
state in a plain dictionary and decides, with ordinary Python code, whether
an action succeeds. No LLM is involved here.

The secret codes are kept in `self.secrets`, separate from the state, and are
never passed to the LLM unless the player has legitimately revealed them.
"""

import json
import random
import re
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "game_config.json"

ACTIONS = ("look", "examine", "take", "open", "use", "enter_code", "inventory", "hint", "other")


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


class GameEngine:
    """Holds the game state and validates every player action."""

    def __init__(self, config: dict | None = None, seed: int | None = None,
                 codes: dict | None = None):
        self.config = config or load_config()
        self.objects = self.config["objects"]
        self.items = self.config["items"]

        # Secret codes are generated for every new game, so they cannot be
        # memorised from an earlier game or guessed from the source code.
        rng = random.Random(seed)
        self.secrets = {}
        for name, spec in self.config["codes"].items():
            if codes and name in codes:
                self.secrets[name] = str(codes[name])
            else:
                self.secrets[name] = "".join(str(rng.randint(1, 9)) for _ in range(spec["length"]))

        self.state = self._initial_state()

    # ------------------------------------------------------------ state

    def _initial_state(self) -> dict:
        objects = {}
        item_locations = {}
        for object_id, spec in self.objects.items():
            status = {"examined": False}
            if "lock" in spec:
                status["locked"] = True
            if "reveal" in spec:
                status["revealed"] = False
            objects[object_id] = status
            for item_id in spec.get("contains", []):
                item_locations[item_id] = object_id
        return {
            "objects": objects,
            "item_locations": item_locations,   # item -> container, or "inventory"
            "inventory": [],
            "puzzles": {puzzle_id: False for puzzle_id in self.config["puzzles"]},
            "failed_code_attempts": {
                object_id: 0 for object_id, spec in self.objects.items()
                if spec.get("lock", {}).get("type") == "code"
            },
            "escaped": False,
            "moves": 0,
            "log": [],
        }

    def public_state(self) -> dict:
        """The part of the state that is safe to show to the player and the LLM.

        It contains no secret codes and no items the player has not seen yet.
        """
        objects = {}
        for object_id, status in self.state["objects"].items():
            spec = self.objects[object_id]
            if "lock" in spec:
                objects[spec["name"]] = "locked" if status["locked"] else "open"
            elif "reveal" in spec:
                objects[spec["name"]] = "hidden message revealed" if status["revealed"] else "normal"
            else:
                objects[spec["name"]] = "examined" if status["examined"] else "not examined yet"
        return {
            "objects": objects,
            "inventory": [self.items[item_id]["name"] for item_id in self.state["inventory"]],
            "puzzles_solved": {
                self.config["puzzles"][puzzle_id]: solved
                for puzzle_id, solved in self.state["puzzles"].items()
            },
            "door": "open" if self.state["escaped"] else "locked",
            "escaped": self.state["escaped"],
            "moves": self.state["moves"],
        }

    def protected_secrets(self) -> list[str]:
        """Codes the player has not earned yet. They must never appear in a reply."""
        protected = []
        if not self.state["puzzles"]["drawer_code"]:
            protected.append(self.secrets["drawer_code"])
        if not self.state["puzzles"]["painting_uv"]:
            protected.append(self.secrets["door_code"])
        return protected

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _normalise(text) -> str:
        text = re.sub(r"[^a-z0-9 ]", " ", str(text or "").lower().replace("_", " "))
        text = re.sub(r"\b(the|a|an|my|that|this|some)\b", " ", text)
        return " ".join(text.split())

    def _lookup(self, text, table: dict) -> str | None:
        wanted = self._normalise(text)
        if not wanted:
            return None
        for entry_id, spec in table.items():
            names = [entry_id, spec["name"], *spec.get("aliases", [])]
            if wanted in (self._normalise(name) for name in names):
                return entry_id
        return None

    def find_object(self, text) -> str | None:
        return self._lookup(text, self.objects)

    def find_item(self, text) -> str | None:
        return self._lookup(text, self.items)

    def _is_open(self, object_id: str) -> bool:
        return self.state["objects"][object_id].get("locked") is False

    def _item_visible(self, item_id: str) -> bool:
        """An item can be seen/taken only when its container has been opened."""
        location = self.state["item_locations"][item_id]
        return location != "inventory" and self._is_open(location)

    def _item_behind_glass(self, item_id: str) -> bool:
        """The item is on show inside a locked container: visible, but not reachable."""
        location = self.state["item_locations"][item_id]
        return (location != "inventory" and not self._is_open(location)
                and self.objects[location].get("contents_visible", False))

    def _fill(self, text: str) -> str:
        """Insert the generated codes into a description from the config file."""
        drawer = self.secrets["drawer_code"]
        return text.format(
            book_red=drawer[0], book_green=drawer[1], book_blue=drawer[2],
            door_code=self.secrets["door_code"],
        )

    def _contents_text(self, object_id: str) -> str:
        left = [self.items[item_id]["name"] for item_id in self.objects[object_id].get("contains", [])
                if self.state["item_locations"][item_id] == object_id]
        if left:
            return " Inside you can see: " + ", ".join(left) + "."
        return " It is empty."

    @staticmethod
    def _result(action, success, reason, message, target=None, item=None) -> dict:
        return {"action": action, "target": target, "item": item,
                "success": success, "reason": reason, "message": message}

    # ------------------------------------------------------------ entry point

    def perform(self, action: dict) -> dict:
        """Validate and apply one action. Always returns a result dictionary.

        `action` looks like {"action": "use", "item": "key", "target": "cabinet", "code": ""}.
        Whatever it contains, the state only changes if the rules below allow it.
        """
        kind = action.get("action")
        if kind not in ACTIONS:
            kind = "other"
        target = action.get("target") or ""
        item = action.get("item") or ""
        code = action.get("code") or ""

        if self.state["escaped"]:
            result = self._result(kind, False, "game_over",
                                  "You have already escaped. Restart the game to play again.")
        elif kind == "look":
            result = self._look()
        elif kind == "examine":
            result = self._examine(target or item)
        elif kind == "take":
            result = self._take(target or item)
        elif kind == "open":
            result = self._open(target)
        elif kind == "use":
            result = self._use(item, target)
        elif kind == "enter_code":
            result = self._enter_code(target, code)
        elif kind == "inventory":
            result = self._inventory()
        elif kind == "hint":
            result = self._hint()
        else:
            result = self._result("other", False, "no_game_action",
                                  "Nothing in the room changes.")

        # The log keeps the precise internal reason; the returned result does not.
        internal_reason = result.pop("internal_reason", result["reason"])
        self.state["moves"] += 1
        self.state["log"].append({"action": result["action"], "target": result["target"],
                                  "item": result["item"], "success": result["success"],
                                  "reason": internal_reason})
        return result

    # ------------------------------------------------------------ actions

    def _look(self) -> dict:
        return self._result("look", True, "ok", self.config["room_description"])

    def _unknown(self, action: str, text) -> dict:
        name = str(text).strip() or "that"
        if self.find_item(text):
            # A real item the player has not uncovered yet: do not confirm that it exists.
            return self._result(action, False, "unknown_object",
                                "You cannot see anything like that here.")
        return self._result(action, False, "unknown_object",
                            f"There is nothing like \"{name}\" in this room.", target=name)

    def _examine(self, text) -> dict:
        if not self._normalise(text):
            return self._look()

        object_id = self.find_object(text)
        if object_id:
            spec, status = self.objects[object_id], self.state["objects"][object_id]
            status["examined"] = True
            if "lock" in spec:
                if status["locked"]:
                    message = spec["examine_locked"]
                else:
                    message = spec["examine_open"] + self._contents_text(object_id)
            elif status.get("revealed"):
                message = spec["examine_revealed"]
            else:
                message = spec["examine"]
            return self._result("examine", True, "ok", self._fill(message), target=object_id)

        item_id = self.find_item(text)
        if item_id and item_id in self.state["inventory"]:
            return self._result("examine", True, "ok", self.items[item_id]["description"], target=item_id)
        if item_id and self._item_visible(item_id):
            container = self.objects[self.state["item_locations"][item_id]]["name"]
            return self._result("examine", True, "ok",
                                f"{self.items[item_id]['description']} It is lying in the {container}.",
                                target=item_id)
        if item_id and self._item_behind_glass(item_id):
            container = self.objects[self.state["item_locations"][item_id]]["name"]
            return self._result("examine", True, "ok",
                                f"You can see it through the glass of the locked {container}, "
                                "but you cannot reach it.", target=item_id)
        # Items that exist but have not been uncovered are treated like any
        # other unknown thing, so the reply does not confirm that they exist.
        return self._unknown("examine", text)

    def _take(self, text) -> dict:
        item_id = self.find_item(text)
        if item_id:
            name = self.items[item_id]["name"]
            if item_id in self.state["inventory"]:
                return self._result("take", False, "already_have",
                                    f"You are already carrying the {name}.", target=item_id)
            if self._item_visible(item_id):
                self.state["inventory"].append(item_id)
                self.state["item_locations"][item_id] = "inventory"
                return self._result("take", True, "ok",
                                    f"You take the {name}. It is now in your inventory.", target=item_id)
            if self._item_behind_glass(item_id):
                container = self.objects[self.state["item_locations"][item_id]]["name"]
                return self._result("take", False, "container_locked",
                                    f"The {name} is behind the glass of the locked {container}. "
                                    "You cannot reach it.", target=item_id)
            return self._result("take", False, "not_available",
                                "You cannot see anything like that within reach.", target=str(text))

        object_id = self.find_object(text)
        if object_id:
            return self._result("take", False, "not_takeable",
                                f"The {self.objects[object_id]['name']} cannot be picked up.", target=object_id)
        return self._unknown("take", text)

    def _open(self, text) -> dict:
        object_id = self.find_object(text)
        if not object_id:
            if self.find_item(text):
                return self._result("open", False, "nothing_to_open", "That is not something you can open.")
            return self._unknown("open", text)

        spec, status = self.objects[object_id], self.state["objects"][object_id]
        name = spec["name"]
        if "lock" not in spec:
            return self._result("open", False, "nothing_to_open",
                                f"There is nothing to open on the {name}.", target=object_id)
        if not status["locked"]:
            return self._result("open", False, "already_open",
                                f"The {name} is already open." + self._contents_text(object_id), target=object_id)

        lock = spec["lock"]
        if lock["type"] == "key":
            if lock["item"] in self.state["inventory"]:
                return self._use(lock["item"], object_id)   # the player holds the right key
            return self._result("open", False, "locked_needs_key",
                                f"The {name} is locked. It will not open without the right key.", target=object_id)

        digits = len(self.secrets[lock["secret"]])
        return self._result("open", False, "locked_needs_code",
                            f"The {name} is locked. It needs a {digits}-digit code.", target=object_id)

    def _use(self, item_text, target_text) -> dict:
        item_id = self.find_item(item_text)
        shown_item = str(item_text).strip() or "that"
        # Inventory check comes first: an item that was never collected cannot
        # be used, whatever the player says about it.
        if not item_id:
            return self._result("use", False, "item_not_in_inventory",
                                f"You are not carrying anything like \"{shown_item}\".", item=shown_item)
        if item_id not in self.state["inventory"]:
            # A real item that was not collected: the reply does not name it.
            return self._result("use", False, "item_not_in_inventory",
                                "You are not carrying anything like that.")

        item_name = self.items[item_id]["name"]
        if not self._normalise(target_text):
            return self._result("use", False, "needs_target",
                                f"What do you want to use the {item_name} on?", item=item_id)

        object_id = self.find_object(target_text)
        if not object_id:
            return self._unknown("use", target_text)

        spec, status = self.objects[object_id], self.state["objects"][object_id]
        lock = spec.get("lock", {})
        if lock.get("type") == "key" and lock["item"] == item_id:
            if not status["locked"]:
                return self._result("use", False, "already_open",
                                    f"The {spec['name']} is already open.", target=object_id, item=item_id)
            status["locked"] = False
            self.state["puzzles"][lock["puzzle"]] = True
            return self._result("use", True, "unlocked",
                                spec["unlock_text"] + self._contents_text(object_id),
                                target=object_id, item=item_id)

        reveal = spec.get("reveal", {})
        if reveal.get("item") == item_id:
            status["revealed"] = True
            self.state["puzzles"][reveal["puzzle"]] = True
            return self._result("use", True, "revealed", self._fill(spec["reveal_text"]),
                                target=object_id, item=item_id)

        return self._result("use", False, "no_effect",
                            f"Using the {item_name} on the {spec['name']} does nothing.",
                            target=object_id, item=item_id)

    def _enter_code(self, target_text, code) -> dict:
        code = re.sub(r"\D", "", str(code))
        object_id = self.find_object(target_text)

        if not object_id and not self._normalise(target_text):
            # No target given: use the one locked code lock that fits the code length.
            fitting = [oid for oid, spec in self.objects.items()
                       if spec.get("lock", {}).get("type") == "code"
                       and self.state["objects"][oid]["locked"]
                       and len(self.secrets[spec["lock"]["secret"]]) == len(code)]
            if len(fitting) != 1:
                return self._result("enter_code", False, "needs_target",
                                    "Where do you want to enter that code?")
            object_id = fitting[0]
        if not object_id:
            return self._unknown("enter_code", target_text)

        spec, status = self.objects[object_id], self.state["objects"][object_id]
        name = spec["name"]
        lock = spec.get("lock", {})
        if lock.get("type") != "code":
            return self._result("enter_code", False, "no_code_lock",
                                f"The {name} has no code lock.", target=object_id)
        if not status["locked"]:
            return self._result("enter_code", False, "already_open",
                                f"The {name} is already open.", target=object_id)

        secret = self.secrets[lock["secret"]]
        if len(code) != len(secret):
            return self._result("enter_code", False, "bad_code_format",
                                f"The lock on the {name} needs exactly {len(secret)} digits.", target=object_id)

        # The exit also requires the earlier puzzles. A lucky guess is rejected
        # with exactly the same result as a wrong code, so nothing is given away
        # to the player or to the LLM. Only the internal log knows the difference.
        prerequisites_met = all(self.state["puzzles"][p] for p in lock.get("requires_puzzles", []))
        if code != secret or not prerequisites_met:
            self.state["failed_code_attempts"][object_id] += 1
            result = self._result("enter_code", False, "code_rejected",
                                  f"The code {code} is rejected. The {name} stays locked.", target=object_id)
            result["internal_reason"] = "wrong_code" if code != secret else "prerequisites_missing"
            return result

        status["locked"] = False
        self.state["puzzles"][lock["puzzle"]] = True
        if spec.get("final_exit"):
            self.state["escaped"] = True
            return self._result("enter_code", True, "escaped", spec["unlock_text"], target=object_id)
        return self._result("enter_code", True, "unlocked",
                            spec["unlock_text"] + self._contents_text(object_id), target=object_id)

    def _inventory(self) -> dict:
        names = [self.items[item_id]["name"] for item_id in self.state["inventory"]]
        message = "You are carrying: " + ", ".join(names) + "." if names else "You are not carrying anything."
        return self._result("inventory", True, "ok", message)

    def _hint(self) -> dict:
        """A nudge towards the next unsolved step. Hints never contain a code."""
        puzzles, hints = self.state["puzzles"], self.config["hints"]
        if not puzzles["drawer_code"]:
            key = "drawer_code"
        elif "brass_key" not in self.state["inventory"] and not puzzles["cabinet_key"]:
            key = "take_brass_key"
        elif not puzzles["cabinet_key"]:
            key = "cabinet_key"
        elif "uv_flashlight" not in self.state["inventory"]:
            key = "take_uv_flashlight"
        elif not puzzles["painting_uv"]:
            key = "painting_uv"
        else:
            key = "door_code"
        return self._result("hint", True, "ok", "Hint: " + hints[key])

    # ------------------------------------------------------------ consistency

    def check_invariants(self) -> list[str]:
        """Return a list of rule violations in the current state (empty = consistent).

        Used by the tests to prove that no sequence of actions can corrupt the game.
        """
        state, problems = self.state, []
        puzzles = state["puzzles"]
        for item_id in state["inventory"]:
            if state["item_locations"][item_id] != "inventory":
                problems.append(f"{item_id} is in the inventory and in a container")
        for item_id, location in state["item_locations"].items():
            if location == "inventory" and item_id not in state["inventory"]:
                problems.append(f"{item_id} is lost")
        if "brass_key" in state["inventory"] and not puzzles["drawer_code"]:
            problems.append("brass key collected although the drawer was never opened")
        if puzzles["cabinet_key"] and not puzzles["drawer_code"]:
            problems.append("cabinet unlocked without the key from the drawer")
        if "uv_flashlight" in state["inventory"] and not puzzles["cabinet_key"]:
            problems.append("flashlight collected although the cabinet was never opened")
        if puzzles["painting_uv"] and not puzzles["cabinet_key"]:
            problems.append("hidden message revealed without the flashlight")
        if state["escaped"] != puzzles["door_code"]:
            problems.append("escaped flag and door puzzle disagree")
        if state["escaped"] and not all(puzzles.values()):
            problems.append("escaped without solving every puzzle")
        for object_id, spec in self.objects.items():
            lock = spec.get("lock")
            if lock and state["objects"][object_id]["locked"] == puzzles[lock["puzzle"]]:
                problems.append(f"{object_id} lock and puzzle status disagree")
        return problems
