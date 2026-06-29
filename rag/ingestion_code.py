import json
import os
# 关键修改：最新的导入路径
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from tqdm import tqdm


def run_ingestion():
    db_path = "./circom_chroma_db"
    jsonl_file = "circom_rag_data_hash_clean.jsonl"

    if not os.path.exists(jsonl_file):
        print(f"❌ 找不到文件: {jsonl_file}")
        return

    # 1. 初始化本地 Embedding
    print("⏳ 正在加载本地 Embedding 模型 (BAAI/bge-small-en-v1.5)...")
    embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-small-en-v1.5",
        model_kwargs={'device': 'cpu'}
    )

    # 2. 读取 JSONL
    docs = []
    print(f"📖 正在读取数据...")
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line)
            # 这里的 Document 构造遵循最新标准
            docs.append(Document(
                page_content=data['text'],
                metadata={
                    "type": data['type'],
                    "title": data['title'],
                    "source": data['source_path']
                }
            ))

    # 3. 分批存入向量数据库
    print(f"📦 正在构建本地向量库 (共 {len(docs)} 条)...")

    # 采用分块初始化，避免 Chroma 一次性处理上万条导致内存峰值
    batch_size = 500

    # 先初始化第一批
    vectorstore = Chroma.from_documents(
        documents=docs[0:batch_size],
        embedding=embeddings,
        persist_directory=db_path
    )

    # 循环存入剩余批次
    for i in tqdm(range(batch_size, len(docs), batch_size)):
        batch = docs[i: i + batch_size]
        vectorstore.add_documents(batch)

    print(f"✅ 持久化完成！数据库已保存至: {os.path.abspath(db_path)}")


if __name__ == "__main__":
    run_ingestion()