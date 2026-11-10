"""Version 1 - Streamlit chat interface for the LLM-only escape room.

Run from the project root:
    streamlit run version1/app.py
"""

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from game_master import ESCAPE_TOKEN, INTRO, GameMasterError, ask_game_master, get_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

st.set_page_config(page_title="AI Escape Room - Version 1", page_icon="🗝️")


def start_new_game() -> None:
    """Reset the session: an empty conversation and a locked door."""
    st.session_state.history = []      # the only "memory" this version has
    st.session_state.escaped = False


if "history" not in st.session_state:
    start_new_game()

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("How to play")
    st.markdown(
        "You are locked in a library. Type what you want to do in plain "
        "English and the AI Game Master will tell you what happens.\n\n"
        "**Things you can try**\n"
        "- *look around*\n"
        "- *examine the bookshelf*\n"
        "- *take the key*\n"
        "- *use the key on the cabinet*\n"
        "- *enter 1234 on the door keypad*\n"
        "- *give me a hint*\n\n"
        "**Goal:** find the clues, solve the puzzles and unlock the door."
    )
    if st.button("🔄 Restart game", use_container_width=True):
        start_new_game()
        st.rerun()
    st.caption("Version 1 - the LLM runs the whole game from a single prompt.")

# ---------------------------------------------------------------- main page
st.title("🗝️ The Midnight Library")
st.caption("AI Escape Room · Version 1")

with st.chat_message("assistant"):
    st.markdown(INTRO)

for message in st.session_state.history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if st.session_state.escaped:
    st.success("🎉 You escaped the Midnight Library! Press **Restart game** to play again.")

player_message = st.chat_input(
    "What do you do?", disabled=st.session_state.escaped
)

if player_message:
    with st.chat_message("user"):
        st.markdown(player_message)

    try:
        with st.spinner("The Game Master is thinking..."):
            reply = ask_game_master(get_client(), st.session_state.history, player_message)
    except GameMasterError as error:
        st.error(str(error))
        st.stop()

    # The LLM tells us the game is over by printing the escape marker.
    if ESCAPE_TOKEN in reply:
        st.session_state.escaped = True
        reply = reply.replace(ESCAPE_TOKEN, "").strip()

    st.session_state.history.append({"role": "user", "content": player_message})
    st.session_state.history.append({"role": "assistant", "content": reply})
    st.rerun()
