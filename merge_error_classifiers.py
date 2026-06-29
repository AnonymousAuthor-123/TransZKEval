import json
import re
import os
import sympy
from pathlib import Path
from collections import defaultdict
from sympy import symbols, expand, Poly

# --- 从 p1012.py 导入相关函数 ---
def get_pure_p1012_labels(code_line):
    labels = []
    clean_line = re.sub(r'//.*$', '', code_line).strip()
    clean_line = re.sub(r'^\d+\s+', '', clean_line)
    if not clean_line: return []

    # 1. 非法比较表达式 (==)
    if re.search(r"(?<![<=!])==(?!=)", clean_line):
        if not any(k in clean_line for k in ["var ", "for ", "if ", "while "]):
            labels.append("P1012-FEAT-Illegal-Comparison-Expression")

    # 2. 非法运算符 (优化：加入对 !== 和 C-style cast 的捕获)
    # 捕获 <, >, %, !=, !==, (int)
    if re.search(r"(?<!<)<(?!=)|(?<!=)>(?!=)|%|!=|(?<![<=!])=(?!=)|\(int\)", clean_line):
        if "==" not in clean_line and not any(k in clean_line for k in ["var ", "for ", "if ", "while "]):
            labels.append("P1012-FEAT-Illegal-Operator-In-Expression")

    # 3. 非法语境下的声明/关键字/导入
    # 增加对 component 作为块定义的捕获
    if re.search(r"\bimport\b|\binclude\b\s*\{|\bcomponent\s+\w+\s*\{", clean_line) or \
       re.search(r"(signal\s+)?(input|output)\s+.*(<==|===|=)", clean_line) or \
       re.search(r"signal\s*\w*\[", clean_line) or \
       "signal var" in clean_line or "constraint" in clean_line:
        labels.append("P1012-FEAT-Illegal-Context-Declaration")

    # 4. 类型或索引构造非法 (Type/Index)
    if re.search(r"(?<!signal)\w+\[\d+\]", clean_line) or ("*" in clean_line and ".out" not in clean_line):
        if not any(k in clean_line for k in ["signal", "var"]):
            labels.append("P1012-FEAT-Index-Illegal-Expression")

    # 5. 函数式/逻辑/复杂结构
    if re.search(r"\b(if|then|else|range|in)\b|\.\.|\?|&&", clean_line):
        if "input " not in clean_line:
            labels.append("P1012-FEAT-Functional-Logic-Hallucination")

    # 6. 裸表达式或结构坍塌
    if (re.search(r"^\w+\([^;]*\);?$", clean_line) and "component" not in clean_line) or \
       clean_line in ["}", "{", "};" , "];"] or re.search(r"^[a-zA-Z0-9_]+\s*[\+\-]\s*[a-zA-Z0-9_]+;?$", clean_line):
        labels.append("P1012-FEAT-Bare-Illegal-Expression")

    return labels

# --- 从 p1008.py 导入相关函数 ---
def get_pure_p1008_labels(code_line):
    labels = []
    clean_line = re.sub(r'^\d+\s+', '', code_line.strip())
    if not clean_line: return []

    # --- 维度 A: 组件作用域与声明幻觉 (Block/Scope) ---
    # 捕获像 "component GreaterEqThan {" 这种试图开启一个块的非法写法
    if re.search(r"component\s+\w+\s*\{", clean_line):
        labels.append("P1008-FEAT-Component-Block-Decl-Hallucination")

    # --- 维度 B: 命令式关键字污染 (Language Hybrid) ---
    # 1. 公共属性幻觉 (之前的大头)
    if "component" in clean_line and "public" in clean_line:
        labels.append("P1008-FEAT-Component-Public-Hallucination")

    # 2. 实例化幻觉 (使用了 new 关键字)
    if "component" in clean_line and " new " in clean_line:
        labels.append("P1008-FEAT-Component-New-Operator-Hallucination")

    # --- 维度 D: 结构畸形 (Stray Brackets) ---
    # 捕获类似 ]} = shuffle_integrity_logic(); 这种完全崩溃的结构
    if re.search(r"^[\]\} \t]+=", clean_line):
        labels.append("P1008-FEAT-Structural-Collapse")

    # 3. 信号修饰符与类型幻觉
    if re.search(r"signal\s+(constant|intermediate|mutable|witness|bool|int|long|i64|u\d+|FT|private|local)", 
                 clean_line, re.I) or \
            re.search(r"\s+of\s+(i64|FT|field|int)", clean_line):
        labels.append("P1008-FEAT-Invalid-Signal-Type-Modifier")

    # 4. 块声明残缺 (New!)
    # 捕获 component Name { 或 constraint Name { 这种没有结尾的声明行
    if re.search(r"\b(component|template|constraint|function)\b.*\{$", clean_line):
        labels.append("P1008-FEAT-Incomplete-Statement")

    # 5. 编程语言混淆 (const/let/for)
    if re.search(r"\b(const\s+uint|const\s+int|let\s+|uint256|i64\s+|for\s*\()", clean_line):
        labels.append("P1008-FEAT-Foreign-Language-Declaration")

    # 6. 语法截断/残缺 (以赋值或运算符结尾)
    if clean_line.endswith(("=", "<", ">", "?", ":", "+", "-", "*", "/")):
        labels.append("P1008-FEAT-Incomplete-Statement")

    # 7. 链式/多重赋值与括号畸形 (New: 增加对 stray brackets 的识别)
    if clean_line.count("<==") > 1 or clean_line.count("===") > 1 or clean_line.count("=") > 1:
        if "signal" not in clean_line and "component" not in clean_line:
            labels.append("P1008-FEAT-Chained-Assignment-Hallucination")

    # 8. 非法符号 (整除/位运算)
    if "//" in clean_line:
        labels.append("P1008-FEAT-Python-Style-Division")
    if any(op in clean_line for op in [">>", "<>", "&", "|", "^"]) and "//" not in clean_line:
        labels.append("P1008-FEAT-Bitwise-Operation-Hallucination")

    # 9. 特殊后缀与逻辑 (as / when / with)
    if re.search(r"\s+(as|when|with)\s+", clean_line):
        labels.append("P1008-FEAT-Incomplete-Statement")

    return labels

# --- 从 1008+1012nlp.py 导入相关函数 ---
def get_comprehensive_labels(code_line, codes):
    """
    根据错误码集合动态生成标签前缀并捕获深度特征
    """
    labels = []
    has_1008 = "P1008" in codes
    has_1012 = "P1012" in codes

    if has_1008 and has_1012:
        prefix = "P1008+P1012"
    elif has_1008:
        prefix = "P1008"
    elif has_1012:
        prefix = "P1012"
    else:
        return []

    clean_line = re.sub(r'^\d+\s+', '', code_line.strip())

    # --- 特征检测逻辑 ---
    if "signal" in clean_line and "=" in clean_line and "<==" not in clean_line:
        labels.append(f"{prefix}-FEAT-Decl-Init-Fusion")
    if re.search(r"\(int\)|\(long\)|as\s+int|as\s+field", clean_line, re.I):
        labels.append(f"{prefix}-FEAT-Type-Casting-Hallucination")
    decl_match = re.search(r"signal\s+([^;,<=]+)", clean_line)
    if decl_match:
        words = decl_match.group(1).strip().split()
        core_words = [w for w in words if w not in ['input', 'output']]
        if len(core_words) > 1:
            labels.append(f"{prefix}-FEAT-Invalid-Type-Declaration")
    if "//" in clean_line:
        labels.append(f"{prefix}-FEAT-Python-Style-Division")
    if re.search(r"\+=|-=|<=[\+=\-]|={2,}>", clean_line):
        labels.append(f"{prefix}-FEAT-Invalid-Assignment-Operator")
    if any(op in clean_line for op in ['&&', '||', '!', '?', ':']):
        labels.append(f"{prefix}-FEAT-Boolean-Ternary-Logic")
    if any(op in clean_line for op in ['&', '|', '^', '<<', '>>']) and "//" not in clean_line:
        labels.append(f"{prefix}-FEAT-Bitwise-Operation")
    if re.search(r'(<==|=).+===|(<==|=).+<==|(===).+===', clean_line):
        labels.append(f"{prefix}-FEAT-Nested-Constraint-Conflict")
    if "signal" in clean_line and "===" in clean_line:
        labels.append(f"{prefix}-FEAT-Decl-Constraint-Conflict")
    if re.search(r"\w+\.\w+\(", clean_line):
        labels.append(f"{prefix}-FEAT-Namespace-Method-Hallucination")
    if re.search(r"\w+\s*\([^)]*\)\s*[\.\[]", clean_line):
        labels.append(f"{prefix}-FEAT-Anonymous-Component-Access")
    if any(kw in clean_line for kw in ["if ", "then ", "else ", "for ", "loop ", "const ", "let"]):
        labels.append(f"{prefix}-FEAT-Keyword-Hallucination")
    if re.search(r"\d+[nL]", clean_line):
        labels.append(f"{prefix}-FEAT-Numeric-Suffix-Hallucination")
    if re.search(r'\d+\.\d+', clean_line):
        labels.append(f"{prefix}-FEAT-Floating-Point-Hallucination")

    return labels

# --- 从 t2021nlp.py 导入相关函数 ---
# --- 核心语义桶：定义该类别的关键词特征 (支持正则前缀) ---
SEMANTIC_BUCKETS = {
    # 1. 乘法类：包含平方 (Square)
    "Arithmetic-Mul": r"Mul|Mult|Multiplier|Multiply|BigMul|fpmul|Pow|Power|matElemPow|Scale|dotProduct|dp3|Square|square",

    # 2. 除模类：涉及逆运算
    "Arithmetic-DivMod": r"Div|Divide|Divider|Quotient|QuotientAndRemainder|QuinMultiBitDiv|reciprocal|Mod|Modulo|InverseModulo|InvModulo|ModularInverse|Inv|Inverse|FieldInverse|Rem|PrimeReduce",

    # 3. 加减类
    "Arithmetic-AddSub": r"Add|Adder|Addition|Sum|Sub|Subtract|Neg|Abs|Absolute|Total|Difference|mean|deviation|Dec|round|Clamp|RLM",

    # 4. 逻辑比较：包含 Sel, Bool, Binary 判断
    "Logic-Comparison": r"Equal|Eq|Neq|Zero|Lt|LessThan|Gt|GreaterThan|GeThan|Gte|Max|Min|Compare|Range|Sign|IsPositive|IsGreater|IsLess|IsOdd|IsOne|IsLeap|isOne|InList|Greater|Less|Ge|And|Or|Xor|Not|Gate|Mux|Selector|Select|Cond|If|Swap|Ternary|Sel|Bool",

    # 5. 位与数据处理：包含 int, uint256, ToBinary 等类型操作
    "Bit-Data-Ops": r"Bit|Num2|Bits2|Shift|SHL|SHR|Decompose|BitExtract|Bitify|Array|Sort|Lookup|Table|Stack|Heap|Search|Counter|int|uint256|ToBinary|FromBinary|DigitBytesToInt|binaryCheck|Binary",

}

def get_canonical_name_v2(entity):
    """
    通过语义提取和正则模糊匹配确定类别
    """
    # 1. 预处理：如果是 Anonymous 或空，直接返回
    if not entity or entity == "Anonymous":
        return "Unclassified-Entity-Anonymous"

    # 2. 遍历语义桶进行正则模糊匹配 (不区分大小写)
    for canonical, pattern in SEMANTIC_BUCKETS.items():
        if re.search(pattern, entity, re.IGNORECASE):
            return canonical

    # 3. 如果没有任何匹配，返回原始名称以便后续分析
    return "Others"

def get_t2021_refined_features(code_line, block_text):
    features = []
    # 匹配 T2021 错误描述
    desc_match = re.search(r"error\[T2021\]:\s*(.*)", block_text)
    raw_desc = desc_match.group(1).strip() if desc_match else "Unknown"

    # 清洗代码行，提取函数/符号名
    clean_line = re.sub(r'^\d+\s+', '', code_line.strip())

    if "Calling symbol" in raw_desc:
        # 提取函数名，如 a = MyFunc(b) -> MyFunc
        entity_match = re.search(r"=\s*([a-zA-Z0-9_]+)\s*\(", clean_line)
        if not entity_match:
            entity_match = re.search(r"([a-zA-Z0-9_]+)\s*\(", clean_line)

        entity = entity_match.group(1) if entity_match else "Anonymous"

        # 使用语义 V2 进行分类
        canonical = get_canonical_name_v2(entity)
        features.append(f"T2021 >> Calling-Symbol >> {canonical}")

    elif "Undeclared symbol" in raw_desc:
        features.append("T2021 >> Undeclared-Symbol")

    return features

# --- 从 t3001.py 导入相关函数 ---
def preprocess_circom_code(rhs):
    """
    专门解决 SymPy 无法解析 Circom 特有语法的问题
    """
    # 1. 剔除行首可能存在的行号 (如 "39  diff*diff")
    rhs = re.sub(r'^\s*\d+\s+', '', rhs)

    # 2. 处理点号：lt.out -> lt__out (防止 AttributeError: 'Symbol' object has no attribute 'out')
    rhs = rhs.replace('.', '__')

    # 3. 处理关键字：将独立的 'in' 替换为 'in_sig' (防止 SyntaxError: invalid syntax)
    rhs = re.sub(r'\bin\b', 'in_sig', rhs)

    # 4. 移除数组下标 [i][j]
    rhs = re.sub(r'\[.*?\]', '', rhs)

    return rhs.strip()

def count_physical_gates(expr):
    """
    通过 AST 递归统计物理乘法门数量 (判断 a*b + c*d)
    """
    if expr.is_Add:
        gate_count = 0
        for term in expr.args:
            try:
                # 统计阶数大于等于2的单项式
                if not term.is_number and Poly(term).total_degree() >= 2:
                    gate_count += 1
            except:
                # 如果包含非多项式算子，根据星号粗略判定
                if term.has(sympy.Symbol) and "*" in str(term):
                    gate_count += 1
        return gate_count

    try:
        if not expr.is_number and Poly(expr).total_degree() >= 2:
            return 1
    except:
        pass
    return 0

def analyze_algebraic_violation(code_line):
    # 1. 提取并预处理 RHS
    rhs_raw = code_line
    for op in ["<==", "===", "="]:
        if op in code_line:
            rhs_raw = code_line.split(op)[1]
            break

    # 深度清洗：解决点号、关键字、行号问题
    rhs = preprocess_circom_code(rhs_raw).replace(';', '')

    # 2. 拦截非代数/逻辑算子
    if any(op in rhs for op in ['%', '\\', '!', '?', ':']):
        return "Alg: Forbidden Operator (Non-Polynomial)"
    if '/' in rhs:
        return "Alg: Forbidden Division"
    if re.search(r'(&|\||\^|<<|>>)', rhs):
        return "Alg: Forbidden Bitwise Op"
    if re.search(r'(>=|<=|>|<|==|!=)', rhs):
        return "Alg: Comparison Logic (Non-Algebraic)"

    try:
        # 3. 符号化 (不使用后缀，直接映射清洗后的词)
        all_words = set(re.findall(r'\b[a-zA-Z_]\w*\b', rhs))
        # 此时 all_words 中已经包含了清洗后的 lt__out 等词
        safe_sym_map = {word: symbols(word) for word in all_words}

        # 4. 建立原始表达式 (禁止自动计算，保留 a*b + c*d 结构)
        raw_expr = sympy.sympify(rhs, locals=safe_sym_map, evaluate=False)

        # --- 判定 1: 物理门并列 ---
        # --- 判定 1: 物理门并列 (a*b + c*d) ---
        if count_physical_gates(raw_expr) >= 2:
            expanded_expr = expand(raw_expr)
            # 关键：检查展开/化简后，二次项的数量
            terms = expanded_expr.as_ordered_terms()
            quad_terms_after_expand = [t for t in terms if not t.is_number and Poly(t).total_degree() == 2]

            if len(quad_terms_after_expand) <= 1:
                # 展开后发现只有一个二次项，说明原始的两个乘法块其实可以合并
                # 典型案例：s*x + (1-s)*x -> x (线性) 或 s*x + (1-s)*y -> 无法完全合并
                # 但只要展开后 quadratic 项数减少了，就说明有化简空间
                return "Alg: Parallel Sum - Need Factorization"
            else:
                # 展开后依然有多个二次项，说明这物理上就是两个门，必须拆分
                # 典型案例：a*b + c*d
                return "Alg: Parallel Sum - Need Intermediate Signal"

        # --- 判定 2: 数学高阶 ---
        expanded_expr = expand(raw_expr)
        if expanded_expr.is_number:
            return "Alg: Constant/Linear"

        poly = Poly(expanded_expr)
        total_degree = poly.total_degree()

        if total_degree > 2:
            return f"Alg: High-Order Polynomial (Degree 3+)"

        # --- 判定 3: 混合项 (a*b + c) ---
        terms = expanded_expr.as_ordered_terms()
        quad_terms = []
        for t in terms:
            try:
                if not t.is_number and Poly(t).total_degree() == 2:
                    quad_terms.append(t)
            except:
                continue

        if len(quad_terms) == 1 and len(terms) > 1:
            #print(code_line)
            return "Alg: Mixed Quadratic-Linear (a*b + c)"

        return "Alg: Other"

    except Exception as e:
        # 如果还是报错，可能是出现了 unmatched ')' 等极端情况
        return f"Alg: Other"

def extract_error_line(error_msg):
    lines = [l.strip() for l in error_msg.split('\n') if l.strip()]
    for i, line in enumerate(lines):
        if "found here" in line and i > 0:
            for j in range(i - 1, -1, -1):
                curr = lines[j]
                code_match = re.search(r'│\s*(.*)$', curr)
                if code_match:
                    content = code_match.group(1).strip()
                    if content: return content
                if any(op in curr for op in ["<==", "===", "=", "*", "/"]):
                    return curr
    return ""

def classify_diagnostic_primary(error_msg):
    msg_match = re.search(r'error\[T3001\]:\s*(.*?)(?:\n|┌|$)', error_msg, re.DOTALL)
    if not msg_match: return "0-Unknown-Format"
    phrase = msg_match.group(1).strip()

    if "signal that is not initialized" in phrase: return "1-Signal-Not-Initialized"
    if "inputs are initialized" in phrase: return "2-Component-Input-Error"
    if "component that is not initialized" in phrase: return "3-Component-Def-Missing"
    if "Non quadratic" in phrase: return "4-Non-Quadratic-Violation"
    if "invalid assignment" in phrase or "cannot be re-assigned" in phrase: return "5-Invalid-Assignment"
    if "False assert" in phrase: return "6-Assert-Failed"
    if "Out of bounds" in phrase: return "7-Index-Error"
    if "Division by zero" in phrase: return "8-Div-Zero"
    return f"9-Other: {phrase[:20]}"

def get_major_category_feature(l1_label, line):
    if not line: return "No-Code-Line"
    if l1_label == "4-Non-Quadratic-Violation":
        return analyze_algebraic_violation(line)

    if l1_label == "1-Signal-Not-Initialized":
        # 预处理：去掉空格，方便精准匹配符号
        clean_line = line.replace(" ", "")

        # 1. 判定是否为“纯约束” (只有 ===)
        # 逻辑：含有 ===，但【不含有】 <== 且【不含有】 只有单个 = 的赋值
        # 注意：Circom 中 = 是赋值，== 是布尔相等(通常在if里)，=== 是约束
        has_constraint = "===" in clean_line
        has_assignment = "<==" in clean_line or (re.search(r'(?<![=<>!])=(?![=])', clean_line))

        if has_constraint and not has_assignment:
            # 只有约束，没有数据流来源
            return "Flow: Constraint-Only (Missing Assignment)"

        if has_assignment:
            # 只要有赋值符号且报错“未初始化”，说明引用的 RHS 信号还没准备好
            return "Flow: Sequence Violation (Topological Order)"

        return "Flow: General Initialization Gap"

    if l1_label == "5-Invalid-Assignment":
        parts = line.split("<==")
        if len(parts) > 1:
            left_var = re.search(r'([a-zA-Z_]\w*)', parts[0])
            if left_var and re.search(rf'\b{left_var.group(1)}\b', parts[1]):
                return "Assign: Imperative Self-Update (a = a+1)"
        return "Assign: Multiple Definition/Re-assign"
    return "N/A"

# --- 主函数 ---
def process_jsonl_files(input_dir, output_dir):
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # 遍历所有 JSONL 文件
    files = list(Path(input_dir).rglob('*.jsonl'))
    print(f"处理 {len(files)} 个文件...")

    for file_path in files:
        output_file = Path(output_dir) / file_path.name
        
        with open(file_path, 'r', encoding='utf-8') as f_in, open(output_file, 'w', encoding='utf-8') as f_out:
            for line in f_in:
                try:
                    data = json.loads(line)
                    error_msg = data.get("error_msg", "")
                    error_classify = []

                    # 处理 P1008 和 P1012 错误
                    if error_msg:
                        # 提取错误块
                        block_pattern = re.compile(r"error\[(P\d+)\]:.*?\n\s+\".+?\":\d+:\d+.*?\n\s+\n\s*(\d+)\s+(.*?)\n", re.DOTALL)
                        line_map = defaultdict(set)
                        matches = block_pattern.findall(error_msg)
                        
                        for err_code, line_num, content in matches:
                            if err_code in ["P1008", "P1012"]:
                                key = f"{line_num}_{content.strip()}"
                                line_map[key].add(err_code)
                        
                        # 处理错误，使用与原始程序相同的逻辑
                        for key, codes in line_map.items():
                            actual_code = key.split('_', 1)[1]
                            
                            # 对于纯 P1008 错误，使用 get_pure_p1008_labels
                            if codes == {"P1008"}:
                                labels = get_pure_p1008_labels(actual_code)
                                error_classify.extend(labels)
                            # 对于纯 P1012 错误，使用 get_pure_p1012_labels
                            elif codes == {"P1012"}:
                                labels = get_pure_p1012_labels(actual_code)
                                error_classify.extend(labels)
                            # 对于组合错误，使用 get_comprehensive_labels
                            elif "P1008" in codes and "P1012" in codes:
                                labels = get_comprehensive_labels(actual_code, codes)
                                error_classify.extend(labels)

                    # 处理 T2021 错误
                    if "error[T2021]" in error_msg:
                        blocks = re.findall(r"(error\[T2021\]:.*?(?=\n\nerror\[|\n\nprevious errors|$))", error_msg, re.DOTALL)
                        for block in blocks:
                            code_match = re.search(r"\n\s*(\d+\s+.*?)\n", block)
                            code_line = code_match.group(1) if code_match else ""
                            labels = get_t2021_refined_features(code_line, block)
                            error_classify.extend(labels)

                    # 处理 T3001 错误
                    if "error[T3001]" in error_msg:
                        l1 = classify_diagnostic_primary(error_msg)
                        code = extract_error_line(error_msg)
                        l2 = get_major_category_feature(l1, code)
                        error_classify.append(l2)

                    # 直接添加到数据中，不进行去重
                    data["error_classify"] = error_classify

                    # 写入输出文件
                    f_out.write(json.dumps(data, ensure_ascii=False) + '\n')
                except Exception as e:
                    # 如果出错，原样写入
                    f_out.write(line)

    print(f"处理完成，结果保存在 {output_dir}")

if __name__ == "__main__":
    input_directory = r"D:\py\TransZKEval\eval_results"
    output_directory = r"D:\py\TransZKEval\eval_results_with_error_classify"
    process_jsonl_files(input_directory, output_directory)