#!/usr/bin/env python3
"""Match Circom compiler diagnostics to the existing TransZKEval refine knowledge."""

from __future__ import annotations

from collections import defaultdict
import argparse
import json
from pathlib import Path
import re
import sys


CATALOG = Path(__file__).with_name("refine_knowledge.jsonl")
COMPILER_RE = re.compile(r"(?:^|[\s;&|()])(?:/[\w./-]+/)?circom(?:\s|$)", re.I)
DIAGNOSTIC_RE = re.compile(
    r"error\[[A-Z0-9]+\]|previous errors were found|no main specified|"
    r"missing semicolon|non quadratic|compiler error|thread ['\"]?main['\"]? panicked|"
    r"(?:^|\n)error:\s",
    re.I,
)
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _plain(text: str) -> str:
    return ANSI_RE.sub("", text or "")


def _clean_line(line: str) -> str:
    return re.sub(r"^\s*\d+\s+", "", line).strip().lstrip("│ ")


def _diagnostic_blocks(text: str):
    starts = list(re.finditer(r"error\[([A-Z0-9]+)\]:", text, re.I))
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[match.start():end]
        numbered = re.findall(r"(?m)^\s*\d+\s+(.*?)\s*$", block)
        code_line = next((_clean_line(line) for line in numbered if _clean_line(line)), "")
        yield match.group(1).upper(), code_line, block


def _p1008(line: str):
    labels = []
    if re.search(r"component\s+\w+\s*\{", line):
        labels.append("P1008-FEAT-Component-Block-Decl-Hallucination")
    if "component" in line and "public" in line:
        labels.append("P1008-FEAT-Component-Public-Hallucination")
    if "component" in line and " new " in f" {line} ":
        labels.append("P1008-FEAT-Component-New-Operator-Hallucination")
    if re.search(r"^[\]\}\s]+=", line):
        labels.append("P1008-FEAT-Structural-Collapse")
    if re.search(r"signal\s+(constant|intermediate|mutable|witness|bool|int|long|i64|u\d+|FT|private|local)", line, re.I) or re.search(r"\s+of\s+(i64|FT|field|int)", line):
        labels.append("P1008-FEAT-Invalid-Signal-Type-Modifier")
    if re.search(r"\b(component|template|constraint|function)\b.*\{$", line) or line.endswith(("=", "<", ">", "?", ":", "+", "-", "*", "/")):
        labels.append("P1008-FEAT-Incomplete-Statement")
    if re.search(r"\b(const\s+uint|const\s+int|let\s+|uint256|i64\s+|for\s*\()", line):
        labels.append("P1008-FEAT-Foreign-Language-Declaration")
    if line.count("<==") > 1 or line.count("===") > 1:
        labels.append("P1008-FEAT-Chained-Assignment-Hallucination")
    if "//" in line:
        labels.append("P1008-FEAT-Python-Style-Division")
    if any(op in line for op in (">>", "<>", "&", "|", "^")) and "//" not in line:
        labels.append("P1008-FEAT-Bitwise-Operation-Hallucination")
    return labels


def _p1012(line: str):
    labels = []
    if re.search(r"(?<![<=!])==(?!=)", line) and not any(k in line for k in ("var ", "for ", "if ", "while ")):
        labels.append("P1012-FEAT-Illegal-Comparison-Expression")
    if re.search(r"(?<!<)<(?!=)|(?<!=)>(?!=)|%|!=|(?<![<=!])=(?!=)|\(int\)", line) and "==" not in line and not any(k in line for k in ("var ", "for ", "if ", "while ")):
        labels.append("P1012-FEAT-Illegal-Operator-In-Expression")
    if re.search(r"\bimport\b|\binclude\b\s*\{|\bcomponent\s+\w+\s*\{", line) or re.search(r"(signal\s+)?(input|output)\s+.*(<==|===|=)", line) or "signal var" in line or "constraint" in line:
        labels.append("P1012-FEAT-Illegal-Context-Declaration")
    if re.search(r"\b(if|then|else|range|in)\b|\.\.|\?|&&", line) and "input " not in line:
        labels.append("P1012-FEAT-Functional-Logic-Hallucination")
    if (re.search(r"^\w+\([^;]*\);?$", line) and "component" not in line) or line in ("}", "{", "};", "];" ):
        labels.append("P1012-FEAT-Bare-Illegal-Expression")
    return labels


def _combined(line: str, prefix: str):
    labels = []
    add = lambda suffix: labels.append(f"{prefix}-FEAT-{suffix}")
    if "signal" in line and "=" in line and "<==" not in line:
        add("Decl-Init-Fusion")
    if re.search(r"\(int\)|\(long\)|as\s+int|as\s+field", line, re.I):
        add("Type-Casting-Hallucination")
    declaration = re.search(r"signal\s+([^;,<=]+)", line)
    if declaration and len([word for word in declaration.group(1).split() if word not in ("input", "output")]) > 1:
        add("Invalid-Type-Declaration")
    if "//" in line:
        add("Python-Style-Division")
    if re.search(r"\+=|-=|<=[+=-]|={2,}>", line):
        add("Invalid-Assignment-Operator")
    if any(op in line for op in ("&&", "||", "!", "?", ":")):
        add("Boolean-Ternary-Logic")
    if any(op in line for op in ("&", "|", "^", "<<", ">>")) and "//" not in line:
        add("Bitwise-Operation")
    if re.search(r"(<==|=).+===|(<==|=).+<==|(===).+===", line):
        add("Nested-Constraint-Conflict")
    if "signal" in line and "===" in line:
        add("Decl-Constraint-Conflict")
    if re.search(r"\w+\.\w+\(", line):
        add("Namespace-Method-Hallucination")
    if re.search(r"\w+\s*\([^)]*\)\s*[\.\[]", line):
        add("Anonymous-Component-Access")
    if any(word in line for word in ("if ", "then ", "else ", "for ", "loop ", "const ", "let")):
        add("Keyword-Hallucination")
    if re.search(r"\d+[nL]", line):
        add("Numeric-Suffix-Hallucination")
    if re.search(r"\d+\.\d+", line):
        add("Floating-Point-Hallucination")
    return labels


SEMANTIC = (
    ("Arithmetic-Mul", r"Mul|Mult|Multiplier|Multiply|BigMul|fpmul|Pow|Power|Square"),
    ("Arithmetic-DivMod", r"Div|Divide|Quotient|reciprocal|Mod|Modulo|Inverse|Rem|PrimeReduce"),
    ("Arithmetic-AddSub", r"Add|Adder|Sum|Sub|Neg|Abs|Total|Difference|mean|deviation|Clamp"),
    ("Logic-Comparison", r"Equal|Eq|Neq|Zero|Lt|Less|Gt|Greater|Max|Min|Compare|Range|Sign|And|Or|Xor|Not|Mux|Select|Cond|Swap|Bool"),
    ("Bit-Data-Ops", r"Bit|Num2|Bits2|Shift|Decompose|Array|Sort|Lookup|Table|Stack|Heap|Search|Counter|int|uint|Binary"),
)


def _t2021(line: str, block: str):
    if "Undeclared symbol" in block:
        return ["T2021 >> Undeclared-Symbol"]
    if "Calling symbol" not in block:
        return []
    found = re.search(r"(?:=\s*)?([A-Za-z_]\w*)\s*\(", line)
    entity = found.group(1) if found else ""
    category = "Others"
    for name, pattern in SEMANTIC:
        if re.search(pattern, entity, re.I):
            category = name
            break
    return [f"T2021 >> Calling-Symbol >> {category}"]


def _t3001(line: str, block: str):
    lower = block.lower()
    if "signal that is not initialized" in lower:
        compact = line.replace(" ", "")
        if "===" in compact and "<==" not in compact:
            return ["Flow: Constraint-Only (Missing Assignment)"]
        if "<==" in compact or re.search(r"(?<![=<>!])=(?!=)", compact):
            return ["Flow: Sequence Violation (Topological Order)"]
        return ["Flow: General Initialization Gap"]
    if "invalid assignment" in lower or "cannot be re-assigned" in lower:
        parts = line.split("<==", 1)
        if len(parts) == 2:
            left = re.search(r"([A-Za-z_]\w*)", parts[0])
            if left and re.search(rf"\b{re.escape(left.group(1))}\b", parts[1]):
                return ["Assign: Imperative Self-Update (a = a+1)"]
        return ["Assign: Multiple Definition/Re-assign"]
    if "non quadratic" not in lower:
        return []
    rhs = re.split(r"<==|===|(?<![<>=!])=(?!=)", line, maxsplit=1)[-1]
    if any(op in rhs for op in ("%", "\\", "!", "?", ":")):
        return ["Alg: Forbidden Operator (Non-Polynomial)"]
    if "/" in rhs:
        return ["Alg: Forbidden Division"]
    if re.search(r"&|\||\^|<<|>>", rhs):
        return ["Alg: Forbidden Bitwise Op"]
    if re.search(r">=|<=|>|<|==|!=", rhs):
        return ["Alg: Comparison Logic (Non-Algebraic)"]
    multiplications = len(re.findall(r"[A-Za-z_][\w.\[\]]*\s*\*\s*[A-Za-z_(]", rhs))
    if multiplications >= 2 and "+" in rhs:
        return ["Alg: Parallel Sum - Need Intermediate Signal"]
    if rhs.count("*") >= 2:
        return ["Alg: High-Order Polynomial (Degree 3+)"]
    if "*" in rhs and ("+" in rhs or "-" in rhs):
        return ["Alg: Mixed Quadratic-Linear (a*b + c)"]
    return ["Alg: Constant/Linear"]


def classify(text: str):
    text = _plain(text)
    blocks = list(_diagnostic_blocks(text))
    primary = []
    for code, _line, _block in blocks:
        if code not in primary:
            primary.append(code)
    labels = []
    grouped = defaultdict(set)
    for code, line, _block in blocks:
        if code in ("P1008", "P1012") and line:
            grouped[line].add(code)
    for line, codes in grouped.items():
        if codes == {"P1008", "P1012"}:
            labels.extend(_combined(line, "P1008+P1012"))
        elif codes == {"P1008"}:
            labels.extend(_p1008(line))
        else:
            labels.extend(_p1012(line))
    for code, line, block in blocks:
        if code == "T2021":
            labels.extend(_t2021(line, block))
        elif code == "T3001":
            labels.extend(_t3001(line, block))
        elif code not in ("P1008", "P1012"):
            labels.append(code)
    return list(dict.fromkeys(labels)), primary


def _catalog():
    entries = []
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        entries.append({key: item.get(key, "") for key in (
            "error_classify", "primary_code", "general_description",
            "specific_description", "target_code",
        )})
    return entries


def match(text: str):
    labels, primary = classify(text)
    entries = _catalog()
    selected = next((item for label in labels for item in entries if item["error_classify"] == label), None)
    match_type = "error_classify" if selected else None
    if selected is None:
        selected = next((item for code in primary for item in entries if item["primary_code"] == code), None)
        match_type = "primary_code" if selected else None
    return {"matched": selected is not None, "match_type": match_type, "labels": labels,
            "primary_codes": primary, "knowledge": selected}


def render(result):
    if not result["matched"]:
        return ""
    item = result["knowledge"]
    example = item.get("target_code", "")
    if len(example) > 12000:
        example = example[:12000] + "\n[example truncated]"
    return "\n".join((
        "[matched_refine_knowledge]",
        "The compiler failure matched TransZKEval's existing refined error knowledge.",
        f"Match type: {result['match_type']}",
        f"Matched class: {item.get('error_classify') or 'N/A'}",
        f"Primary compiler code: {item.get('primary_code') or 'N/A'}",
        f"General guidance: {item.get('general_description') or 'N/A'}",
        f"Specific guidance: {item.get('specific_description') or 'N/A'}",
        "Example faulty code from the knowledge base (diagnose it; do not copy it):",
        example or "N/A",
        "[/matched_refine_knowledge]",
    ))


def augment(command: str, exit_code, stdout: str, stderr: str):
    combined = _plain((stdout or "") + "\n" + (stderr or ""))
    if not COMPILER_RE.search(command or "") or not DIAGNOSTIC_RE.search(combined):
        return {"injected": False, "text": "", "match": None, "matcher_error": None}
    try:
        result = match(combined)
    except Exception as error:
        return {"injected": False, "text": "", "match": None,
                "matcher_error": f"{type(error).__name__}: {error}"}
    block = render(result)
    return {"injected": bool(block), "text": block, "match": result, "matcher_error": None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("diagnostic", nargs="?")
    args = parser.parse_args()
    if args.json:
        payload = json.load(sys.stdin)
        result = augment(payload.get("command", ""), payload.get("exit"), payload.get("stdout", ""), payload.get("stderr", ""))
    else:
        result = match(args.diagnostic if args.diagnostic is not None else sys.stdin.read())
        result["text"] = render(result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
