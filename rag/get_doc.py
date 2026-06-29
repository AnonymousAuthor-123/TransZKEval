import os
import re
import json


def process_docs(root_dir, output_file):
    doc_entries = []

    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith(('.md', '.txt')):
                file_path = os.path.join(root, file)
                print(f"📖 正在处理文档: {file_path}")

                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                    # 核心逻辑：按 Markdown 的二级或三级标题切分
                    # 这样能保证一个“知识点”是完整的
                    chunks = re.split(r'\n(?=#{2,3} )', content)

                    for i, chunk in enumerate(chunks):
                        clean_chunk = chunk.strip()
                        if len(clean_chunk) > 100:  # 过滤掉太短的标题或无意义片段
                            doc_entries.append({
                                "type": "doc",  # 标记为文档
                                "source_path": file_path,
                                "title": f"{file}_section_{i}",
                                "text": f"Context from {file}:\n{clean_chunk}",
                                "metadata": {
                                    "file_name": file,
                                    "entity_type": "instruction"
                                }
                            })

    with open(output_file, 'w', encoding='utf-8') as f:
        for entry in doc_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"✅ 文档处理完成！共生成 {len(doc_entries)} 条规则块。")


# 执行
process_docs('circom-master', 'circom_docs.jsonl')