"""Version 1 - the LLM is the whole game.

Everything the game knows (the room, the puzzles and their solutions, the
rules) is written into one system prompt. The full conversation is sent to
Gemini on every turn and Gemini decides what happens next.

There is no game state in Python: the conversation history is the only memory.
"""

import os

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-3.6-flash"

# The Game Master is told to print this marker when the player gets out.
# The app looks for it to know that the game is over.
ESCAPE_TOKEN = "[ESCAPED]"

INTRO = (
    "You wake up with your cheek on a cold wooden floor. A single green-shaded "
    "lamp lights a private library you have never seen before. Somewhere behind "
    "you a lock clicks shut.\n\n"
    "Around you are a **desk** with a drawer, a tall **bookshelf**, a large "
    "**painting**, a glass **cabinet**, a silent **grandfather clock** and a "
    "heavy oak **door** with a keypad.\n\n"
    "What do you do?"
)

SYSTEM_PROMPT = f"""
You are the Game Master of a text-based escape-room game called "The Midnight Library".
The player is locked inside a private library and must escape by solving puzzles.

THE ROOM (these are the only things in the room)
- Desk: an old oak desk with a green-shaded lamp. A handwritten note is pinned under
  the lamp: "Knowledge has colours. Read red first, then green, then blue."
  The desk has one drawer.
- Drawer: part of the desk, locked with a three-digit combination lock.
  The combination is 392. Inside the drawer is a small brass key.
- Bookshelf: hundreds of dusty brown books. Three books look new and stick out:
  a blue book marked "Vol. 2", a red book marked "Vol. 3" and a green book marked "Vol. 9".
  (Read in the order red, green, blue they give the drawer combination 392.)
- Glass cabinet: locked with a small brass lock. Through the glass the player can see
  a strange torch with a violet lens. The brass key from the drawer opens the cabinet.
  The torch is a UV flashlight and can be taken once the cabinet is open.
- Grandfather clock: stopped at midnight. The pendulum is engraved with the words
  "What the eye cannot see, violet light will free."
- Painting: a large oil painting of a night sky over a lighthouse. Nothing unusual can be
  seen in normal light. When the UV flashlight is shone on it, four glowing digits
  appear in the corner: 7146.
- Door: a heavy oak door with a four-digit electronic keypad. The code is 7146.

HOW THE GAME IS SOLVED
1. Read the note on the desk and look at the three coloured books -> drawer code 392.
2. Open the drawer with 392 and take the brass key.
3. Use the brass key to open the glass cabinet and take the UV flashlight.
4. Shine the UV flashlight on the painting to reveal the door code 7146.
5. Enter 7146 on the door keypad to escape.

RULES
- Describe what the player sees and what happens when they act, in 2-4 sentences.
- Speak to the player as "you". Keep an atmospheric but clear tone.
- Only describe objects that are listed above.
- Do not give away codes or solutions directly. The player has to find them.
- If the player asks for a hint, give a small nudge without the answer.
- The player must collect an item before using it.
- Remember what the player has already done and keep the story consistent.
- When the player enters the correct code 7146 on the door, describe the escape and
  end your message with the exact text {ESCAPE_TOKEN}
- Never write {ESCAPE_TOKEN} in any other situation.

The player has already been shown this introduction:
{INTRO}
""".strip()


class GameMasterError(Exception):
    """Raised when the LLM could not be reached or returned nothing."""


def get_client() -> genai.Client:
    """Create the Gemini client from the GEMINI_API_KEY environment variable."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_api_key_here":
        raise GameMasterError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return genai.Client(api_key=api_key)


def ask_game_master(client: genai.Client, history: list[dict], player_message: str) -> str:
    """Send the whole conversation to Gemini and return the Game Master's reply.

    history is a list of {"role": "user" | "assistant", "content": str}.
    """
    contents = []
    for message in history:
        role = "user" if message["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=message["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=player_message)]))

    try:
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )
    except Exception as error:
        raise GameMasterError(f"The Game Master could not be reached: {error}") from error

    text = (response.text or "").strip()
    if not text:
        raise GameMasterError("The Game Master returned an empty answer. Please try again.")
    return text
