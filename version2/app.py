"""Version 2 - Streamlit interface for the reliable escape room.

Run from the project root:
    streamlit run version2/app.py

The chat works like Version 1, but every message goes through
interpreter -> engine -> narrator, and the sidebar shows the real game
state kept by Python.
"""

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from engine import GameEngine
from llm import GeminiLLM
from pipeline import play_turn

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

st.set_page_config(page_title="AI Escape Room - Version 2", page_icon="🗝️", layout="wide")


def start_new_game() -> None:
    """A fresh engine (with new random codes) and an empty conversation."""
    st.session_state.engine = GameEngine()
    st.session_state.messages = []      # what is shown in the chat
    st.session_state.llm = GeminiLLM()


def describe_turn(details: dict) -> str:
    """One line per action: what the interpreter understood and what the engine decided."""
    lines = []
    for action, result in zip(details["actions"], details["results"]):
        arguments = ", ".join(f"{key}={action[key]}" for key in ("item", "target", "code") if action[key])
        verdict = "✅ allowed" if result["success"] else "⛔ refused"
        lines.append(f"⚙️ `{action['action']}({arguments})` → {verdict} · `{result['reason']}`")
    lines.append(f"interpreter: {details['interpreter']} · narrator: {details['narrator']}")
    return "  \n".join(lines)


if "engine" not in st.session_state:
    start_new_game()

engine: GameEngine = st.session_state.engine
llm: GeminiLLM = st.session_state.llm
state = engine.public_state()

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Game status")
    st.markdown(f"**Exit door:** {'🟢 open' if state['escaped'] else '🔒 locked'}")
    st.markdown(f"**Moves:** {state['moves']}")

    st.subheader("Puzzles")
    for name, solved in state["puzzles_solved"].items():
        st.markdown(f"{'✅' if solved else '⬜'} {name}")

    st.subheader("Inventory")
    if state["inventory"]:
        for item in state["inventory"]:
            st.markdown(f"🎒 {item}")
    else:
        st.caption("You are not carrying anything.")

    st.divider()
    if st.button("🔄 Restart game", use_container_width=True):
        start_new_game()
        st.rerun()
    show_details = st.toggle("Show what the engine decided", value=False,
                             help="Shows the structured action and the engine's verdict under each reply. "
                                  "Meant for demonstrations and debugging.")

    with st.expander("How to play"):
        st.markdown(
            "Type what you want to do in plain English.\n\n"
            "- *look around*\n"
            "- *examine the bookshelf*\n"
            "- *take the key*\n"
            "- *use the key on the cabinet*\n"
            "- *enter 1234 on the door keypad*\n"
            "- *what am I carrying?*\n"
            "- *give me a hint*\n\n"
            "**Goal:** find the clues, solve the puzzles and unlock the door."
        )

    if llm.available:
        used = llm.last_model or llm.model
        st.caption(f"Narrator: Gemini ({used}). If a model hits its free-tier limit, "
                   f"the next one is used: {', '.join(llm.models[1:])}.")
    else:
        st.caption("Narrator: offline mode (no GEMINI_API_KEY found). "
                   "The game is fully playable with plain descriptions.")
    st.caption("Version 2 - Python decides what happens, the LLM tells the story.")

# ---------------------------------------------------------------- main page
st.title("🗝️ The Midnight Library")
st.caption("AI Escape Room · Version 2")

with st.chat_message("assistant"):
    st.markdown(engine.config["intro"])

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if show_details and message.get("details"):
            st.caption(describe_turn(message["details"]))

if st.session_state.pop("celebrate", False):
    st.balloons()
if state["escaped"]:
    st.success(f"🎉 You escaped the Midnight Library in {state['moves']} moves! "
               "Press **Restart game** to play again with new codes.")

player_message = st.chat_input("What do you do?", disabled=state["escaped"])

if player_message:
    with st.chat_message("user"):
        st.markdown(player_message)

    recent = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    with st.spinner("The Game Master is thinking..."):
        turn = play_turn(player_message, engine, llm, recent)

    st.session_state.messages.append({"role": "user", "content": player_message})
    st.session_state.messages.append({
        "role": "assistant",
        "content": turn["reply"],
        "details": {key: turn[key] for key in ("actions", "results", "interpreter", "narrator")},
    })
    st.session_state.celebrate = engine.state["escaped"]
    st.rerun()
