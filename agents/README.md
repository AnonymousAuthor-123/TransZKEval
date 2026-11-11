# Coding-agent configuration

## Systems and protocol

| System | Underlying model |
| --- | --- |
| DeepSeek Harness (DSH) | DeepSeek-V4-Pro |
| Claude Code | Claude-Opus-5.5 |
| Gemini CLI | Gemini-3.1-Pro |

Each system has access to circomlib and compiler feedback and can compile and revise its circuit within a 300-second per-program budget. Evaluation uses the final available artifact, including a saved artifact when a run reaches its time budget. The comparison uses the same 340 programs from 85 tasks in Python, Java, Rust, and Go. These tasks are disjoint from the 15 exemplar tasks listed in the [partition file](../dataset/evaluation_partition.json).

## Diagnostic guidance

The enhanced configuration adds the [domain rules](RULES.md) to the initial prompt. The controller checks Circom compiler diagnostics, classifies the reported error, and appends the matching explanation and repair guidance to the compiler output returned to the agent. Successful compilation and unrelated shell commands receive no diagnostic knowledge block.

`knowledge_matcher.py` implements diagnostic matching. `refine_knowledge.jsonl` contains stored source snippets and descriptions from the exemplar tasks. The catalogue contains 76 stored entries; the complete error taxonomy contains 81 subcategories. Initial rules and diagnostic examples are separate inputs to the enhanced configuration.

Original and enhanced configurations use the same underlying model, evaluation programs, and interaction budget. Compilation, functional correctness, and constraint security are evaluated separately.
