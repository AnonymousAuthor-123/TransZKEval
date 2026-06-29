import json
import os
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from tqdm import tqdm


def ingest_doc_only():
    # --- 配置路径 ---
    db_path = "./db_doc"
    jsonl_file = "circom_docs.jsonl"  # 刚才生成的 128 条文档块

    # 确保文件存在
    if not os.path.exists(jsonl_file):
        print(f"❌ 错误: 找不到 {jsonl_file}，请先运行 getdoc.py")
        return

    # 1. 加载本地 Embedding 模型 (保持模型一致，确保后续检索维度相同)
    print("⏳ 正在加载本地 Embedding 模型...")
    embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-small-en-v1.5",
        model_kwargs={'device': 'cpu'}
    )

    # 2. 解析文档 JSONL
    docs = []
    print(f"📖 正在读取 {jsonl_file}...")
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line)
            # 文档通常包含元数据，有助于检索后的溯源
            docs.append(Document(
                page_content=data['text'],
                metadata=data.get('metadata', {"type": "doc"})
            ))

    # 3. 创建向量库并持久化
    print(f"📦 正在构建文档向量库 (共 {len(docs)} 条)...")

    # 如果已存在旧库，先删除（可选，视你需求而定）
    # if os.path.exists(db_path):
    #     import shutil
    #     shutil.rmtree(db_path)

    vectorstore = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=db_path
    )

    print(f"✅ 文档库构建完成！目录: {os.path.abspath(db_path)}")


if __name__ == "__main__":
    ingest_doc_only()