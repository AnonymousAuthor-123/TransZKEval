# TransZKEval: Unraveling LLM Behaviors in ZKP Circuit Translation

> A Systematic Framework for Evaluating LLMs on Cross-Language Translation to Circom ZK Circuits with Retrieval-Augmented Generation and Error Taxonomy

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green.svg)]()
[![Circom 2.1](https://img.shields.io/badge/Circom-2.1.4-orange.svg)]()
[![SnarkJS](https://img.shields.io/badge/SnarkJS-latest-yellow.svg)]()


---

## 📁 Project Structure

```
repo/
├── dataset/
│   ├── source_ipls.jsonl                  # Source functions (Python/Go/Rust/Java + test inputs)
│   ├── groundtruth.jsonl                   # Expert-written Circom implementations (ground truth)
│   └── groundtruth_results_eval.jsonl      # Pre-computed ground truth evaluation results
│
├── generate/                               # ⭐ Code Generation Strategies (3 categories, 8 variants)
│   ├── circom_gen_ir&direct&ki.py          #   6 single-pass strategies: basic, knowledge, rag, ir_pseudo, ir_summary, ir_cot
│   ├── circom_gen_Refinement.py            #   Basic one-shot iterative refinement
│   └── circom_gen_Refine(Knowledge).py     #   Knowledge-guided refinement (error-classification-aware)
│   └── cpp_gen.py                          #   C++ baseline generation (for comparison)
│
├── rag/                                    # RAG System
│   ├── get_code.py                         #   Scrape top-100 Circom repos from GitHub
│   ├── get_doc.py                          #   Parse Circom documentation
│   ├── parse.py                            #   Extract templates/docs → structured knowledge units
│   ├── hash_deduplication.py               #   MD5 content-level deduplication
│   ├── ingestion_code.py                   #   Code → Chroma vector DB
│   ├── ingestion_doc.py                    #   Docs → Chroma vector DB
│   ├── pre_retrieve.py                     #   3+2 Retrieval (3 code + 2 doc examples)
│   ├── circom_docs.jsonl                   #   Processed documentation chunks
│   ├── circom_rag_data.jsonl               #   Raw knowledge units
│   └── circom_rag_data_hash_clean.jsonl    #   Deduplicated knowledge units
│
├── test/
│   ├── eval_analytics.py                   # ⭐ Automated evaluation pipeline
│   └── safety_analysis.ipynb               #   Interactive analysis notebook
│
├── results/
│   ├── circom_full_analysis.xlsx           #   Per-task detailed results
│   ├── evaluation_statistics.xlsx          #   Aggregate metrics
│   ├── evaluation_statistics_cpp.xlsx      #   C++ baseline metrics
│   ├── evaluation_statistics_with_refine_knowledge.xlsx  # Knowledge-refined results
│   └── security_summary_total.xlsx         #   Security analysis
│
├── images/
│   ├── rq1pl.png / rq1model.png            # RQ1: accuracy vs. efficiency
│   ├── rq2.png                             # RQ2: knowledge injection impact
│   └── rq3.png                             # RQ3: error taxonomy distribution
│
├── merge_error_classifiers.py              # NLP-based compilation error classification
├── Failure Taxonomy and Case Analysis.pdf  # Paper: detailed error taxonomy
└── Table5_Supplementary.pdf                # Paper: supplementary results
```

---

## 💾 Dataset

**File**: `dataset/source_ipls.jsonl`

~100 hand-selected functions across 4 languages. Each entry:

```json
{
  "id": 1,
  "func_name": "is_in_range",
  "py": "def is_in_range(n, low, high): return [1 if low <= n <= high else 0]",
  "go": "func (l *LogicFunctions) IsInRange(n, low, high int) []int { ... }",
  "rs": "fn is_in_range(n: u64, low: u64, high: u64) -> u64 { ... }",
  "jv": "public static long isInRange(long n, long low, long high) { ... }",
  "inputs": [
    [50, 0, 100],    // normal: in range
    [0, 0, 10],      // edge: lower boundary
    [10, 0, 10],     // edge: upper boundary
    [150, 0, 100],   // edge: out of range
    [5, 10, 20]      // edge: below lower bound
  ]
}
```

**Ground Truth**: `dataset/groundtruth.jsonl` — expert-written Circom implementations for correctness checking.

---

## 🎯 Code Generation Strategies

Complete 8 Circom Translation & Refinement Strategies.

---

### 1: Direct Translation

**File**: `generate/circom_gen_ir&direct&ki.py` (function `translate_basic`)

**System Prompt:**
```
You are a code translator. Output only Circom code.
```

**User Prompt:**

> Example:
> Translate the following {lang} function into a Circom 2.1.4 template named SimpleMax. Base your translation SOLELY on the retrieved templates and documentation above. Follow the syntax style from the retrieved examples:
> ```python
> def simple_max(a, b):
>     if a >= b:
>         return a
>     else:
>         return b
> ```
>
> ```circom
> include "node_modules/circomlib/circuits/comparators.circom";
> template SimpleMax() {
>     signal input a;
>     signal input b;
>     signal output out;
>     component gte = GreaterEqThan(64);
>     gte.in[0] <== a;
>     gte.in[1] <== b;
>     signal sel <== gte.out;
>     out <== sel * (a - b) + b;
> }
> component main = SimpleMax();
> ```
>
> Task:
> Translate the following {lang} function into a Circom 2.1.4 template named {func_name}:
> {source_code}

**Strategy Explanation:** This is the baseline control strategy for Circom code translation. It only provides a standard one-shot translation example without professional ZK domain rules, retrieval knowledge or auxiliary reasoning guidance. The model relies purely on its general code translation capability to convert high-level programming code to Circom syntax, serving as the benchmark to measure the performance of advanced optimization strategies.

---

### 2: KI(Rules)

**File**: `generate/circom_gen_ir&direct&ki.py` (function `translate_knowledge`)

**System Prompt:**
```
You are a code translator.
```

**User Prompt:** Same one-shot as Strategy 1, but prepended with the full 20-rule `DOMAIN_KNOWLEDGE_EN`:

> ### 1. The Zero-Jump Rule (Branching)
> In ZK circuits, there is no instruction pointer jump. Both `if` and `else` paths are executed. You must compute both results and use a binary selector signal ($0$ or $1$) to pick the valid output.
>
> ### 2. Quadratic Constraint Limit (R1CS)
> Circom constraints (`<==` or `===`) must be **quadratic**. You cannot multiply three or more signals directly.
> * **Wrong**: `out <== a * b * c;`
> * **Correct**: `signal intermediate <== a * b; out <== intermediate * c;`
>
> ### 3. Verification over Calculation (Division/Mod)
> You cannot "calculate" division ($/$) or modulo ($\%$) directly in a constraint. You must provide the answer as a witness and **verify** it via a linear equation.
> * **Pattern**: `Dividend === Divisor * Quotient + Remainder;`
> * **Constraint**: Use `<--` for the witness assignment and `===` for the enforcement.
>
> ### 4. Field Element Awareness (Negative Numbers)
> Circom operates in a Prime Field $F_p$. A negative number $-x$ is represented as $P - x$ (a very large positive number).
> * **Comparison**: To compare $a < b$ where $a$ might be negative, you must use `Num2Bits` to check the sign bit (bit 253) or shift values into a safe range.
>
> ### 5. Absolute Value Shielding
> When performing division or scaling on signed numbers, follow this pipeline to avoid field overflow errors:
> 1. Extract the sign bit via `Num2Bits(254)`.
> 2. Convert to absolute value: `abs <== sign * (-2 * val) + val;`
> 3. Perform unsigned arithmetic (div/mod) on the `abs` value.
> 4. Re-apply the sign to the result: `out <== (1 - 2 * sign) * abs_result;`
>
> ### 6. Signal Immutability
> Signals are constants once assigned. If you need to update a value in a loop (like an accumulator), use a `var` for intermediate calculation or a signal array (`s[i]`) for sequential constraints.
>
> ### 7. Bit-Length Safety (Aliasing)
> Always specify the bit-length in comparators (e.g., `LessThan(252)`). Using the full 254 bits of the prime field can lead to "aliasing" where a value wraps around the prime $P$. 252 bits is the standard safety limit.
>
> ### 8. Boolean Logic Arithmetization
> Translate logical gates into polynomials to stay within the arithmetic circuit paradigm:
> * `NOT(a)` $\rightarrow$ `1 - a`
> * `AND(a, b)` $\rightarrow$ `a * b`
> * `OR(a, b)` $\rightarrow$ `a + b - a * b`
>
> ### 9. Priority Chains (Else-If Logic)
> To simulate `if-else if-else`, ensure the selectors are mutually exclusive to avoid adding results together.
> * `isA <== condA;`
> * `isB <== (1 - isA) * condB;` // B only triggers if A is false.
> * `isC <== (1 - isA) * (1 - isB);` // C is the default "else" case.
>
> ### 10. The Zero-Division Trap
> Always handle the case where a divisor might be zero using the `IsZero()` component. A division by zero during witness generation (`<--`) will cause the prover to crash or produce an invalid proof.
>
> ### 11. Integer Scaling (Fixed-Point)
> Since ZK circuits do not support floating-point numbers, multiply your values by a large power of 10 (scaling factor) before dividing to maintain precision.
> * **Rule**: `(numerator * scale) / denominator`.
>
> ### 12. Linear vs. Non-Linear Constraints
> Multiplying a signal by a constant (e.g., `out <== a * 5;`) is a "linear" constraint and is computationally cheap. Multiplying two signals (e.g., `out <== a * b;`) is "non-linear" and increases the proof size.
>
> ### 13. Witness vs. Constraint Separation
> Use `<--` (assignment) for values that are computationally expensive but easy to verify (e.g., square roots or private hints). Always follow with `===` (enforcement) to ensure the prover is honest.
>
> ### 14. Range Proofs
> Always enforce that inputs stay within expected bounds (e.g., $0-2^{32}-1$). Never assume an input is "small" just because it looks like a small integer; in $F_p$, it could be a malicious large value.
>
> ### 15. The Mux Formula (Standard Selection)
> For any basic ternary operation `res = condition ? a : b`, use the optimized quadratic form:
> `out <== condition * (a - b) + b;`
>
> ### 16. Component Encapsulation
> Keep templates small and modular. If a piece of logic involves more than 5-10 complex constraints, wrap it in a separate `template` to improve readability and debuggability.
>
> ### 17. Constant Bit-Widths
> When using `Num2Bits(n)`, ensure $n$ is a constant known at compile time. Dynamic bit-widths are not supported in Circom.
>
> ### 18. Avoid Nested Signal Declarations
> Do not declare `signal` or `component` inside a `for` loop that depends on an input variable. All signals must be declared in the top-level scope or as fixed-size arrays.
>
> ### 19. Underflow Awareness
> In $F_p$, $3 - 5$ does not result in $-2$ directly; it results in $P-2$. While this works for addition/subtraction, it breaks comparisons. Always use comparators designed for the field.
>
> ### 20. Deterministic Constraints
> Every `output` signal must be constrained to a unique value. An unconstrained output allows a malicious prover to pick any value they want, breaking the soundness of the ZK proof.
>
> Example:
> Translate this {lang} code into Circom 2.1.4 template SimpleMax:
> ```python
> def simple_max(a, b):
>     if a >= b:
>         return a
>     else:
>         return b
> ```
>
> ```circom
> include "node_modules/circomlib/circuits/comparators.circom";
> template SimpleMax() {
>     signal input a;
>     signal input b;
>     signal output out;
>     component gte = GreaterEqThan(64);
>     gte.in[0] <== a;
>     gte.in[1] <== b;
>     signal sel <== gte.out;
>     out <== sel * (a - b) + b;
> }
> component main = SimpleMax();
> ```
>
> Task:
> Translate this {lang} code into Circom 2.1.4 template {func_name}:
> {source_code}

**Strategy Explanation:** This strategy augments basic translation with 20 professional ZK-Circom domain rules covering constraint limitations, field arithmetic, signal logic, and circuit coding specifications. It standardizes model behavior to comply with R1CS circuit constraints, effectively avoiding common compilation and logical errors caused by ignorance of zero-knowledge circuit underlying principles.

---

### 3: KI(RAG)

**File**: `generate/circom_gen_ir&direct&ki.py` (function `translate_rag`)

**System Prompt:**
```
You are a code translator.
```

**User Prompt:**

> === Retrieved Circom Templates ===
> {retrieved_code}
>
> === Retrieved Documentation ===
> {retrieved_doc}
>
> Example:
> Translate this {lang} code into Circom 2.1.4 template SimpleMax:
> ```python
> def simple_max(a, b):
>     if a >= b:
>         return a
>     else:
>         return b
> ```
>
> ```circom
> include "node_modules/circomlib/circuits/comparators.circom";
> template SimpleMax() {
>     signal input a;
>     signal input b;
>     signal output out;
>     component gte = GreaterEqThan(64);
>     gte.in[0] <== a;
>     gte.in[1] <== b;
>     signal sel <== gte.out;
>     out <== sel * (a - b) + b;
> }
> component main = SimpleMax();
> ```
>
> Task:
> Translate this {lang} code into Circom 2.1.4 template {func_name}. Base your translation SOLELY on the retrieved templates and documentation above. Follow the syntax style from the retrieved examples:
> {source_code}

**Strategy Explanation:** This retrieval-augmented strategy leverages external Circom template libraries and official documentation as auxiliary knowledge. The model strictly follows retrieved high-quality code cases and standard specifications for translation, reducing hallucinations. It improves the accuracy and standardization of generated Circom code by referencing verified real-world circuit implementations.

---

### 4: IR(Pseudo)

**File**: `generate/circom_gen_ir&direct&ki.py` (function `translate_ir_pseudo`)

**Stage 1 — Source Code → Pseudo-IR**

**Stage 1 System Prompt:**
```
You are a Zero-Knowledge Circuit Compiler.
Convert the given program into "Circuit Pseudo IR", an intermediate representation used for ZK circuit synthesis.
The IR must follow these sections:

1. Signal Declarations
Declare all signals and classify them as:
- public input
- private witness
- intermediate signal
- output

2. Witness Computation
Describe how intermediate signals are computed using arithmetic operations.

3. Constraint System
Express all relations that must hold as algebraic constraints.

Rules:
- Use '=' for witness computation.
- Use '==' for constraint enforcement.
- Express constraints using arithmetic equations only.
- Eliminate control flow:
  - Replace if/else with arithmetic selection:
      out = cond * x + (1-cond) * y
- Any condition variable must satisfy:
      cond * (cond - 1) == 0

Output format:

[Signal Declarations]

[Witness Computation]

[Constraint System]
```

**Stage 1 User Prompt:**

> Example:
> Convert this {lang} code into circuit-level pseudo-logic:
> ```python
> def simple_max(a, b):
>     if a >= b:
>         return a
>     else:
>         return b
> ```
>
> [Signal Declarations]
> - public input: a, b
> - intermediate signal: gte_out, sel
> - output: out
>
> [Witness Computation]
> gte_out = compare(a >= b)
> sel = gte_out
> out = sel * (a - b) + b
>
> [Constraint System]
> gte_out * (gte_out - 1) == 0
> out == sel * (a - b) + b
>
> Task:
> Convert this {lang} code into circuit-level pseudo-logic:
> {source_code}

**Stage 2 — Pseudo-IR → Circom Code**

**Stage 2 System Prompt:**
```
You are a Circom expert.
```

**Stage 2 User Prompt:**

> Example:
> Based ONLY on this circuit pseudo-logic, implement the Circom 2.1.4 template SimpleMax:
>
> [Signal Declarations]
> - public input: a, b
> - intermediate signal: gte_out, sel
> - output: out
>
> [Witness Computation]
> gte_out = compare(a >= b)
> sel = gte_out
> out = sel * (a - b) + b
>
> [Constraint System]
> gte_out * (gte_out - 1) == 0
> out == sel * (a - b) + b
>
> ```circom
> include "node_modules/circomlib/circuits/comparators.circom";
> template SimpleMax() {
>     signal input a;
>     signal input b;
>     signal output out;
>     component gte = GreaterEqThan(64);
>     gte.in[0] <== a;
>     gte.in[1] <== b;
>     signal sel <== gte.out;
>     out <== sel * (a - b) + b;
> }
> component main = SimpleMax();
> ```
>
> Task:
> Based ONLY on this circuit pseudo-logic, implement the Circom 2.1.4 template {func_name}:
> {generated_pseudo_ir}

**Strategy Explanation:** This two-stage intermediate representation strategy disassembles high-level code into standardized circuit pseudo-code first, then compiles the pseudo-code into formal Circom code. It completely eliminates high-level control flow and unifies all logic into signal declaration, witness calculation, and algebraic constraints, ensuring the final circuit strictly conforms to ZK constraint system characteristics.

---

### 5: IR(Summary)

**File**: `generate/circom_gen_ir&direct&ki.py` (function `translate_ir_summary`)

**Stage 1 — Source Code → Functional Summary**

**Stage 1 System Prompt:**
```
You are a ZK-SNARK Consultant.
Provide a high-level functional summary of the code.
Focus on:
1. The mathematical objective.
2. The data flow from input signals to results.
3. Essential arithmetic operations to be preserved.
Do not include source code in your output.
```

**Stage 1 User Prompt:**

> Example:
> Summarize the mathematical flow of this {lang} function:
> ```python
> def simple_max(a, b):
>     if a >= b:
>         return a
>     else:
>         return b
> ```
>
> The function computes the maximum of two input values a and b. It performs a comparison operation to determine if a is greater than or equal to b, then selects the larger value using arithmetic selection. The output is the maximum of the two inputs.
>
> Task:
> Summarize the mathematical flow of this {lang} function:
> {source_code}

**Stage 2 — Summary → Circom Code**

**Stage 2 System Prompt:**
```
You are a Circom expert.
```

**Stage 2 User Prompt:**

> Example:
> Based ONLY on this summary, implement the Circom 2.1.4 template SimpleMax:
>
> The function computes the maximum of two input values a and b. It performs a comparison operation to determine if a is greater than or equal to b, then selects the larger value using arithmetic selection. The output is the maximum of the two inputs.
>
> ```circom
> include "node_modules/circomlib/circuits/comparators.circom";
> template SimpleMax() {
>     signal input a;
>     signal input b;
>     signal output out;
>     component gte = GreaterEqThan(64);
>     gte.in[0] <== a;
>     gte.in[1] <== b;
>     signal sel <== gte.out;
>     out <== sel * (a - b) + b;
> }
> component main = SimpleMax();
> ```
>
> Task:
> Based ONLY on this summary, implement the Circom 2.1.4 template {func_name}:
> {generated_summary}

**Strategy Explanation:** This strategy abstracts the core mathematical logic and data flow of source code via high-level functional summarization, stripping irrelevant programming syntax details. The model generates Circom circuits purely based on summarized mathematical objectives and core operations, focusing on logical correctness of zero-knowledge proof rather than syntax similarity with source code.

---

### 6: IR(CoT)

**File**: `generate/circom_gen_ir&direct&ki.py` (function `translate_ir_cot`)

**Stage 1 — Source Code → 5-Step CoT Analysis**

**Stage 1 System Prompt:**
```
You are a ZK Constraint Engineer.
Analyze the program and derive a constraint-friendly representation using the following steps:

Step 1: Mathematical Objective
Describe the final relation that the circuit proves.

Step 2: Signal Graph Construction
List all signals and define their dependencies.

Step 3: Control Flow Flattening
Transform conditional logic and loops into arithmetic expressions.

Step 4: Constraint Extraction
Convert each operation into R1CS-style constraints.

Step 5: Circom Mapping
Map the constraints into Circom syntax:
- signal declarations
- component templates
- constraint statements
```

**Stage 1 User Prompt:**

> Example:
> Analyze this {lang} code for ZK implementation:
> ```python
> def simple_max(a, b):
>     if a >= b:
>         return a
>     else:
>         return b
> ```
>
> Step 1: Mathematical Objective
> Prove that the output equals the maximum of two input values.
>
> Step 2: Signal Graph Construction
> - Inputs: a, b
> - Intermediate: gte_out (comparison result), sel (selector)
> - Output: out
>
> Step 3: Control Flow Flattening
> Replace if-else with arithmetic selection: out = sel * (a - b) + b, where sel = 1 if a >= b, else 0
>
> Step 4: Constraint Extraction
> - gte_out * (gte_out - 1) == 0 (binary constraint)
> - out == sel * (a - b) + b (selection constraint)
>
> Step 5: Circom Mapping
> Use GreaterEqThan comparator and arithmetic selection formula.
>
> Task:
> Analyze this {lang} code for ZK implementation:
> {source_code}

**Stage 2 — CoT Analysis → Circom Code**

**Stage 2 System Prompt:**
```
You are a Circom expert.
```

**Stage 2 User Prompt:**

> Example:
> Based on this 5-step analysis, implement the Circom 2.1.4 template SimpleMax:
>
> Step 1: Mathematical Objective
> Prove that the output equals the maximum of two input values.
>
> Step 2: Signal Graph Construction
> - Inputs: a, b
> - Intermediate: gte_out (comparison result), sel (selector)
> - Output: out
>
> Step 3: Control Flow Flattening
> Replace if-else with arithmetic selection: out = sel * (a - b) + b, where sel = 1 if a >= b, else 0
>
> Step 4: Constraint Extraction
> - gte_out * (gte_out - 1) == 0 (binary constraint)
> - out == sel * (a - b) + b (selection constraint)
>
> Step 5: Circom Mapping
> Use GreaterEqThan comparator and arithmetic selection formula.
>
> ```circom
> include "node_modules/circomlib/circuits/comparators.circom";
> template SimpleMax() {
>     signal input a;
>     signal input b;
>     signal output out;
>     component gte = GreaterEqThan(64);
>     gte.in[0] <== a;
>     gte.in[1] <== b;
>     signal sel <== gte.out;
>     out <== sel * (a - b) + b;
> }
> component main = SimpleMax();
> ```
>
> Task:
> Based on this 5-step analysis, implement the Circom 2.1.4 template {func_name}:
> {generated_cot_analysis}

**Strategy Explanation:** This step-by-step reasoning strategy standardizes ZK circuit transformation through five fixed analytical dimensions. It forces the model to explicitly sort mathematical goals, signal dependencies, flow flattening, constraint rules and syntax mapping, eliminating reasoning omissions. It significantly improves the logical rigor and constraint compliance of generated Circom code.

---

### 7: Refinement

**File**: `generate/circom_gen_Refinement.py`

**System Prompt:**
```
You are a Circom expert. Fix the code and output ONLY the corrected code without any explanation or markdown tags.
```

**User Prompt:**

> Fix the following Circom compilation error.
>
> Example:
>
> [Faulty Circom Code]:
> ```circom
> pragma circom 2.1.0;
> include "node_modules/circomlib/circuits/comparators.circom";
>
> template SimpleMax() {
>     signal input a;
>     signal input b;
>     signal output out;
>
>     component gte = GreaterEqThan(64);
>     gte.in[0] <== a;
>     gte.in[1] <== b;
>
>     if (gte.out == 1) {
>         out <== a;
>     } else {
>         out <== b;
>     }
> }
>
> component main = SimpleMax();
> ```
>
> [Compiler Error]:
> error[T2005]: Typing error found
>     "circuit.circom":12:8
>
> 12     if (gte.out == 1) {
>            ^^^^^^^^^^^^ There are constraints depending on the value of the condition and it can be unknown during the constraint generation phase
>
> previous errors were found
>
> [Fixed Circom Code]:
> ```circom
> pragma circom 2.1.0;
> include "node_modules/circomlib/circuits/comparators.circom";
>
> template SimpleMax() {
>     signal input a;
>     signal input b;
>     signal output out;
>
>     component gte = GreaterEqThan(64);
>     gte.in[0] <== a;
>     gte.in[1] <== b;
>
>     signal sel <== gte.out;
>     out <== sel * (a - b) + b;
> }
>
> component main = SimpleMax();
> ```
>
> Task:
> [Faulty Circom Code]:
> {faulty_circom_code}
>
> [Compiler Error]:
> {compiler_error_msg}
>
> [Fixed Circom Code]:

Only processes `COMPILE_FAIL` tasks; skips `SUCCESS` and `LOGIC_FAIL`.

**Strategy Explanation:** This post-processing repair strategy targets compilation-failed Circom code. It provides a standard error repair one-shot case, enabling the model to quickly identify typical Circom syntax and constraint errors based on compiler prompts, and output corrected compilable code in a single round without iterative debugging.

---

### 8: Refinement(Knowledge)

**File**: `generate/circom_gen_Refine(Knowledge).py`

**System Prompt:**
```
You are a Circom expert. Return only code.
```

**User Prompt:**

> You are a Circom expert. Your task is to fix Circom compilation errors.
>
> ## [Learning from Similar Error Case]
> Use this pattern to understand the nature of the error:
> - [Error Classification]: {ex_error_classify}
> - [Primary Code]: {ex_primary_code}
> - [General Description]: {ex_general_desc}
> - [Specific Description]: {ex_specific_desc}
> - [Example Faulty Code for Reference]:
> {ex_faulty_sample_code}
>
> ---
>
> ## [Current Task to Fix]
> Fix the compilation error in the following translated Circom code.
>
> [Source {lang} Code]:
> {source_code}
>
> [Current Faulty Circom Code]:
> {faulty_circom_code}
>
> [Compiler Error Message]:
> {compiler_error_msg}
>
> [Fixed Circom Code]:
> (Output ONLY the functional code, no markdown tags, no explanations)

Error matching logic:
1. Extract primary error code (e.g., `T2005`, `P1008`) via regex `error\[([A-Z0-9]+)\]`
2. Look up the error classification in `descriptions_map` (built from `extracted_samples_with_descriptions.jsonl`)
3. Fall back to primary code lookup if no classification match

Also supports **SKIP_IDS** — a set of task IDs to entirely bypass.

**Strategy Explanation:** This advanced error repair strategy introduces classified error case libraries and professional error descriptions. Compared to one-shot repair, it matches similar historical error cases according to error codes and classification, allowing the model to understand error essences systematically. It achieves more accurate and robust error fixing for complex and atypical Circom compilation errors.

---

## 📚 RAG System

Files in `rag/`:

| File | What It Does | How to Run |
|------|-------------|------------|
| `get_code.py` | Scrapes top-100 starred Circom repos from GitHub, downloads all `.circom` files | `python get_code.py` |
| `get_doc.py` | Scrapes Circom documentation (`.md`, `.txt` files) from local repo copy | `python get_doc.py` |
| `parse.py` | Extracts individual `template` blocks from code; splits docs by headings | `python parse.py` |
| `hash_deduplication.py` | MD5-hashes each knowledge unit's text field, removes duplicates | `python hash_deduplication.py` |
| `ingestion_code.py` | Loads deduplicated code units into Chroma vector DB (BAAI/bge-small-en-v1.5 embeddings) | `python ingestion_code.py` |
| `ingestion_doc.py` | Loads doc units into separate Chroma vector DB | `python ingestion_doc.py` |
| `pre_retrieve.py` | **3+2 Retrieval**: queries code DB for top-3 similar templates + doc DB for top-2 doc chunks | Import `get_3plus2_context()` |

### Retrieval Logic (`pre_retrieve.py`)

```python
def get_3plus2_context(func_name):
    query = func_name.replace("_", " ")
    code_results = db_code.similarity_search(query, k=3)   # 3 code templates
    doc_results = db_doc.similarity_search(query, k=2)      # 2 doc chunks
    return code_snippets, doc_snippets
```

Each code result uses **smart cropping** (head 1000 chars + tail 500 chars) to stay within token limits.

---

## ⚙️ Evaluation Pipeline

**File**: `test/eval_analytics.py`

Automated flow for each generated circuit:

```
circom circuit.circom --r1cs --wasm    →  status: COMPILE_FAIL | OK
     │
snarkjs groth16 setup ...               →  status: SETUP_FAIL | OK
     │
for each test input:
  generate_witness + verify output      →  PASS | FAIL (LOGIC_FAIL)
     │
if first PASS case:
  groth16 prove → proving_time_ms, proof_size_bytes
```

### Output Format

```json
{
  "id": 1,
  "func": "is_in_range", "lang": "Python",
  "status": "SUCCESS",          // SUCCESS | COMPILE_FAIL | SETUP_FAIL | LOGIC_FAIL
  "constraints": 139,
  "proving_time_ms": 399,
  "proof_size_bytes": 802,
  "test_cases": [
    {"input": [50, 0, 100], "expected": 1, "actual": 1, "status": "PASS"},
    ...
  ],
  "error_msg": ""
}
```

### C++ Baseline

**File**: `generate/cpp_gen.py`

Same-sourced functions translated to C++ instead of Circom, using language-specific one-shot examples. Results in `results/evaluation_statistics_cpp.xlsx` serve as a baseline isolating ZK-circuit-specific challenges from general translation difficulty.

---

## 🐛 Error Classification

**File**: `merge_error_classifiers.py`

Using this program, the four main types of errors reported by the Circom compiler (P1012, P1008, T3001, T2021) can be classified in detail according to the preset rules. Other error codes do not require detailed classification; the subcategory can be determined simply based on the error code.

---

## 📊 Results

Pre-computed in `results/` as Excel files:

| File | Contents |
|------|----------|
| `circom_full_analysis.xlsx` | Per-task results across all strategies |
| `evaluation_statistics.xlsx` | Aggregate metrics per strategy × language |
| `evaluation_statistics_cpp.xlsx` | C++ baseline comparison |
| `evaluation_statistics_with_refine_knowledge.xlsx` | Knowledge-refined results |
| `security_summary_total.xlsx` | Security/correctness summary |


The visual charts in the `images/` directory answer the following three research questions:
- **RQ1** (`rq1pl.png`, `rq1model.png`): The logical correctness of the code generated by the model and its correlation with the source language/target language, as well as its correlation with LLM categories
- **RQ2** (`rq2.png`): The impact of different strategies on the logical correctness of the code generated by the model
- **RQ3** (`rq3.png`): The influence of different strategies/models on the security of the code generated by the model
---

## 🚀 How to Run

### 1. Generate

```bash
cd generate

# All 6 single-pass strategies (basic, knowledge, rag, ir_pseudo, ir_summary, ir_cot)
python circom_gen_ir&direct&ki.py

# Iterative refinement on compile failures
python circom_gen_Refinement.py <model_name> <strategy>
python circom_gen_Refine\(Knowledge\).py <model_name> <strategy>

# C++ baseline
python cpp_gen.py
```

### 2. Evaluate

```bash
cd test
python eval_analytics.py --input <results_file.jsonl>
```

### 3. Classify Errors

```bash
python merge_error_classifiers.py
# Reads: ./eval_results/*.jsonl
# Writes: ./eval_results_with_error_classify/*.jsonl
```

### 4. Analyze

```bash
jupyter notebook test/safety_analysis.ipynb
# Or view results/*.xlsx directly
```

### Setup Quick Reference

```bash
# Prerequisites: Node.js ≥18, Circom ≥2.1.4, SnarkJS
npm install -g snarkjs

# Python
pip install openai langchain-core langchain-community langchain-huggingface
pip install chromadb huggingface-hub sentence-transformers sympy tqdm

# RAG (optional — needed only for RAG strategy)
cd rag && python get_code.py && python parse.py && python hash_deduplication.py
python ingestion_code.py && python ingestion_doc.py
```

---

## 📄 Paper

- **Failure Taxonomy and Case Analysis.pdf** — This PDF acts as the formal detailed failure case appendix and core reference material for the knowledge refinement strategy proposed in the paper. All error-aware prompt design, failure repair ablation experiments, and qualitative root-cause analysis rely on the systematic taxonomy and real translation cases recorded in this document. The paper’s main text only summarizes high-level error categories; this appendix provides full hierarchical classification, compiler error codes, faulty Circom code samples, source IPL code, compiler error logs, and root-cause explanations for every error type.

- **Table5_Supplementary.pdf** — This supplementary table file is the complete extended version of Table 5 in the paper’s main body. The main text only retains core averaged metrics for space limitation; this PDF attaches full fine-grained experimental results covering all 8 translation strategies, all test dataset samples, multi-dimensional evaluation indicators, and statistical significance data. It serves as the quantitative experiment backup for ablation study, strategy comparison, and performance analysis sections.


