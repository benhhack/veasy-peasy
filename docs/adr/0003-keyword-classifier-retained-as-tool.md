# Old keyword classifier retained only as a Tool

`classifier.py` predates the **Orchestrator**. Its `classify()` function is no longer called anywhere; only the `RULES` keyword dictionary survives, exposed to the Orchestrator LLM as the `keyword_score` Tool — a cheap sanity check the LLM can request on ambiguous Documents. The file is kept (not deleted) so the keyword list has an obvious home; deleting `classifier.py` will silently break the `keyword_score` Tool. If the Tool is ever removed from `TOOL_SCHEMAS`, `classifier.py` should go with it.
