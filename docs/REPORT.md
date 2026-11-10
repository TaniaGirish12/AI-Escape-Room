# AI-Powered Escape Room — Project Report

**Course:** Deep Learning & Generative AI · **Mini Project 1** · **Author:** Tania Girish

## 1. Goal

The goal was to build a text escape-room game where a Large Language Model (Google Gemini) acts
as the Game Master. The player is locked in a room and types what they want to do in plain English.
The Game Master describes the room, reacts to the player's actions and recognises when the player
has escaped. The project was built in two versions. Version 1 is a working LLM game. Version 2
makes the game reliable, so that the LLM cannot be talked into breaking the rules.

## 2. Game design — "The Midnight Library"

The player wakes up in a private library. The room has seven interactive objects: a **desk** with a
note, a locked **drawer**, a **bookshelf**, a glass **cabinet**, a **grandfather clock**, a
**painting** and the exit **door** with a keypad. There are two collectable items, a **brass key**
and a **UV flashlight**. The solution is a chain of four puzzles, where each step depends on the
one before it:

1. **Colour puzzle.** The note says *"Read red first, then green, then blue."* Three new books on
   the shelf are marked with volume numbers. Read in that colour order, they give the drawer's
   three-digit code.
2. **Key puzzle.** The drawer holds a brass key, which opens the glass cabinet.
3. **Hidden message.** The cabinet holds a UV flashlight. The clock's pendulum says
   *"What the eye cannot see, violet light will free"*. Shining the light on the painting shows four
   glowing digits.
4. **Final escape.** Entering those four digits on the keypad opens the door.

The interface uses Streamlit. It shows an introduction, a "How to play" section with example
commands, a chat window and a **Restart** button. Version 2 also shows a live status panel with
door status, solved puzzles and inventory.

## 3. Version 1 — the LLM is the whole game

**Implementation.** Version 1 has two short files. `game_master.py` holds one system prompt that
describes the room, every object, the full solution with both codes, and the rules ("only describe
listed objects", "don't reveal codes", "the player must collect an item before using it"). On every
turn the complete chat history is sent to Gemini together with the new message. The model's reply is
shown as it is. When the player enters the right door code, the model is told to end its message
with the marker `[ESCAPED]`, and `app.py` treats that marker as the win condition.

**What works.** Version 1 meets the functional brief with very little code. The descriptions are
varied and atmospheric, free-form actions ("I knock on the painting") get a natural answer, and an
honest player can finish the game.

**Problems.** All of the problems come from one design decision: the LLM is both the storyteller
and the referee, and the only memory is text.

- **The secrets are in the prompt.** Both codes are sent to the model on every turn. Only one
  instruction stands between the player and the solution, and prompt injection can beat it.
- **No real state.** Progress exists only as chat text, and the player's own claims ("I already
  opened the drawer") become part of that text. The model cannot check them. In long sessions it can
  also forget or contradict earlier events.
- **The LLM decides whether actions succeed.** Nothing stops it from agreeing with the player:
  using a key that was never taken, accepting a crowbar that does not exist, or opening a lock for
  someone who claims to be an administrator.
- **The win condition can be spoofed.** The player can ask the model to print `[ESCAPED]`.
- **Fixed codes.** The solution is a constant in the source code, so a leak spoils every future game.

These were confirmed with tests that use a fake Gemini client (`test_version1_limitations.py`).
`evaluate.py` lets the same attacks be run against the real API.

## 4. Version 2 — Python decides, the LLM describes

The main change is to **separate the decision from the description**. Each player message now
passes through three steps:

1. **Interpreter (LLM, JSON mode).** Gemini turns the message into at most three structured actions
   such as `{"action": "use", "item": "brass_key", "target": "cabinet"}`, using a fixed list of
   verbs and the list of object names. It is given **no codes and no solutions**. Its output is
   cleaned: unknown verbs become `other`, and any digits that the player did not type are deleted.
   This stops a manipulated model from "entering" the real code itself. If the API fails, a keyword
   parser takes over.
2. **Engine (Python).** `engine.py` keeps the game state in a dictionary: the status of every
   object, where each item is, the inventory, solved puzzles, the escape flag, failed attempts and a
   log. The room itself is data in `game_config.json`. Each action goes through a validation
   function. `use` checks that the item is **in the inventory**. `take` checks that the container is
   open. `enter_code` checks the number of digits, the code itself and, for the exit, that **all
   earlier puzzles are solved**. Only the engine can change the state. Codes are generated randomly
   for each game and kept in a separate `secrets` dictionary. The bookshelf text is filled in from
   that code, so the clue always matches.
3. **Narrator (LLM).** Gemini gets the engine's result (success or failure, the reason and the
   facts) and the public state, and describes it. It never receives a code the player has not found,
   so it has nothing to leak. Before the reply is shown, `check_reply()` rejects it if it contains a
   protected code (also as `3-9-2`) or describes the door opening while the engine says it is
   locked. In that case the engine's own plain text is shown instead.

**Why these changes were necessary.** Asking the model more firmly to follow the rules would not
fix the Version 1 problems, because a prompt is a suggestion and not a guarantee. Version 2 moves
every decision that matters into ordinary code, which cannot be persuaded. The LLM still does
what it is good at, understanding loose language and writing good descriptions, but it has no
authority. If the LLM fails completely, the game still works: the keyword parser and the engine's
plain text keep it playable, which is how the offline mode works.

**Smaller details.** A rejected exit code is reported the same way whether the code was wrong or the
earlier puzzles were missing, so a correct guess is not given away. Failed actions do not name items
the player has not found yet. After the escape, every action is refused.

## 5. Testing

The project has 46 automated tests (`pytest`, run in under a second, no API key needed). They cover
the full solution, every challenge from the brief, invalid actions, items that do not exist, and
the five Version 1 weaknesses. Two tests simulate a fully **compromised LLM**: an interpreter that
obeys the fake administrator, and a narrator that leaks codes and announces an escape. In both cases
the state stays correct and the guard replaces the text. A fuzz test runs 10,000 random actions with
wrong codes and 150,000 with mixed codes. After every action `check_invariants()` checks rules such
as "the key cannot be held unless the drawer was opened" and "escaped implies every puzzle is
solved". No violation was found. Seven test cases are documented in `docs/TEST_CASES.md`.

## 6. Problems encountered during development

- **Hidden information leaking through the engine itself.** An early Version 2 answered "use the
  brass key" with *"You are not carrying anything like 'brass_key'"*. This confirmed that a key
  exists before the player had found it. Messages for items that have not been found are now neutral.
- **Telling a correct guess apart from a wrong one.** The first version of the exit check returned a
  different reason when the code was right but the puzzles were missing, and that reason was passed
  to the narrator. The public result is now identical. The real reason is kept only in the internal log.
- **The escape check blocked honest text.** *"The glass door of the cabinet swings open"* matched
  the door pattern. Sentences about the cabinet or drawer, and negated sentences ("the door stays
  locked"), are now excluded. Tests cover both the honest and the dishonest wording.
- **API changes.** The Gemini model line-up changed during the project (older 2.x models are being
  retired). The model name is now a setting in `.env`, and `check_setup.py` lists the models a key
  can use.

## 7. Conclusion and possible improvements

Version 1 shows how quickly an LLM can produce an engaging game. Version 2 shows that reliability
comes from the system design, not from the prompt. When the LLM translates and narrates and Python
decides, the game cannot be corrupted by persuasion, invented objects or false claims, and it keeps
most of the LLM's flexibility. Possible next steps are a limit on code attempts, more rooms loaded
from additional JSON files, saving and loading the state, and an LLM-based check of the narration
for invented details.
