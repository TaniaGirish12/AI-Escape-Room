"""Version 2 - Streamlit interface for the reliable escape room.

Run from the project root:
    streamlit run version2/app.py

Players can type freely (interpreter -> engine -> narrator) or use the room
panel, whose buttons send structured actions straight to the engine. The
sidebar shows the real game state kept by Python.
"""

import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))                       # for the shared ui/ package

from engine import GameEngine                       # noqa: E402
from llm import GeminiLLM                           # noqa: E402
from pipeline import play_action, play_turn         # noqa: E402
from ui.theme import (GAME_MASTER_AVATAR, ITEM_ICONS, OBJECT_ICONS, PLAYER_AVATAR,  # noqa: E402
                      apply_theme, hero, object_header, role_marker, side_label, title_case,
                      victory_card)

load_dotenv(ROOT / ".env")
st.set_page_config(page_title="The Midnight Library · Version 2", page_icon="🗝️", layout="wide")
apply_theme()


# ---------------------------------------------------------------- session

def start_new_game() -> None:
    """A fresh engine (with new random codes) and an empty conversation."""
    st.session_state.engine = GameEngine()
    st.session_state.messages = []
    st.session_state.llm = GeminiLLM()
    st.session_state.toasts = []
    st.session_state.pop("queued", None)


def queue_text(text: str) -> None:
    st.session_state.queued = {"text": text}


def queue_action(action: dict, label: str) -> None:
    st.session_state.queued = {"action": action, "text": label}


def queue_code(object_id: str, key: str, name: str) -> None:
    code = "".join(ch for ch in st.session_state.get(key, "") if ch.isdigit())
    st.session_state[key] = ""
    if code:
        queue_action({"action": "enter_code", "target": object_id, "code": code},
                     f"I enter {code} on the {name}.")


def describe_turn(details: dict) -> str:
    """One line per action: what was understood and what the engine decided."""
    lines = []
    for action, result in zip(details["actions"], details["results"]):
        arguments = ", ".join(f"{key}={action[key]}" for key in ("item", "target", "code") if action[key])
        verdict = "✅ allowed" if result["success"] else "⛔ refused"
        lines.append(f"⚙️ `{action['action']}({arguments})` → {verdict} · `{result['reason']}`")
    lines.append(f"interpreter: {details['interpreter']} · narrator: {details['narrator']}")
    return "  \n".join(lines)


def progress_toasts(before: dict, engine: GameEngine) -> list[tuple[str, str]]:
    """Short notifications for new items and newly solved puzzles."""
    toasts = []
    for item_id in engine.state["inventory"]:
        if item_id not in before["inventory"]:
            toasts.append((f"{title_case(engine.items[item_id]['name'])} added to your inventory",
                           ITEM_ICONS.get(item_id, "🎒")))
    for puzzle_id, solved in engine.state["puzzles"].items():
        if solved and not before["puzzles"][puzzle_id]:
            toasts.append((f"Puzzle solved: {engine.config['puzzles'][puzzle_id]}", "🧩"))
    return toasts


if "engine" not in st.session_state:
    start_new_game()

engine: GameEngine = st.session_state.engine
llm: GeminiLLM = st.session_state.llm
state = engine.public_state()
statuses = engine.object_status()
game_over = state["escaped"]

for message, icon in st.session_state.toasts:
    st.toast(message, icon=icon)
st.session_state.toasts = []

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown('<div class="brand">🗝️ The Midnight Library</div>'
                '<div class="brand-sub">Version 2 · Python decides, the AI tells the story</div>',
                unsafe_allow_html=True)

    solved = sum(state["puzzles_solved"].values())
    side_label(f"Progress · {solved} of {len(state['puzzles_solved'])} puzzles")
    st.progress(solved / len(state["puzzles_solved"]))
    rows = "".join(
        f'<div class="puzzle-row{" done" if done else ""}"><span class="mark">{"✅" if done else "▫️"}</span>{name}</div>'
        for name, done in state["puzzles_solved"].items())
    st.markdown(rows, unsafe_allow_html=True)

    door = ("🟢", "The exit door is <b>open</b>") if state["escaped"] else ("🔒", "The exit door is <b>locked</b>")
    st.markdown(f'<div class="door-state"><span>{door[0]}</span><span>{door[1]}</span>'
                f'<span style="margin-left:auto;color:var(--muted)">{state["moves"]} moves</span></div>',
                unsafe_allow_html=True)

    side_label("Inventory")
    if engine.state["inventory"]:
        for item_id in engine.state["inventory"]:
            item = engine.items[item_id]
            st.markdown(f'<div class="item-card"><span class="icon">{ITEM_ICONS.get(item_id, "🎒")}</span>'
                        f'<div><div class="name">{title_case(item["name"])}</div>'
                        f'<div class="desc">{item["description"]}</div></div></div>', unsafe_allow_html=True)
            with st.popover(f"Use the {item['name']} on…", use_container_width=True, disabled=game_over):
                for object_id, spec in engine.objects.items():
                    st.button(f"{OBJECT_ICONS[object_id]}  {title_case(spec['name'])}",
                              key=f"use-{item_id}-{object_id}", use_container_width=True,
                              on_click=queue_action,
                              args=({"action": "use", "item": item_id, "target": object_id},
                                    f"I use the {item['name']} on the {spec['name']}."))
    else:
        st.markdown('<div class="empty">Your pockets are empty.</div>', unsafe_allow_html=True)

    side_label("Journal")
    entries = engine.journal()
    if entries:
        for entry in entries:
            name = engine.objects[entry["object"]]["name"]
            st.markdown(f'<div class="journal-entry"><b>{name}</b>{entry["text"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="empty">Clues you discover are written down here.</div>', unsafe_allow_html=True)

    st.divider()
    st.button("↻  Restart with new codes", use_container_width=True, on_click=start_new_game)
    show_details = st.toggle("Show what the engine decided", value=False,
                             help="Shows the structured action and the engine's verdict under each reply.")
    with st.expander("How to play"):
        st.markdown(
            "Type anything in plain English, or use the **room panel**.\n\n"
            "- *examine the bookshelf* · *read the note*\n"
            "- *take the key* · *use the key on the cabinet*\n"
            "- *enter 123 on the drawer* · *give me a hint*\n\n"
            "**Goal:** find the clues, solve the puzzles and unlock the door."
        )
    if llm.available:
        st.caption(f"Narrator: Gemini · {llm.last_model or llm.model}. Falls back to "
                   f"{', '.join(llm.models[1:])} if a free-tier limit is reached.")
    else:
        st.caption("Offline mode: no GEMINI_API_KEY found. The game is fully playable with plain descriptions.")

# ---------------------------------------------------------------- main
hero("The Midnight Library",
     "You wake on a cold wooden floor. Somewhere behind you, a lock clicks shut.", "Version 2 · Reliable")

chat_col, room_col = st.columns([1.65, 1], gap="large")

with room_col:
    st.markdown('<div class="panel-title">The room</div>', unsafe_allow_html=True)
    quick = st.container(key="quick-actions").columns(3)
    quick[0].button("👀 Look", use_container_width=True, disabled=game_over, on_click=queue_action,
                    args=({"action": "look"}, "I look around the room."))
    quick[1].button("💡 Hint", use_container_width=True, disabled=game_over, on_click=queue_action,
                    args=({"action": "hint"}, "Can I have a hint?"))
    quick[2].button("🎒 Bag", use_container_width=True, disabled=game_over, on_click=queue_action,
                    args=({"action": "inventory"}, "What am I carrying?"))

    reachable = dict()
    for item_id, container in engine.reachable_items():
        reachable.setdefault(container, []).append(item_id)

    def object_tile(object_id: str, wide: bool = False) -> None:
        spec = engine.objects[object_id]
        with st.container(border=True):
            st.markdown(object_header(object_id, spec["name"], statuses[object_id]), unsafe_allow_html=True)
            lock = spec.get("lock", {})
            has_keypad = lock.get("type") == "code" and statuses[object_id] == "locked"
            buttons = st.columns(2) if (has_keypad and wide) else [st.container(), st.container()]
            buttons[0].button("Inspect", key=f"inspect-{object_id}", use_container_width=True, disabled=game_over,
                              on_click=queue_action,
                              args=({"action": "examine", "target": object_id}, f"I examine the {spec['name']}."))
            if has_keypad:
                digits = len(engine.secrets[lock["secret"]])
                label = "⌨️ Keypad" if object_id == "door" else "🔢 Enter code"
                with buttons[1].popover(label, use_container_width=True, disabled=game_over):
                    st.text_input(f"Enter {digits} digits", key=f"code-{object_id}", max_chars=digits,
                                  placeholder="•" * digits,
                                  on_change=queue_code, args=(object_id, f"code-{object_id}", spec["name"]))
                    st.caption("Press Enter to try the code.")
            for item_id in reachable.get(object_id, []):
                item = engine.items[item_id]
                st.button(f"✋ Take {item['name']}", key=f"take-{item_id}", use_container_width=True,
                          type="primary", on_click=queue_action,
                          args=({"action": "take", "target": item_id}, f"I take the {item['name']}."))

    others = [object_id for object_id in engine.objects if object_id != "door"]
    for start in range(0, len(others), 2):
        for column, object_id in zip(st.columns(2), others[start:start + 2]):
            with column:
                object_tile(object_id)
    object_tile("door", wide=True)      # the exit gets a full-width tile

with chat_col:
    with st.chat_message("assistant", avatar=GAME_MASTER_AVATAR):
        role_marker("assistant")
        st.markdown(engine.config["intro"])

    for message in st.session_state.messages:
        avatar = PLAYER_AVATAR if message["role"] == "user" else GAME_MASTER_AVATAR
        with st.chat_message(message["role"], avatar=avatar):
            role_marker(message["role"])
            st.markdown(message["content"])
            if show_details and message.get("details"):
                st.caption(describe_turn(message["details"]))

    if state["escaped"]:
        if st.session_state.pop("celebrate", False):
            st.balloons()
        failed = sum(engine.state["failed_code_attempts"].values())
        victory_card(state["moves"], {"Wrong codes": failed, "Clues found": len(engine.journal())})
        st.button("Play again with new codes", type="primary", use_container_width=True, on_click=start_new_game)

    live_turn = st.container()          # the new message appears here, above the input box
    typed = st.chat_input("What do you do?  e.g. examine the bookshelf", disabled=game_over)
    pending = {"text": typed} if typed else st.session_state.pop("queued", None)

    if pending and not game_over:
        with live_turn, st.chat_message("user", avatar=PLAYER_AVATAR):
            role_marker("user")
            st.markdown(pending["text"])

        recent = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
        before = {"inventory": list(engine.state["inventory"]), "puzzles": dict(engine.state["puzzles"])}
        with live_turn, st.spinner("The Game Master is thinking…"):
            if "action" in pending:
                turn = play_action(pending["action"], pending["text"], engine, llm, recent)
            else:
                turn = play_turn(pending["text"], engine, llm, recent)

        st.session_state.messages.append({"role": "user", "content": pending["text"]})
        st.session_state.messages.append({
            "role": "assistant", "content": turn["reply"],
            "details": {key: turn[key] for key in ("actions", "results", "interpreter", "narrator")},
        })
        st.session_state.toasts = progress_toasts(before, engine)
        st.session_state.celebrate = engine.state["escaped"]
        st.rerun()
