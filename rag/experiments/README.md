# RAG configuration

The retrieval code is in the parent [rag directory](../). The [configuration file](configuration.json) records the baseline and three supplementary retrieval settings.

The baseline uses BAAI/bge-small-en-v1.5, function-name queries with underscores replaced by spaces, three code templates and two document chunks, and no relevance filtering or reranking. Long passages use the first 1,000 and last 500 characters of a 1,500-character context budget.

| Setting | Retrieval procedure | Code/document entries |
| --- | --- | --- |
| Original RAG | Original cached retrieval | 3 / 2 |
| Expanded context | Preserve the original entries and append additional material from the same corpus | 6 / 4 |
| Hybrid retrieval | Function-name and source-code query views; dense retrieval and BM25; reciprocal-rank fusion; BGE-reranker-v2-m3 | 3 / 2 |
| Embedding replacement | Qwen/Qwen3-Embedding-0.6B with the original query form, distance convention, and context counts | 3 / 2 |

Hybrid retrieval changes several pipeline components together. Embedding replacement keeps the remaining retrieval procedure aligned with the baseline. The supplementary settings use DeepSeek-V4-Pro and all 100 tasks in four source languages. Retrieval is performed before generation.

Context equality compares quantity, order, titles, and content under the configured normalization policy. The original baseline cache is the reference for reuse decisions.
