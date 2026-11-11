# Evaluation protocol

## Benchmark units

The benchmark has 100 semantic tasks, each implemented in Python, Java, Rust, and Go with a Circom reference. Its 511 semantic inputs are replayed in each source language. Evaluation keys combine task ID and source language. The domain allocation and task-design process are documented in the [construction report](benchmark-construction/TransZKEval_Benchmark_Construction_Report.pdf).

## Translation strategies

Direct supplies a language-specific translation example and the source program. KI (Rules) adds domain rules. KI (RAG) supplies retrieved code and documentation. The three IR variants use high-level natural-language descriptions, chain-of-thought reasoning, or pseudocode before circuit generation. Refinement is triggered by compilation failure and makes one additional attempt with the source program, circuit, and compiler diagnostics. Compiled outputs are retained, including outputs that fail functional tests.

Refinement (Knowledge) adds diagnostic explanations and examples to the repair prompt. The [task partition](../dataset/evaluation_partition.json) contains 15 exemplar tasks and 85 evaluation tasks, applied consistently across all four source languages. Coding agents use a separate interaction budget described in the [agent protocol](../agents/README.md).

## Functional evaluation

The [functional evaluator module](../test/corrected_evaluation.py) records compilation status and per-test expected and actual outputs. The original evaluation entry point remains in [eval_analytics.py](../test/eval_analytics.py).

CSR is the fraction of programs that compile. PR is the number of passed tests divided by the total number of source-language test executions. CA is the fraction of programs passing the complete task test suite. Compilation failures contribute zero passed tests. The denominator is determined from benchmark inputs, including tests that could not execute after compilation failure.

Reference-circuit constraint counts define Small (<100), Medium (100-999), and Large (>=1000) size tiers. The same task grouping applies across models and strategies.

## Security evaluation

ConsCS, Picus, and ZkFuzz verdicts are handled separately. DIR is the difference between insecure rates for two configurations on their common program set. A positive DIR indicates a higher insecure rate for the first configuration. Unknown verdicts remain in the common denominator; missing tool records are retained as missing. ZkFuzz computation-abort outcomes are recorded separately from non-determinism verdicts.

The original [security analysis notebook](../test/safety_analysis.ipynb) provides the repository's security-analysis entry point. Compilation and functional improvement are assessed separately from constraint security.
