# Hybrid Orchestrator: deterministic MRZ before the LLM

The **Orchestrator** runs a deterministic **Fast Path** before any LLM call: if `passporteye` finds a valid MRZ, the Document is Classified as `passport` and the LLM is never invoked. MRZ is a standardised machine-readable format — deterministic parsing strictly dominates probabilistic generation by a small local model, and short-circuiting saves both latency and a class of small-model misclassifications. Do not "simplify" the Orchestrator by removing the Fast Path and handing passports to the LLM.
