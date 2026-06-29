import json
import hashlib


def hash_deduplication(input_file, output_file):
    unique_hashes = set()
    final_data = []
    dup_count = 0

    print(f"开始进行绝对内容哈希去重...")

    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line)
            content = item['text'].strip()

            # 计算内容的 MD5 哈希
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()

            if content_hash not in unique_hashes:
                unique_hashes.add(content_hash)
                final_data.append(item)
            else:
                dup_count += 1

    with open(output_file, 'w', encoding='utf-8') as f:
        for entry in final_data:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"✅ 去重完成！")
    print(f"📊 原始总数: {len(final_data) + dup_count}")
    print(f"📉 剔除完全重复内容: {dup_count} 条")
    print(f"✨ 最终保留知识块: {len(final_data)} 条")


if __name__ == "__main__":
    hash_deduplication('circom_rag_data.jsonl', 'circom_rag_data_hash_clean.jsonl')