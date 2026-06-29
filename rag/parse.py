import os
import re
import json


def extract_templates(file_content):
    """
    提取 Circom 文件中的所有 template 块。
    使用更健壮的正则来捕获 template 定义。
    """
    # 匹配 template Name(...) { ... }
    pattern = r'template\s+([a-zA-Z0-9_]+)\s*\((.*?)\)\s*\{([\s\S]*?)\n\}'
    matches = re.finditer(pattern, file_content)

    templates = []
    for match in matches:
        t_name = match.group(1)
        t_params = match.group(2)
        t_body = match.group(3)
        full_code = f"template {t_name}({t_params}) {{{t_body}\n}}"
        templates.append({
            "name": t_name,
            "content": full_code
        })
    return templates


def process_directory(root_dir, output_file):
    dataset = []
    processed_dirs = 0
    file_count = 0

    print(f"🚀 开始扫描根目录: {root_dir}")
    print("-" * 50)

    # os.walk 递归处理所有子文件夹
    for root, dirs, files in os.walk(root_dir):
        # 每进入一个新文件夹就打印一次
        if files:  # 只有包含文件的文件夹才打印，避免刷屏
            print(f"📁 正在处理目录: {root} (包含 {len(files)} 个文件)")
            processed_dirs += 1

        for file in files:
            file_path = os.path.join(root, file)

            # 处理 Circom 代码
            if file.endswith('.circom'):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        templates = extract_templates(content)
                        for t in templates:
                            dataset.append({
                                "type": "code",
                                "source_path": file_path,
                                "title": t["name"],
                                "text": t["content"],
                                "metadata": {
                                    "file_name": file,
                                    "entity_type": "template",
                                    "folder": os.path.basename(root)
                                }
                            })
                        file_count += 1
                except Exception as e:
                    print(f"❌ 读取代码文件出错 {file}: {e}")

            # 处理教学文档
            elif file.endswith(('.md', '.txt')):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        chunks = re.split(r'\n(?=## )|\n\n', content)
                        for i, chunk in enumerate(chunks):
                            clean_chunk = chunk.strip()
                            if len(clean_chunk) > 50:
                                dataset.append({
                                    "type": "doc",
                                    "source_path": file_path,
                                    "title": f"{file}_chunk_{i}",
                                    "text": clean_chunk,
                                    "metadata": {
                                        "file_name": file,
                                        "entity_type": "instruction",
                                        "folder": os.path.basename(root)
                                    }
                                })
                        file_count += 1
                except Exception as e:
                    print(f"❌ 读取文档文件出错 {file}: {e}")

    # 写入 JSONL
    print("-" * 50)
    print(f"💾 正在将数据写入 {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        for entry in dataset:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"✅ 处理完成！")
    print(f"📊 统计：遍历了 {processed_dirs} 个目录，处理了 {file_count} 个文件，提取了 {len(dataset)} 条知识块。")


# 执行
process_directory('circom_data_full', 'circom_rag_data.jsonl')