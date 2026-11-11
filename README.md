# TransZKEval: Unraveling LLM Behaviors in ZKP Circuit Translation

TransZKEval evaluates translation from Python, Java, Rust, and Go into Circom. The benchmark contains 100 method-level tasks across eight domains, 400 source implementations, 100 Circom references, and 511 shared semantic test inputs.

## Materials

| Material | Location |
| --- | --- |
| Benchmark construction report | [PDF](docs/benchmark-construction/TransZKEval_Benchmark_Construction_Report.pdf), [text](docs/benchmark-construction/TransZKEval_Benchmark_Construction_Report.md), [LaTeX](docs/benchmark-construction/TransZKEval_Benchmark_Construction_Report.tex) |
| Code sample and application analysis | [Construction records](docs/benchmark-construction/analysis/) |
| Source programs and reference circuits | [Dataset](dataset/) |
| Exemplar and evaluation task partition | [Task IDs](dataset/evaluation_partition.json) |
| Translation code and prompts | [Generation scripts](generate/), [prompt guide](docs/prompt-templates.md) |
| Evaluation procedure | [Protocol](docs/evaluation-protocol.md), [evaluator module](test/corrected_evaluation.py) |
| RAG configuration | [Settings](rag/experiments/README.md), [retrieval code](rag/) |
| Agent diagnostic guidance | [Protocol and code](agents/README.md) |

## Task construction

Functional analysis uses a sample of 346 templates from 3,405 distinct public Circom templates. The construction report explains code collection, functional analysis, domain allocation, expert requirement design, method-level adaptation, cross-language implementation, and validation.

| Domain | Tasks |
| --- | ---: |
| Simple Control-Flow | 20 |
| Artificial Intelligence | 15 |
| DeFi Applications | 15 |
| Games and Interaction | 10 |
| Cryptography | 10 |
| Blockchain | 10 |
| Data Structures | 10 |
| Statistics | 10 |
| Total | 100 |

Each task has Python, Java, Rust, Go, and Circom implementations. The shared 511 test inputs are replayed in each source language. The [construction report](docs/benchmark-construction/TransZKEval_Benchmark_Construction_Report.pdf) provides the selection rationale and complete process.

## Models and strategies

The study covers GPT-5.4, Gemini-3.1-Pro, DeepSeek-V3.2, Qwen-Max, Claude-Opus-5.5, DeepSeek-V4-Pro, GLM-5.3, Qwen3-Coder-Plus, Kimi-K2.8, Llama-3.1-8B, and Llama-3.1-70B. The Llama variants provide coverage of smaller parameter scales and a within-family comparison.

The seven main strategies are Direct, KI (Rules), KI (RAG), IR (NL), IR (Pseudocode), IR (CoT), and Refinement. Direct uses a language-specific translation example. Refinement provides one additional repair attempt after compilation failure. Refinement (Knowledge) adds taxonomy-specific guidance and uses the 85-task evaluation partition, separated from 15 exemplar tasks.

The [RAG configuration](rag/experiments/configuration.json) specifies context expansion, hybrid retrieval with reranking, and embedding-model replacement. The [agent protocol](agents/README.md) describes rule injection and compiler-diagnostic guidance for DSH, Claude Code, and Gemini CLI.

## Evaluation code

`test/corrected_evaluation.py` provides the functional evaluator module. `test/eval_analytics.py` retains the original evaluation entry point. `scripts/summarize_results.py` computes CSR, PR, and CA from a user-supplied saved evaluation file:

```bash
python scripts/summarize_results.py path/to/evaluation.jsonl
```

The benchmark inputs determine the test denominator. The summary command uses the Python standard library and performs no model calls or circuit execution. Original spreadsheets and figures remain in their existing repository locations.
