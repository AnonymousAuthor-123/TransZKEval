import json
import os
import subprocess
import shutil
import re
import sys
import argparse
import time

def clean_ansi(text):
    # 匹配所有的 ANSI 逃逸序列
    ansi_escape = re.compile(r'''
        \x1B  # ESC
        (?:   # 7-bit C1 Fe 控制字符
            [@-Z\\-_]
        |     # 或者序列 [ 参数 中间字符 命令
            \[
            [0-?]* # 参数
            [ -/]* # 中间字符
            [@-~]   # 命令
        )
    ''', re.VERBOSE)
    text = ansi_escape.sub('', text)
    # 2. 清理制表符 (┌ ─ │ └ ┴ 等 Unicode 字符范围)
    # 这些字符通常在 \u2500 到 \u257F 之间
    box_chars = re.compile(r'[\u2500-\u257F]')
    text = box_chars.sub('', text)

    return box_chars.sub('', text)

def run_cmd(cmd, cwd):
    try:
        res = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=120)
        return res.returncode, res.stdout, res.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"

def find_file(path):
    if not path: return None
    if os.path.exists(path): return os.path.abspath(path)
    script_rel = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.path.basename(path))
    if os.path.exists(script_rel): return script_rel
    return None

def get_main_line(code_content, func_name):
    # 1. 提取代码中所有的 template 名称
    templates = re.findall(r'template\s+([a-zA-Z0-9_]+)\s*\(', code_content)
    
    # 2. 预处理：去掉下划线并转小写，用于模糊比对
    def normalize(s):
        return s.replace('_', '').lower()
    
    target = normalize(func_name)
    
    # 3. 寻找最匹配的 template
    matched_name = None
    for t in templates:
        if normalize(t) == target:
            matched_name = t
            break
    
    # 4. 保底逻辑：如果没匹配上，选最后一个 template (通常是主逻辑)；再不行就转驼峰
    if not matched_name:
        matched_name = templates[-1] if templates else ''.join(word.capitalize() for word in func_name.split('_'))
        
    return f'component main = {matched_name}();'

def extract_input_signals(full_code):
    all_signals = []
    
    # 1. 匹配所有 signal input 语句，直到遇到分号
    # 这里的 [^;]+ 表示匹配除分号以外的所有字符
    input_blocks = re.findall(r"signal\s+input\s+([^;]+);", full_code)
    
    for block in input_blocks:
        # 2. 处理可能存在的逗号分隔（如: a, b, c）
        parts = block.split(',')
        
        for p in parts:
            # 3. 清理：去掉数组符号 [..] 及其内容，并去除首尾空格
            # 例如将 " in[N][2] " 变为 "in"
            clean_name = re.sub(r"\[.*?\]", "", p).strip()
            
            if clean_name:
                all_signals.append(clean_name)
                
    return all_signals

def evaluate_task(task, expected_outputs, lib_path, ptau_path, eval_root):
 
    task_id = task.get('id', 0)
    lang = task.get('source_lang', 'unk')
    func_name = task.get('func_name', 'unk')
    code = task.get('translated_circom', '')
    inputs = task.get('inputs', [])
    
    work_dir = os.path.join(eval_root, f"{task_id}_{lang}_{func_name}")
    if os.path.exists(work_dir): shutil.rmtree(work_dir)
    os.makedirs(work_dir)

    report = {
        "id": task_id, "func": func_name, "lang": lang, 
        "status": "FAIL", "constraints": 0, "proving_time_ms": 0, "proof_size_bytes": 0,
        "test_cases": [],
        "error_msg": ""
    }

    # 1. 注入代码并编译
    # 1. 使用正则移除模型生成代码中可能存在的 pragma 和 include 声明
    # re.I 表示忽略大小写，确保匹配更稳健
    clean_code = re.sub(r'(?i)pragma\s+circom\s+[^;]+;', '', code)
    clean_code = re.sub(r'(?i)include\s+"[^"]+";', '', clean_code).strip()
    #clean_code = re.sub(r'(?i)component\s+main\s*[^;]*;', '', clean_code).strip()
    # 2. 统一注入标准头部，并合并清理后的代码
    # 强制指定版本并引入常用库，确保环境一致性

    
    full_code = (
        'pragma circom 2.1.4;\n'
        'include "comparators.circom";\n'
        'include "bitify.circom";\n\n'
        f'{clean_code}\n\n'
       # f"{get_main_line(clean_code, func_name)}"
    )

    # 3. 写入文件
    with open(os.path.join(work_dir, "circuit.circom"), "w") as f: 
        f.write(full_code)

    ret, _, err = run_cmd(f"circom circuit.circom --r1cs --wasm -l {lib_path}", work_dir)
    if ret != 0:
        report["status"] = "COMPILE_FAIL"
        report["error_msg"] = clean_ansi(err.strip())
        return report

    # 2. 获取约束数量 (R1CS Info)
    _, info_out, _ = run_cmd(f"npx snarkjs r1cs info circuit.r1cs", work_dir)
    match = re.search(r"# of Constraints:\s+(\d+)", info_out)
    if match: report["constraints"] = int(match.group(1))

    # 3. Trusted Setup (Groth16)
    setup_cmd = (
        f"snarkjs groth16 setup circuit.r1cs {ptau_path} c_0.zkey && "
        f"snarkjs zkey contribute c_0.zkey c_final.zkey --name='Eval' -e='rand' && "
        f"snarkjs zkey export verificationkey c_final.zkey v_key.json"
    )
    if run_cmd(setup_cmd, work_dir)[0] != 0:
        report["status"] = "SETUP_FAIL"
        report["error_msg"] = clean_ansi(err.strip())
        return report

    # 4. 运行测试用例并计时
    all_pass = True
    for idx, val_list in enumerate(inputs):
        case_info = {"input": val_list, "expected": expected_outputs[idx], "actual": None, "status": "FAIL"}
        
        # 信号名动态匹配
        # 1. 从 Circom 源码中提取所有 input 信号名
        found_signals = extract_input_signals(full_code)
        
        # 2. 按顺序将 val_list 的值填入找到的信号名中
        # 假设 val_list 是 [50, 0, 100]，found_signals 是 ['n', 'low', 'high']
        # 结果会是 {"n": 50, "low": 0, "high": 100}
        input_dict = {}
        for i, sig_name in enumerate(found_signals):
            if i < len(val_list):
                input_dict[sig_name] = str(val_list[i])
        
        with open(os.path.join(work_dir, "input.json"), "w") as f: json.dump(input_dict, f)
     

  

        # 生成 Witness
        if run_cmd(f"node circuit_js/generate_witness.js circuit_js/circuit.wasm input.json w.wtns", work_dir)[0] == 0:
            run_cmd(f"npx snarkjs wtns export json w.wtns w.json", work_dir)
            with open(os.path.join(work_dir, "w.json"), "r") as f:
                actual = int(json.load(f)[1])
                case_info["actual"] = actual
                if actual == expected_outputs[idx]:
                    case_info["status"] = "PASS"
                    
                    # 仅在第一个成功的 Case 记录 Proof 性能指标（避免重复计算）
                    if report["proving_time_ms"] == 0:
                        start_t = time.time()
                        run_cmd(f"snarkjs groth16 prove c_final.zkey w.wtns proof.json pub.json", work_dir)
                        end_t = time.time()
                        report["proving_time_ms"] = int((end_t - start_t) * 1000)
                        if os.path.exists(os.path.join(work_dir, "proof.json")):
                            report["proof_size_bytes"] = os.path.getsize(os.path.join(work_dir, "proof.json"))
                else:
                    all_pass = False
                    report["error_msg"] = f"Witness gen failed: {clean_ansi(err.strip())}"
        else:
            all_pass = False
            report["error_msg"] = f"Witness gen failed: {clean_ansi(err.strip())}"
        
        report["test_cases"].append(case_info)

    report["status"] = "SUCCESS" if all_pass else "LOGIC_FAIL"
    return report

def get_dynamic_truth_map(file_path):
    t_map = {}
    if not os.path.exists(file_path):
        return t_map
    with open(file_path, 'r') as f:
        for line in f:
            if not line.strip(): continue
            data = json.loads(line)
            # 建立映射：{ ID: { "输入列表字符串": 输出值 } }
            t_map[data['id']] = {str(d['input']): d['py'][0] for d in data['details']}
    return t_map

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", default="groundtruth_results.jsonl",help="Input JSONL file")
    args = parser.parse_args()

    input_file = find_file(args.input)
    if not input_file:
        print(f"File not found: {args.input}"); sys.exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    ptau = find_file(os.path.join(script_dir, "circuits/pot15_final.ptau"))
    lib = os.path.join(script_dir, "circuits/node_modules/circomlib/circuits")
    sandbox = os.path.join(script_dir, "eval_sandbox")

    # 预期真值表 (根据 ID 匹配)
    with open("evaluation_results.jsonl", "r") as f:
        truth_map = {j['id']: [d['py'][0] for d in j['details']] for j in [json.loads(l) for l in f]}

    print(f"开始详尽评测: {input_file}")
    with open(input_file, 'r') as f_in, open(f"{args.input.split('_')[0]}_eval_results.jsonl", "w") as f_out:
        for line in f_in:
            if not line.strip(): continue
            task = json.loads(line)
            print(f"Checking {task['func_name']} ({task['source_lang']})...", end="", flush=True)
            
            res = evaluate_task(task, truth_map.get(task['id'], [0,0]), lib, ptau, sandbox)
            f_out.write(json.dumps(res) + "\n")
            print(f" {res['status']} ({res['constraints']} constraints, {res['proving_time_ms']}ms)")

if __name__ == "__main__":
    main()