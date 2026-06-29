import json
import os
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# --- 配置 ---
DB_CODE_PATH = "./db_code"
DB_DOC_PATH = "./db_doc"
INPUT_FILE = "dataset.jsonl"
OUTPUT_FILE = "dataset_enriched.jsonl"
MAX_CHARS = 1500  # 每个参考片段的硬上限

# --- 初始化 ---
print("⏳ 正在加载 3+2 检索配置...")
embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")
db_code = Chroma(persist_directory=DB_CODE_PATH, embedding_function=embeddings)
db_doc = Chroma(persist_directory=DB_DOC_PATH, embedding_function=embeddings)


def smart_crop(text, limit=1500):
    """
    针对 3+2 模式的截断：
    保留头部 1000 (定义) 和尾部 500 (约束)
    """
    if not text or len(text) <= limit:
        return text

    head_size = 1000
    tail_size = 500

    return (
            text[:head_size] +
            "\n\n// [... 中间逻辑已截断 ...] \n\n" +
            text[-tail_size:]
    )


def get_3plus2_context(func_name):
    query = func_name.replace("_", " ")

    # 执行 3+2 检索
    code_results = db_code.similarity_search(query, k=3)
    doc_results = db_doc.similarity_search(query, k=2)

    # 处理 3 个代码块
    final_codes = []
    for res in code_results:
        final_codes.append({
            "title": res.metadata.get('title', 'n/a'),
            "text": smart_crop(res.page_content, limit=MAX_CHARS)
        })

    # 处理 2 个文档块
    final_docs = []
    for res in doc_results:
        final_docs.append(smart_crop(res.page_content, limit=MAX_CHARS))

    return final_codes, final_docs


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ 找不到输入文件: {INPUT_FILE}")
        return

    with open(INPUT_FILE, 'r', encoding='utf-8') as f_in, \
            open(OUTPUT_FILE, 'w', encoding='utf-8') as f_out:

        for line in f_in:
            item = json.loads(line)
            print(f"🔍 3+2 检索 ID {item['id']}: {item['func_name']}...")

            codes, docs = get_3plus2_context(item['func_name'])

            # 注入增强后的列表
            item['retrieved_code'] = codes
            item['retrieved_doc'] = docs

            f_out.write(json.dumps(item, ensure_ascii=False) + '\n')

    print(f"✅ 3+2 预检索完成！已生成: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()