# Translation prompts

The generation scripts retain the prompt text and language-specific examples used by the translation strategies.

| Strategy | Prompt function or entry point |
| --- | --- |
| Direct | `get_basic_one_shot`, `translate_basic` |
| KI (Rules) | `DOMAIN_KNOWLEDGE_EN`, `get_knowledge_one_shot`, `translate_knowledge` |
| KI (RAG) | `get_rag_one_shot`, `translate_rag` |
| IR (Pseudocode) | `get_pseudo_one_shot`, `translate_ir_pseudo` |
| IR (NL) | `get_summary_one_shot`, `translate_ir_summary` |
| IR (CoT) | `get_cot_one_shot`, `translate_ir_cot` |

These definitions are in [the main generation script](../generate/circom_gen_ir&direct&ki.py). The language-specific examples are stored in `LANGUAGE_EXAMPLES` and `CIRCOM_ANSWER`; IR prompts use their corresponding system-prompt and example constants.

[Refinement](../generate/circom_gen_Refinement.py) and [Refinement (Knowledge)](../generate/circom_gen_Refine%28Knowledge%29.py) have separate entry points. The method names in the experimental protocol distinguish the compilation-triggered repair from its knowledge-augmented configuration. The [domain rule text](../agents/RULES.md) and [diagnostic catalogue](../agents/refine_knowledge.jsonl) are available separately.

Model access credentials are supplied locally. Do not commit API credentials or local environment files. The saved-outcome verification commands in the repository README use the Python standard library and make no model API calls.
