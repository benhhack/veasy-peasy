"""Test fixtures for Engine implementations."""


class ScriptedEngine:
    """Returns a pre-canned final state, ignoring input messages and the LLM.

    Useful when testing code that consumes an EngineState without caring how it was produced.
    """

    def __init__(self, final_state: dict):
        self._final = final_state

    def run(self, state, tools, llm, max_rounds):
        # Merge: scripted final state wins over caller-provided initial state.
        merged = {**state, **self._final}
        merged.setdefault("stop_reason", "final")
        merged.setdefault("error", None)
        return merged
