# Local-only LLM via Ollama

These are sensitive personal Documents (passports, bank statements, proof of address). All inference runs against a local Ollama server — no external API calls — so nothing leaves the machine. This constrains us to small models that fit comfortably on consumer hardware (target: 8 GB RAM), which in turn shapes prompt design, the choice of `qwen2.5:3b` as default, and the existence of the **Fast Path** for problems small models would mishandle.
