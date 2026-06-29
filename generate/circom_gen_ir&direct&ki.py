
import json
import time
import os
from openai import OpenAI

# ==========================================
# 1. 配置与专业 Prompt 定义
# ==========================================

client = OpenAI(
    api_key="xx",
    base_url="xx"
)

# [Knowledge] Enhanced Professional Domain Knowledge (15+ rules)
DOMAIN_KNOWLEDGE_EN = """
### 1. The Zero-Jump Rule (Branching)
In ZK circuits, there is no instruction pointer jump. Both `if` and `else` paths are executed. You must compute both results and use a binary selector signal ($0$ or $1$) to pick the valid output.


### 2. Quadratic Constraint Limit (R1CS)
Circom constraints ($<==$ or $===$) must be **quadratic**. You cannot multiply three or more signals directly.
* **Wrong**: `out <== a * b * c;`
* **Correct**: `signal intermediate <== a * b; out <== intermediate * c;`

### 3. Verification over Calculation (Division/Mod)
You cannot "calculate" division ($/$) or modulo ($\%$) directly in a constraint. You must provide the answer as a witness and **verify** it via a linear equation.
* **Pattern**: `Dividend === Divisor * Quotient + Remainder;`
* **Constraint**: Use `<--` for the witness assignment and `===` for the enforcement.

### 4. Field Element Awareness (Negative Numbers)
Circom operates in a Prime Field $F_p$. A negative number $-x$ is represented as $P - x$ (a very large positive number). 
* **Comparison**: To compare $a < b$ where $a$ might be negative, you must use `Num2Bits` to check the sign bit (bit 253) or shift values into a safe range.

### 5. Absolute Value Shielding
When performing division or scaling on signed numbers, follow this pipeline to avoid field overflow errors:
1.  Extract the sign bit via `Num2Bits(254)`.
2.  Convert to absolute value: `abs <== sign * (-2 * val) + val;`
3.  Perform unsigned arithmetic (div/mod) on the `abs` value.
4.  Re-apply the sign to the result: `out <== (1 - 2 * sign) * abs_result;`

### 6. Signal Immutability
Signals are constants once assigned. If you need to update a value in a loop (like an accumulator), use a `var` for intermediate calculation or a signal array (`s[i]`) for sequential constraints.

### 7. Bit-Length Safety (Aliasing)
Always specify the bit-length in comparators (e.g., `LessThan(252)`). Using the full 254 bits of the prime field can lead to "aliasing" where a value wraps around the prime $P$. 252 bits is the standard safety limit.

### 8. Boolean Logic Arithmetization
Translate logical gates into polynomials to stay within the arithmetic circuit paradigm:
* `NOT(a)` $\rightarrow$ `1 - a`
* `AND(a, b)` $\rightarrow$ `a * b`
* `OR(a, b)` $\rightarrow$ `a + b - a * b`

### 9. Priority Chains (Else-If Logic)
To simulate `if-else if-else`, ensure the selectors are mutually exclusive to avoid adding results together.
* `isA <== condA;`
* `isB <== (1 - isA) * condB;` // B only triggers if A is false.
* `isC <== (1 - isA) * (1 - isB);` // C is the default "else" case.

### 10. The Zero-Division Trap
Always handle the case where a divisor might be zero using the `IsZero()` component. A division by zero during witness generation (`<--`) will cause the prover to crash or produce an invalid proof.

### 11. Integer Scaling (Fixed-Point)
Since ZK circuits do not support floating-point numbers, multiply your values by a large power of 10 (scaling factor) before dividing to maintain precision.
* **Rule**: `(numerator * scale) / denominator`.

### 12. Linear vs. Non-Linear Constraints
Multiplying a signal by a constant (e.g., `out <== a * 5;`) is a "linear" constraint and is computationally cheap. Multiplying two signals (e.g., `out <== a * b;`) is "non-linear" and increases the proof size.

### 13. Witness vs. Constraint Separation
Use `<--` (assignment) for values that are computationally expensive but easy to verify (e.g., square roots or private hints). Always follow with `===` (enforcement) to ensure the prover is honest.

### 14. Range Proofs
Always enforce that inputs stay within expected bounds (e.g., $0-2^{32}-1$). Never assume an input is "small" just because it looks like a small integer; in $F_p$, it could be a malicious large value.

### 15. The Mux Formula (Standard Selection)
For any basic ternary operation `res = condition ? a : b`, use the optimized quadratic form:
`out <== condition * (a - b) + b;`

### 16. Component Encapsulation
Keep templates small and modular. If a piece of logic involves more than 5-10 complex constraints, wrap it in a separate `template` to improve readability and debuggability.

### 17. Constant Bit-Widths
When using `Num2Bits(n)`, ensure $n$ is a constant known at compile time. Dynamic bit-widths are not supported in Circom.

### 18. Avoid Nested Signal Declarations
Do not declare `signal` or `component` inside a `for` loop that depends on an input variable. All signals must be declared in the top-level scope or as fixed-size arrays.

### 19. Underflow Awareness
In $F_p$, $3 - 5$ does not result in $-2$ directly; it results in $P-2$. While this works for addition/subtraction, it breaks comparisons. Always use comparators designed for the field.

### 20. Deterministic Constraints
Every `output` signal must be constrained to a unique value. An unconstrained output allows a malicious prover to pick any value they want, breaking the soundness of the ZK proof.
"""


# [IR-Pseudo] 侧重电路逻辑约束
PSEUDO_SYSTEM_PROMPT = """You are a Zero-Knowledge Circuit Compiler.

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

[Constraint System]"""

# [IR-Summary] 侧重功能描述
SUMMARY_SYSTEM_PROMPT = """You are a ZK-SNARK Consultant. 
Provide a high-level functional summary of the code. 
Focus on:
1. The mathematical objective.
2. The data flow from input signals to results.
3. Essential arithmetic operations to be preserved.
Do not include source code in your output."""

# [IR-CoT] 结构化思维链
COT_SYSTEM_PROMPT = """You are a ZK Constraint Engineer.

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










"""


# [Iterative-Fix] 调试修复
FIX_STAGE2_SYSTEM_PROMPT = """You are a Circom Debugger. 
Review the Circom code against the original logic. 
Output ONLY the corrected Circom code."""


# ==========================================
# 2. One-Shot 示例定义
# ==========================================

# 不同语言的示例代码
LANGUAGE_EXAMPLES = {
    "Python": "def simple_max(a, b):\n    if a >= b:\n        return a\n    else:\n        return b",
    "Go": "func simpleMax(a, b int) int {\n    if a >= b {\n        return a\n    }\n    return b\n}",
    "Rust": "fn simple_max(a: i32, b: i32) -> i32 {\n    if a >= b {\n        return a;\n    }\n    b\n}",
    "Java": "public int simpleMax(int a, int b) {\n    if (a >= b) {\n        return a;\n    }\n    return b;\n}"
}

# Circom答案模板
CIRCOM_ANSWER = """include "node_modules/circomlib/circuits/comparators.circom";
template SimpleMax() {
    signal input a;
    signal input b;
    signal output out;
    component gte = GreaterEqThan(64);
    gte.in[0] <== a;
    gte.in[1] <== b;
    signal sel <== gte.out;
    out <== sel * (a - b) + b;
}
component main = SimpleMax();"""

# 中间表示到代码的one-shot示例
PSEUDO_TO_CODE_ONESHOT = """
Example:
Based ONLY on this circuit pseudo-logic, implement the Circom 2.1.4 template SimpleMax:

[Signal Declarations]
- public input: a, b
- intermediate signal: gte_out, sel
- output: out

[Witness Computation]
gte_out = compare(a >= b)
sel = gte_out
out = sel * (a - b) + b

[Constraint System]
gte_out * (gte_out - 1) == 0
out == sel * (a - b) + b

include "node_modules/circomlib/circuits/comparators.circom";
template SimpleMax() {
    signal input a;
    signal input b;
    signal output out;
    component gte = GreaterEqThan(64);
    gte.in[0] <== a;
    gte.in[1] <== b;
    signal sel <== gte.out;
    out <== sel * (a - b) + b;
}
component main = SimpleMax();"""

SUMMARY_TO_CODE_ONESHOT = """
Example:
Based ONLY on this summary, implement the Circom 2.1.4 template SimpleMax:

The function computes the maximum of two input values a and b. It performs a comparison operation to determine if a is greater than or equal to b, then selects the larger value using arithmetic selection. The output is the maximum of the two inputs.

include "node_modules/circomlib/circuits/comparators.circom";
template SimpleMax() {
    signal input a;
    signal input b;
    signal output out;
    component gte = GreaterEqThan(64);
    gte.in[0] <== a;
    gte.in[1] <== b;
    signal sel <== gte.out;
    out <== sel * (a - b) + b;
}
component main = SimpleMax();"""

COT_TO_CODE_ONESHOT = """
Example:
Based on this 5-step analysis, implement the Circom 2.1.4 template SimpleMax:

Step 1: Mathematical Objective
Prove that the output equals the maximum of two input values.

Step 2: Signal Graph Construction
- Inputs: a, b
- Intermediate: gte_out (comparison result), sel (selector)
- Output: out

Step 3: Control Flow Flattening
Replace if-else with arithmetic selection: out = sel * (a - b) + b, where sel = 1 if a >= b, else 0

Step 4: Constraint Extraction
- gte_out * (gte_out - 1) == 0 (binary constraint)
- out == sel * (a - b) + b (selection constraint)

Step 5: Circom Mapping
Use GreaterEqThan comparator and arithmetic selection formula.

include "node_modules/circomlib/circuits/comparators.circom";
template SimpleMax() {
    signal input a;
    signal input b;
    signal output out;
    component gte = GreaterEqThan(64);
    gte.in[0] <== a;
    gte.in[1] <== b;
    signal sel <== gte.out;
    out <== sel * (a - b) + b;
}
component main = SimpleMax();"""

def get_basic_one_shot(lang):
    """获取Basic策略的one-shot示例"""
    example_code = LANGUAGE_EXAMPLES.get(lang, LANGUAGE_EXAMPLES["Python"])
    return f"""Example: \n Translate the following {lang} function into a Circom 2.1.4 template named SimpleMax. Base your translation SOLELY on the retrieved templates and documentation above. Follow the syntax style from the retrieved examples:
{example_code}

{CIRCOM_ANSWER}"""

def get_knowledge_one_shot(lang):
    """获取Knowledge策略的one-shot示例"""
    example_code = LANGUAGE_EXAMPLES.get(lang, LANGUAGE_EXAMPLES["Python"])
    return f"""{DOMAIN_KNOWLEDGE_EN}

Example: \n Translate this {lang} code into Circom 2.1.4 template SimpleMax:
{example_code}

{CIRCOM_ANSWER}"""


def get_rag_one_shot(lang):
    """获取RAG策略的one-shot示例（不包含固定领域知识）"""
    example_code = LANGUAGE_EXAMPLES.get(lang, LANGUAGE_EXAMPLES["Python"])
    return f"""Example: \n Translate this {lang} code into Circom 2.1.4 template SimpleMax:
{example_code}

{CIRCOM_ANSWER}"""

def get_pseudo_one_shot(lang):
    """获取IR-Pseudo策略的one-shot示例"""
    example_code = LANGUAGE_EXAMPLES.get(lang, LANGUAGE_EXAMPLES["Python"])
    return f"""Example: \n Convert this {lang} code into circuit-level pseudo-logic:
{example_code}

[Signal Declarations]
- public input: a, b
- intermediate signal: gte_out, sel
- output: out

[Witness Computation]
gte_out = compare(a >= b)
sel = gte_out
out = sel * (a - b) + b

[Constraint System]
gte_out * (gte_out - 1) == 0
out == sel * (a - b) + b"""

def get_summary_one_shot(lang):
    """获取IR-Summary策略的one-shot示例"""
    example_code = LANGUAGE_EXAMPLES.get(lang, LANGUAGE_EXAMPLES["Python"])
    return f"""Example: \n Summarize the mathematical flow of this {lang} function:
{example_code}

The function computes the maximum of two input values a and b. It performs a comparison operation to determine if a is greater than or equal to b, then selects the larger value using arithmetic selection. The output is the maximum of the two inputs."""

def get_cot_one_shot(lang):
    """获取IR-CoT策略的one-shot示例"""
    example_code = LANGUAGE_EXAMPLES.get(lang, LANGUAGE_EXAMPLES["Python"])
    return f"""Example: \n Analyze this {lang} code for ZK implementation:
{example_code}

Step 1: Mathematical Objective
Prove that the output equals the maximum of two input values.

Step 2: Signal Graph Construction
- Inputs: a, b
- Intermediate: gte_out (comparison result), sel (selector)
- Output: out

Step 3: Control Flow Flattening
Replace if-else with arithmetic selection: out = sel * (a - b) + b, where sel = 1 if a >= b, else 0

Step 4: Constraint Extraction
- gte_out * (gte_out - 1) == 0 (binary constraint)
- out == sel * (a - b) + b (selection constraint)

Step 5: Circom Mapping
Use GreaterEqThan comparator and arithmetic selection formula."""

# ==========================================
# 3. 策略函数实现
# ==========================================

def get_completion(system_prompt, user_prompt):
    """通用请求封装"""
    try:
        response = client.chat.completions.create(
            model="xx",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            timeout=120,
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error API Call: {str(e)}"


def clean_code(text):
    """提取 Circom 代码块"""
    if "```circom" in text:
        return text.split("```circom")[1].split("```")[0].strip()
    elif "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text.strip()


# --- 各策略逻辑 ---

def translate_basic(src, lang, name):
    one_shot = get_basic_one_shot(lang)
    prompt = f"{one_shot}\n\nTask: \nTranslate the following {lang} function into a Circom 2.1.4 template named {name}:\n{src}"
    return clean_code(get_completion("You are a code translator. Output only Circom code.", prompt))


def translate_knowledge(src, lang, name):
    one_shot = get_knowledge_one_shot(lang)
    prompt = f"{one_shot}\n\nTask: \nTranslate this {lang} code into Circom 2.1.4 template {name}:\n{src}"
    return clean_code(get_completion("You are a code translator.", prompt))


def translate_rag(src, lang, name, retrieved_content):
    """RAG策略：使用检索到的内容辅助翻译"""
    # 构建RAG上下文
    retrieved_code = "\n".join([f"// {item['title']}\n{item['text']}" for item in retrieved_content.get('retrieved_code', [])])
    retrieved_doc = "\n".join(retrieved_content.get('retrieved_doc', []))
    
    rag_context = """
=== Retrieved Circom Templates ===
{retrieved_code}

=== Retrieved Documentation ===
{retrieved_doc}
    """.format(retrieved_code=retrieved_code, retrieved_doc=retrieved_doc).strip()
    
    one_shot = get_rag_one_shot(lang)
    prompt = f"\n{rag_context}\n{one_shot}\n\nTask: \nTranslate this {lang} code into Circom 2.1.4 template {name}. Base your translation SOLELY on the retrieved templates and documentation above. Follow the syntax style from the retrieved examples:\n{src}"
    return clean_code(get_completion("You are a code translator.", prompt))


def translate_ir_pseudo(src, lang, name):
    one_shot = get_pseudo_one_shot(lang)
    prompt = f"{one_shot}\n\nTask: \nConvert this {lang} code into circuit-level pseudo-logic:\n{src}"
    pseudo_ir = get_completion(PSEUDO_SYSTEM_PROMPT, prompt)
    target_prompt = f"{PSEUDO_TO_CODE_ONESHOT}\n\nTask: \nBased ONLY on this circuit pseudo-logic, implement the Circom 2.1.4 template {name}:\n\n{pseudo_ir}"
    circom_output = clean_code(get_completion("You are a Circom expert.", target_prompt))
    return {
        "circom_code": circom_output,
        "intermediate": pseudo_ir
    }


def translate_ir_summary(src, lang, name):
    one_shot = get_summary_one_shot(lang)
    prompt = f"{one_shot}\n\nTask: \nSummarize the mathematical flow of this {lang} function:\n{src}"
    summary_ir = get_completion(SUMMARY_SYSTEM_PROMPT, prompt)
    target_prompt = f"{SUMMARY_TO_CODE_ONESHOT}\n\nTask: \nBased ONLY on this summary, implement the Circom 2.1.4 template {name}:\n\n{summary_ir}"
    circom_output = clean_code(get_completion("You are a Circom expert.", target_prompt))
    return {
        "circom_code": circom_output,
        "intermediate": summary_ir
    }


def translate_ir_cot(src, lang, name):
    one_shot = get_cot_one_shot(lang)
    prompt = f"{one_shot}\n\nTask: \nAnalyze this {lang} code for ZK implementation:\n{src}"
    cot_ir = get_completion(COT_SYSTEM_PROMPT, prompt)
    target_prompt = f"{COT_TO_CODE_ONESHOT}\n\nTask: \nBased on this 5-step analysis, implement the Circom 2.1.4 template {name}:\n\n{cot_ir}"
    circom_output = clean_code(get_completion("You are a Circom expert.", target_prompt))
    return {
        "circom_code": circom_output,
        "intermediate": cot_ir
    }



# ==========================================
# 3. 自动化批处理实验引擎
# ==========================================

STRATEGIES = {
    "basic": translate_basic,
    "knowledge": translate_knowledge,
    "rag": translate_rag,
    "ir_pseudo": translate_ir_pseudo,
    "ir_summary": translate_ir_summary,
    "ir_cot": translate_ir_cot,
}


def run_experiment():
    # 使用enriched dataset
    input_path = "dataset_enriched.jsonl"
    lang_map = {"py": "Python", "go": "Go", "rs": "Rust", "jv": "Java"}

    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found!")
        return

    # 读取所有任务
    with open(input_path, 'r', encoding='utf-8') as f:
        all_tasks = [json.loads(line) for line in f if line.strip()]

    print(f"Loaded {len(all_tasks)} tasks from dataset_enriched.jsonl")
    print("=" * 60)

    # 依次处理每个任务
    for task in all_tasks:
        task_id = task.get("id")
        func_name = task.get("func_name")
        
        print(f"\n>>> [START] Task {task_id}: {func_name} <<<")
        
        # 依次跑完5种策略
        for strategy_name, strategy_func in STRATEGIES.items():
            output_path = f"xx_results_{strategy_name}_oneshot.jsonl"
            
            # 断点续传：读取已完成的任务
            finished = set()
            if os.path.exists(output_path):
                with open(output_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            d = json.loads(line)
                            finished.add((d["id"], d["source_lang"]))
            
            # 执行翻译逻辑
            with open(output_path, 'a', encoding='utf-8') as f_out:
                for l_key, l_full in lang_map.items():
                    # 如果该语言任务已完成或原数据中没有该语言代码，跳过
                    if (task_id, l_full) in finished or not task.get(l_key):
                        continue
                    
                    print(f"  - [{strategy_name}] Processing ({l_full})...")
                    
                    try:
                        source_code = task.get(l_key)
                        
                        # 处理RAG策略的特殊参数
                        if strategy_name == "rag":
                            output = strategy_func(source_code, l_full, func_name, task)
                        else:
                            output = strategy_func(source_code, l_full, func_name)
                        
                        # 处理IR策略返回的字典格式
                        if isinstance(output, dict):
                            circom_code = output["circom_code"]
                            intermediate = output["intermediate"]
                        else:
                            circom_code = output
                            intermediate = None
                        
                        result = {
                            "id": task_id,
                            "func_name": func_name,
                            "source_lang": l_full,
                            "translated_circom": circom_code,
                            "strategy": strategy_name,
                            "timestamp": time.strftime("%H:%M:%S")
                        }
                        
                        # 如果是IR策略，保存中间结果
                        if intermediate:
                            result["intermediate_result"] = intermediate
                        
                        f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
                        f_out.flush()
                        
                        # 单独保存中间结果到文件
                        if intermediate:
                            intermediate_path = f"intermediate_results_{strategy_name}_oneshot.jsonl"
                            with open(intermediate_path, 'a', encoding='utf-8') as f_inter:
                                intermediate_result = {
                                    "id": task_id,
                                    "func_name": func_name,
                                    "source_lang": l_full,
                                    "intermediate": intermediate,
                                    "strategy": strategy_name,
                                    "timestamp": time.strftime("%H:%M:%S")
                                }
                                f_inter.write(json.dumps(intermediate_result, ensure_ascii=False) + "\n")
                                f_inter.flush()
                    
                    except Exception as e:
                        print(f"  [ERROR] ({l_full}) failed: {e}")
                        continue


if __name__ == "__main__":
    run_experiment()
    print("\n[FINISH] All 5 strategies (One-Shot) have been processed.")