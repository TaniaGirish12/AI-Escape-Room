"""Version 2 - one game turn, from the player's message to the reply.

    player text --> interpreter (LLM) --> actions --> engine (Python rules)
                                                         |
    reply text  <-- output check <-- narrator (LLM) <-- results

Only the engine step can change the game state.
"""

from engine import GameEngine
from interpreter import interpret
from narrator import narrate


def play_turn(player_text: str, engine: GameEngine, llm=None,
              recent_turns: list[dict] | None = None) -> dict:
    """Run one turn and return the reply together with what happened behind the scenes."""
    actions, interpreter_source = interpret(player_text, engine, llm)

    results = []
    for action in actions:
        result = engine.perform(action)
        results.append(result)
        if not result["success"]:
            break                       # do not continue a chain after a failed step

    reply, narrator_source = narrate(player_text, results, engine, llm, recent_turns)
    return {
        "reply": reply,
        "actions": actions[:len(results)],
        "results": results,
        "interpreter": interpreter_source,
        "narrator": narrator_source,
    }


def play_action(action: dict, label: str, engine: GameEngine, llm=None,
                recent_turns: list[dict] | None = None) -> dict:
    """Run a turn for a button in the interface.

    The action is already structured, so the interpreter is skipped. It still
    goes through the engine (which decides) and the narrator (which describes).
    """
    full_action = {"action": "other", "target": "", "item": "", "code": "", **action}
    result = engine.perform(full_action)
    reply, narrator_source = narrate(label, [result], engine, llm, recent_turns)
    return {"reply": reply, "actions": [full_action], "results": [result],
            "interpreter": "button", "narrator": narrator_source}
