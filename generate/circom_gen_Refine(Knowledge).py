import json
import time
import os
import re
from openai import OpenAI
from collections import defaultdict

# 1. 配置 API
client = OpenAI(
    api_key="xx",
    base_url="xx"
)

# 2. 核心配置与跳过名单
BASE_DIR = r"D:\py\TransZKEval"
DATASET_PATH = os.path.join(BASE_DIR, "dataset.jsonl")
EVAL_DIR = os.path.join(BASE_DIR, "eval_results_with_error_classify")
DESCRIPTIONS_PATH = os.path.join(BASE_DIR, "extracted_samples_with_descriptions.jsonl")
PENDING_DIR = os.path.join(BASE_DIR, "pending_eval")

# 你指定的 Used IDs：不修复，不保持原状，直接跳过
SKIP_IDS = {10, 42, 44, 48, 50, 57, 68, 69, 71, 78, 85, 86, 92, 94, 98}


# 3. 工具函数
def extract_primary_code(error_msg):
    """从错误信息中提取错误代号 (如 T2005)"""
    if not error_msg or not isinstance(error_msg, str):
        return "GENERAL_ERROR"
    match = re.search(r"error\[([A-Z0-9]+)\]", error_msg)
    if match:
        return match.group(1)
    return "GENERAL_ERROR"


def load_jsonl_to_dict(path, key_fields):
    """加载 jsonl 并生成索引"""
    data_dict = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                item = json.loads(line)
                key = tuple(item.get(field) for field in key_fields)
                data_dict[key] = item
    return data_dict


def load_descriptions_map(path):
    """加载描述库，支持 classify 和 primary_code 双重匹配"""
    desc_map = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                item = json.loads(line)
                c_key = item.get('error_classify')
                p_key = item.get('primary_code')
                if c_key: desc_map[str(c_key).strip()] = item
                if p_key: desc_map[str(p_key).strip()] = item
    return desc_map


# 4. Prompt 生成函数
def get_refinement_prompt(lang, source, faulty, error, ex_data):
    """构造 Prompt，注入示例及其 target_code (故障示例)"""
    ex_classify = ex_data.get("error_classify", "N/A")
    ex_primary = ex_data.get("primary_code", "N/A")
    ex_general = ex_data.get("general_description", "No description.")
    ex_specific = ex_data.get("specific_description", "No specific description.")
    ex_faulty_sample = ex_data.get("target_code", "// No sample provided")

    return f"""You are a Circom expert. Your task is to fix Circom compilation errors.

## [Learning from Similar Error Case]
Use this pattern to understand the nature of the error:
- [Error Classification]: {ex_classify}
- [Primary Code]: {ex_primary}
- [General Description]: {ex_general}
- [Specific Description]: {ex_specific}
- [Example Faulty Code for Reference]:
{ex_faulty_sample}

---

## [Current Task to Fix]
Fix the compilation error in the following translated Circom code.

[Source {lang} Code]:
{source}

[Current Faulty Circom Code]:
{faulty}

[Compiler Error Message]:
{error}

[Fixed Circom Code]:
(Output ONLY the functional code, no markdown tags, no explanations)"""


# 5. 主修复流程
def process_iterative_fix(model_name="gemini", strategy="basic"):
    eval_file = os.path.join(EVAL_DIR, f"{model_name}-{strategy}_results_eval.jsonl")
    prev_file = os.path.join(PENDING_DIR, f"{model_name}-{strategy}_results.jsonl")
    output_file = os.path.join(PENDING_DIR, f"{model_name}-{strategy}_results_fixdes.jsonl")

    if not os.path.exists(eval_file):
        print(f"Error: Missing eval file {eval_file}")
        return

    print(f"--- Starting Iterative Fix: {model_name}-{strategy} ---")
    lang_map = {"Python": "py", "Go": "go", "Rust": "rs", "Java": "jv"}
    dataset = load_jsonl_to_dict(DATASET_PATH, ["id"])
    eval_results = load_jsonl_to_dict(eval_file, ["id", "lang"])
    prev_results = load_jsonl_to_dict(prev_file, ["id", "source_lang"])
    desc_map = load_descriptions_map(DESCRIPTIONS_PATH)

    # 断点续传
    finished = load_jsonl_to_dict(output_file, ["id", "source_lang"])

    fixed_count = 0
    skipped_count = 0
    ignored_count = 0

    with open(output_file, 'a', encoding='utf-8') as f_out:
        for (tid, lang), eval_item in eval_results.items():
            if (tid, lang) in finished: continue

            # --- ID 过滤逻辑 ---
            if tid in SKIP_IDS:
                print(f"[-] Task {tid}: In SKIP_IDS, bypassing entirely.")
                ignored_count += 1
                continue

            status = eval_item.get("status")
            error_msg = eval_item.get("error_msg", "")
            error_classify_list = eval_item.get("error_classify", [])

            if status == "COMPILE_FAIL":
                print(f"[*] Task {tid} [{lang}]: Fixing compile error...")

                # 匹配示例
                p_code = extract_primary_code(error_msg)
                example_data = None
                for cls in error_classify_list:
                    if str(cls).strip() in desc_map:
                        example_data = desc_map[str(cls).strip()]
                        break
                if not example_data:
                    example_data = desc_map.get(p_code, {})

                # 准备数据
                source_entry = dataset.get((tid,))
                source_code = source_entry.get(lang_map.get(lang, ""), "") if source_entry else ""
                old_record = prev_results.get((tid, lang), {})
                faulty_circom = old_record.get("translated_circom", "")

                # 请求 API
                prompt = get_refinement_prompt(lang, source_code, faulty_circom, error_msg, example_data)
                try:
                    response = client.chat.completions.create(
                        model="xx",
                        messages=[
                            {"role": "system", "content": "You are a Circom expert. Return only code."},
                            {"role": "user", "content": prompt}
                        ],
                        timeout=120
                    )
                    fixed_code = response.choices[0].message.content.strip()
                    fixed_code = re.sub(r"```(circom)?\n", "", fixed_code).replace("```", "").strip()
                    fixed_count += 1
                except Exception as e:
                    print(f"    API Error: {e}")
                    fixed_code = faulty_circom

                result = {
                    "id": tid,
                    "func_name": eval_item.get("func"),
                    "source_lang": lang,
                    "translated_circom": fixed_code,
                    "prev_status": status,
                    "error_msg": error_msg,
                    "fixed": True,
                    "match_type": example_data.get("primary_code", "none")
                }
            else:
                # SUCCESS 或 LOGIC_FAIL：不修复，保持原记录
                old_record = prev_results.get((tid, lang))
                result = old_record.copy() if old_record else eval_item.copy()
                result["fixed"] = False
                skipped_count += 1

            # 写入文件
            f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
            f_out.flush()

    print(f"\n[DONE]")
    print(f"Fixed (COMPILE_FAIL): {fixed_count}")
    print(f"Retained (SUCCESS/LOGIC): {skipped_count}")
    print(f"Ignored (SKIP_IDS): {ignored_count}")


if __name__ == "__main__":
    import sys

    m = sys.argv[1] if len(sys.argv) > 1 else "gemini"
    s = sys.argv[2] if len(sys.argv) > 2 else "basic"
    process_iterative_fix(m, s)