import requests
import os
import time

# --- 配置区 ---
GITHUB_TOKEN = 'xx'  # 必须填写
SEARCH_QUERY = 'language:circom fork:false'
MAX_REPOS = 100
DOWNLOAD_DIR = 'circom_data_full'
HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}


def get_top_repos():
    """获取 Star 排名最高的原创 Circom 仓库"""
    print(f"正在获取 {SEARCH_QUERY} 的前 100 个仓库...")
    url = f"https://api.github.com/search/repositories?q={SEARCH_QUERY}&sort=stars&order=desc&per_page=100"
    try:
        res = requests.get(url, headers=HEADERS)
        res.raise_for_status()
        return res.json().get('items', [])
    except Exception as e:
        print(f"获取仓库列表出错: {e}")
        return []


def get_all_circom_files_recursive(repo_full_name):
    """通过递归 Tree API 获取仓库内所有 .circom 文件路径"""
    # 1. 获取默认分支
    repo_api_url = f"https://api.github.com/repos/{repo_full_name}"
    try:
        repo_data = requests.get(repo_api_url, headers=HEADERS).json()
        default_branch = repo_data.get('default_branch', 'main')

        # 2. 递归获取完整文件树
        tree_url = f"https://api.github.com/repos/{repo_full_name}/git/trees/{default_branch}?recursive=1"
        tree_res = requests.get(tree_url, headers=HEADERS)

        if tree_res.status_code == 200:
            tree_data = tree_res.json().get('tree', [])
            # 过滤出所有 .circom 文件
            files = [
                {
                    'path': item['path'],
                    'download_url': f"https://raw.githubusercontent.com/{repo_full_name}/{default_branch}/{item['path']}"
                }
                for item in tree_data
                if item.get('path', '').endswith('.circom') and item.get('type') == 'blob'
            ]
            return files
        else:
            print(f"  [!] 无法读取树结构 (HTTP {tree_res.status_code})")
            return []
    except Exception as e:
        print(f"  [!] 递归获取路径失败: {e}")
        return []


def save_file(repo_name, path, url):
    """下载并保存文件"""
    local_path = os.path.join(DOWNLOAD_DIR, repo_name, path)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    try:
        # 使用流式下载处理大文件
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            with open(local_path, 'w', encoding='utf-8') as f:
                f.write(res.text)
            return True
    except:
        pass
    return False


def main():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    repos = get_top_repos()
    if not repos:
        return

    for i, repo in enumerate(repos):
        repo_name = repo['full_name']
        print(f"\n[{i + 1}/{MAX_REPOS}] 正在全量递归扫描: {repo_name}")

        circom_files = get_all_circom_files_recursive(repo_name)

        if not circom_files:
            print(f"  [!] 未找到任何 .circom 文件。")
            continue

        success_count = 0
        for file in circom_files:
            if save_file(repo_name, file['path'], file['download_url']):
                success_count += 1

        print(f"  [√] 完成！在此仓库抓取到 {success_count} 个文件。")

        # API 频率保护
        time.sleep(1)


if __name__ == "__main__":
    main()