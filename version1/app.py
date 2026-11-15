"""Version 1 - Streamlit chat interface for the LLM-only escape room.

Run from the project root:
    streamlit run version1/app.py

The room panel only sends text messages to the Game Master. Version 1 keeps
no game state, so it cannot show what is locked or open: that knowledge
exists only inside the conversation.
"""

import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))                       # for the shared ui/ package

from game_master import ESCAPE_TOKEN, INTRO, GameMasterError, ask_game_master, get_client  # noqa: E402
from ui.theme import (GAME_MASTER_AVATAR, PLAYER_AVATAR, apply_theme, hero,  # noqa: E402
                      object_header, role_marker, side_label, victory_card)

load_dotenv(ROOT / ".env")
st.set_page_config(page_title="The Midnight Library · Version 1", page_icon="🗝️", layout="wide")
apply_theme()

# The objects the player is told about in the introduction.
ROOM = [("desk", "desk"), ("drawer", "drawer"), ("bookshelf", "bookshelf"), ("painting", "painting"),
        ("cabinet", "glass cabinet"), ("clock", "grandfather clock"), ("door", "door")]
CODE_LOCKS = {"drawer": 3, "door": 4}


def start_new_game() -> None:
    """Reset the session: an empty conversation and a locked door."""
    st.session_state.history = []      # the only "memory" this version has
    st.session_state.escaped = False
    st.session_state.pop("queued", None)


def queue_text(text: str) -> None:
    st.session_state.queued = text


def queue_code(object_id: str, key: str, name: str) -> None:
    code = "".join(ch for ch in st.session_state.get(key, "") if ch.isdigit())
    st.session_state[key] = ""
    if code:
        queue_text(f"I enter {code} on the {name}.")


if "history" not in st.session_state:
    start_new_game()
game_over = st.session_state.escaped

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown('<div class="brand">🗝️ The Midnight Library</div>'
                '<div class="brand-sub">Version 1 · the AI runs the whole game</div>',
                unsafe_allow_html=True)
    side_label("How to play")
    st.markdown(
        "Type what you want to do in plain English, or use the buttons in the room panel.\n\n"
        "- *examine the bookshelf*\n"
        "- *take the key*\n"
        "- *use the key on the cabinet*\n"
        "- *enter 1234 on the door keypad*\n"
        "- *give me a hint*\n\n"
        "**Goal:** find the clues, solve the puzzles and unlock the door."
    )
    side_label("About this version")
    st.markdown('<div class="note-card">There is <b>no game state</b> in Version 1. The Game Master '
                'remembers progress only through the conversation, so this screen cannot show your '
                'inventory or which locks are open. Version 2 fixes this.</div>', unsafe_allow_html=True)
    st.divider()
    st.button("↻  Restart game", use_container_width=True, on_click=start_new_game)

# ---------------------------------------------------------------- main
hero("The Midnight Library",
     "You wake on a cold wooden floor. Somewhere behind you, a lock clicks shut.", "Version 1 · LLM only")

chat_col, room_col = st.columns([1.65, 1], gap="large")

with room_col:
    st.markdown('<div class="panel-title">The room</div>', unsafe_allow_html=True)
    quick = st.container(key="quick-actions").columns(3)
    quick[0].button("👀 Look", use_container_width=True, disabled=game_over,
                    on_click=queue_text, args=("I look around the room.",))
    quick[1].button("💡 Hint", use_container_width=True, disabled=game_over,
                    on_click=queue_text, args=("Can I have a hint?",))
    quick[2].button("🎒 Bag", use_container_width=True, disabled=game_over,
                    on_click=queue_text, args=("What am I carrying?",))

    def object_tile(object_id: str, name: str, wide: bool = False) -> None:
        with st.container(border=True):
            st.markdown(object_header(object_id, name, "unknown"), unsafe_allow_html=True)
            buttons = st.columns(2) if (wide and object_id in CODE_LOCKS) else [st.container(), st.container()]
            buttons[0].button("Inspect", key=f"inspect-{object_id}", use_container_width=True, disabled=game_over,
                              on_click=queue_text, args=(f"I examine the {name}.",))
            if object_id in CODE_LOCKS:
                digits = CODE_LOCKS[object_id]
                label = "⌨️ Keypad" if object_id == "door" else "🔢 Enter code"
                with buttons[1].popover(label, use_container_width=True, disabled=game_over):
                    st.text_input(f"Enter {digits} digits", key=f"code-{object_id}", max_chars=digits,
                                  placeholder="•" * digits,
                                  on_change=queue_code, args=(object_id, f"code-{object_id}", name))
                    st.caption("Press Enter to try the code.")

    others = [entry for entry in ROOM if entry[0] != "door"]
    for start in range(0, len(others), 2):
        for column, (object_id, name) in zip(st.columns(2), others[start:start + 2]):
            with column:
                object_tile(object_id, name)
    object_tile("door", "door", wide=True)

with chat_col:
    with st.chat_message("assistant", avatar=GAME_MASTER_AVATAR):
        role_marker("assistant")
        st.markdown(INTRO)

    for message in st.session_state.history:
        avatar = PLAYER_AVATAR if message["role"] == "user" else GAME_MASTER_AVATAR
        with st.chat_message(message["role"], avatar=avatar):
            role_marker(message["role"])
            st.markdown(message["content"])

    if game_over:
        if st.session_state.pop("celebrate", False):
            st.balloons()
        victory_card(len(st.session_state.history) // 2)
        st.button("Play again", type="primary", use_container_width=True, on_click=start_new_game)

    live_turn = st.container()
    typed = st.chat_input("What do you do?  e.g. examine the bookshelf", disabled=game_over)
    player_message = typed or st.session_state.pop("queued", None)

    if player_message and not game_over:
        with live_turn, st.chat_message("user", avatar=PLAYER_AVATAR):
            role_marker("user")
            st.markdown(player_message)
        try:
            with live_turn, st.spinner("The Game Master is thinking…"):
                reply = ask_game_master(get_client(), st.session_state.history, player_message)
        except GameMasterError as error:
            text = str(error)
            if "RESOURCE_EXHAUSTED" in text or "429" in text:
                reason = "The free Gemini quota for this model is used up for now."
            elif "UNAVAILABLE" in text or "503" in text or "DEADLINE" in text:
                reason = "The Gemini model is overloaded at the moment."
            else:
                reason = "The Game Master could not be reached."
            with live_turn:
                st.warning(f"{reason} Wait a moment and send your message again, or set another "
                           "model in `GEMINI_MODEL` in `.env`.", icon="⏳")
                with st.expander("Technical details"):
                    st.code(text, language=None)
            st.stop()

        # The LLM tells us the game is over by printing the escape marker.
        if ESCAPE_TOKEN in reply:
            st.session_state.escaped = True
            st.session_state.celebrate = True
            reply = reply.replace(ESCAPE_TOKEN, "").strip()

        st.session_state.history.append({"role": "user", "content": player_message})
        st.session_state.history.append({"role": "assistant", "content": reply})
        st.rerun()
