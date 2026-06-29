import json
import time
import os
from openai import OpenAI

# 1. 配置 API
client = OpenAI(
    api_key="xx",
    base_url="xx"
)

# One-shot修复示例：展示错误代码和修复后的正确代码
ITERATIVE_FIX_ONESHOT = '''Fix the following Circom compilation error.

Example:

[Faulty Circom Code]:
pragma circom 2.1.0;
include "node_modules/circomlib/circuits/comparators.circom";

template SimpleMax() {
    signal input a;
    signal input b;
    signal output out;
    
    component gte = GreaterEqThan(64);
    gte.in[0] <== a;
    gte.in[1] <== b;

    if (gte.out == 1) {
        out <== a;
    } else {
        out <== b;
    }
}

component main = SimpleMax();

[Compiler Error]:
error[T2005]: Typing error found
    "circuit.circom":12:8
   
12     if (gte.out == 1) {
           ^^^^^^^^^^^^ There are constraints depending on the value of the condition and it can be unknown during the constraint generation phase

previous errors were found

[Fixed Circom Code]:
pragma circom 2.1.0;
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

component main = SimpleMax();'''


def get_one_shot_refinement_prompt(lang, func, source, faulty, error):
    """生成one-shot迭代修复prompt"""
    return f"{ITERATIVE_FIX_ONESHOT}\n\nTask:\n[Faulty Circom Code]:\n{faulty}\n\n[Compiler Error]:\n{error}\n\n [Fixed Circom Code]:"


def load_jsonl_to_dict(path, key_fields):
    """通用加载函数，将jsonl转为字典，方便快速查找"""
    data_dict = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                item = json.loads(line)
                # 生成复合主键，例如 (1, "Python")
                key = tuple(item.get(field) for field in key_fields)
                data_dict[key] = item
    return data_dict


def process_one_shot_refinement(model_name="xx", strategy="basic"):
    """
    One-shot迭代修复主函数
    只修复COMPILE_FAIL状态的任务，跳过LOGIC_FAIL和SUCCESS
    """
    # 文件路径
    DATASET_PATH = "dataset.jsonl"
    EVAL_PATH = f"eval_results/{model_name}-{strategy}_results_eval.jsonl"
    PREV_RESULTS_PATH = f"{model_name}_results_{strategy}_oneshot.jsonl" if os.path.exists(f"{model_name}_results_{strategy}_oneshot.jsonl") else f"{model_name}_results_{strategy}.jsonl"
    OUTPUT_PATH = f"{model_name}_results_{strategy}_oneshot_fixed.jsonl"

    # 检查文件是否存在
    if not os.path.exists(EVAL_PATH):
        print(f"Error: Evaluation file not found: {EVAL_PATH}")
        return
    
    if not os.path.exists(PREV_RESULTS_PATH):
        print(f"Error: Previous results file not found: {PREV_RESULTS_PATH}")
        return

    # 映射 dataset 中的 key
    lang_to_key = {"Python": "py", "Go": "go", "Rust": "rs", "Java": "jv"}

    # 1. 加载所有数据到内存
    print("正在加载数据...")
    dataset = load_jsonl_to_dict(DATASET_PATH, ["id"])
    eval_results = load_jsonl_to_dict(EVAL_PATH, ["id", "lang"])
    prev_results = load_jsonl_to_dict(PREV_RESULTS_PATH, ["id", "source_lang"])

    # 加载已完成的修复任务（支持断点）
    finished_refines = load_jsonl_to_dict(OUTPUT_PATH, ["id", "source_lang"])

    # 统计需要修复的任务
    compile_fail_count = 0
    for (tid, lang), eval_item in eval_results.items():
        if eval_item.get("status") == "COMPILE_FAIL":
            compile_fail_count += 1
    
    print(f"总任务数: {len(eval_results)}")
    print(f"编译错误需要修复: {compile_fail_count}")
    print(f"已修复任务数: {len(finished_refines)}")
    print("=" * 60)

    fixed_count = 0
    skipped_count = 0

    with open(OUTPUT_PATH, 'a', encoding='utf-8') as f_out:
        for (tid, lang), eval_item in eval_results.items():
            # 跳过已修复的任务
            if (tid, lang) in finished_refines:
                continue

            status = eval_item.get("status")
            error_msg = eval_item.get("error_msg", "")
            func_name = eval_item.get("func")

            # 获取旧代码和原始代码
            old_record = prev_results.get((tid, lang), {})
            faulty_circom = old_record.get("translated_circom", "")

            # 从 dataset 获取原始代码
            source_entry = dataset.get((tid,))
            source_code = source_entry.get(lang_to_key.get(lang, ""), "") if source_entry else ""

            # 只修复COMPILE_FAIL状态的任务
            if status == "COMPILE_FAIL" and faulty_circom:
                print(f"[{model_name}-{strategy}] 修复 Task {tid} [{lang}] (错误: {status})...")

                # 调用 AI 进行修复
                prompt = get_one_shot_refinement_prompt(lang, func_name, source_code, faulty_circom, error_msg)
                try:
                    response = client.chat.completions.create(
                        model="xx",
                        messages=[
                            {"role": "system",
                             "content": "You are a Circom expert. Fix the code and output ONLY the corrected code without any explanation or markdown tags."},
                            {"role": "user", "content": prompt}
                        ],
                        timeout=60
                    )
                    fixed_code = response.choices[0].message.content.strip()
                    # 清洗 markdown 格式
                    fixed_code = fixed_code.replace("```circom", "").replace("```", "").strip()
                    fixed_count += 1
                except Exception as e:
                    print(f"Task {tid} 修复失败: {e}")
                    fixed_code = 'Error API Call'

                # 构造结果
                result = {
                    "id": tid,
                    "func_name": func_name,
                    "source_lang": lang,
                    "translated_circom": fixed_code,
                    "prev_status": status,
                    "error_msg": error_msg,
                    "fixed": True,
                    "timestamp": time.strftime("%H:%M:%S")
                }
            else:
                # 如果不是COMPILE_FAIL，直接复制原记录
                if status == "SUCCESS":
                    print(f"Task {tid} [{lang}] 已成功，跳过。")
                elif status == "LOGIC_FAIL":
                    print(f"Task {tid} [{lang}] 逻辑错误，跳过（不修复逻辑错误）。")
                else:
                    print(f"Task {tid} [{lang}] 状态: {status}，跳过。")
                
                result = old_record.copy() if old_record else {
                    "id": tid,
                    "func_name": func_name,
                    "source_lang": lang,
                    "translated_circom": faulty_circom,
                    "prev_status": status,
                    "error_msg": error_msg,
                    "fixed": False
                }
                skipped_count += 1

            # 写入文件
            f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
            f_out.flush()

    print("=" * 60)
    print(f"修复完成！")
    print(f"修复了 {fixed_count} 个编译错误")
    print(f"跳过了 {skipped_count} 个任务（SUCCESS/LOGIC_FAIL/其他）")
    print(f"结果保存在: {OUTPUT_PATH}")


if __name__ == "__main__":
    import sys
    
    # 支持命令行参数
    if len(sys.argv) >= 3:
        model_name = sys.argv[1]
        strategy = sys.argv[2]
    else:
        model_name = "xx"
        strategy = "basic"
    
    print(f"Starting One-Shot Iterative Fix for {model_name}-{strategy}")
    process_one_shot_refinement(model_name, strategy)
    print("\n[FINISH] One-Shot Iterative Fix completed.")
