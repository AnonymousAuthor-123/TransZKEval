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

# C++答案模板
CPP_ANSWER = """#include <iostream>

int simpleMax(int a, int b) {
    if (a >= b) {
        return a;
    } else {
        return b;
    }
}

int main() {
    // Example usage
    std::cout << simpleMax(5, 10) << std::endl;
    return 0;
}"""

# ==========================================
# 3. 策略函数实现
# ==========================================

def get_basic_one_shot(lang):
    """获取Basic策略的one-shot示例"""
    example_code = LANGUAGE_EXAMPLES.get(lang, LANGUAGE_EXAMPLES["Python"])
    return f"""Example: \n Translate the following {lang} function into a C++ function named simpleMax:
{example_code}

{CPP_ANSWER}"""

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
    """提取 C++ 代码块"""
    if "```cpp" in text:
        return text.split("```cpp")[1].split("```")[0].strip()
    elif "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text.strip()


def translate_basic(src, lang, name):
    """Basic策略：直接翻译"""
    one_shot = get_basic_one_shot(lang)
    prompt = f"{one_shot}\n\nTask: \nTranslate the following {lang} function into a C++ function named {name}:\n{src}"
    return clean_code(get_completion("You are a code translator. Output only C++ code.", prompt))


# ==========================================
# 4. 自动化批处理实验引擎
# ==========================================

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

    # 只使用basic策略
    strategy_name = "basic"
    strategy_func = translate_basic
    output_path = f"xx_results_cpp.jsonl"

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
        for task in all_tasks:
            task_id = task.get("id")
            func_name = task.get("func_name")
            
            print(f"\n>>> [START] Task {task_id}: {func_name} <<<")
            
            for l_key, l_full in lang_map.items():
                # 如果该语言任务已完成或原数据中没有该语言代码，跳过
                if (task_id, l_full) in finished or not task.get(l_key):
                    continue
                
                print(f"  - [{strategy_name}] Processing ({l_full})...")
                
                try:
                    source_code = task.get(l_key)
                    
                    # 执行翻译
                    cpp_code = strategy_func(source_code, l_full, func_name)
                    
                    # 构造结果
                    result = {
                        "id": task_id,
                        "func_name": func_name,
                        "source_lang": l_full,
                        "translated_cpp": cpp_code,
                        "strategy": strategy_name,
                        "timestamp": time.strftime("%H:%M:%S")
                    }
                    
                    f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
                    f_out.flush()
                    
                except Exception as e:
                    print(f"  [ERROR] ({l_full}) failed: {e}")
                    continue


if __name__ == "__main__":
    run_experiment()
    print("\n[FINISH] C++ translation completed.")
