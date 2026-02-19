import json
import requests
import time
import os
from urllib.parse import urlparse

# GitHub API 配置
GH_TOKEN = os.environ.get('GH_TOKEN')
HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}
SEARCH_QUERY = '"api.php/provide/vod"+in:file+extension:json'  # 搜索关键词，可调整如 +language:json
API_URL = 'https://api.github.com/search/code'
PER_PAGE = 100  # 每页结果数，最大 100

# 测试 API 可用性（发送 ?ac=list 请求，超时 5s）
def test_api(url):
    test_url = url.rstrip('/') + '/?ac=list'
    try:
        resp = requests.get(test_url, timeout=5)
        return resp.status_code == 200
    except:
        return False

# 从 JSON 内容中提取所有类似 /api.php/provide/vod 的 URL
def extract_apis_from_json(content):
    apis = set()
    if isinstance(content, dict):
        for value in content.values():
            if isinstance(value, str) and 'api.php/provide/vod' in value:
                apis.add(value)
            elif isinstance(value, (dict, list)):
                apis.update(extract_apis_from_json(value))
    elif isinstance(content, list):
        for item in content:
            apis.update(extract_apis_from_json(item))
    return apis

# 搜索 GitHub 并提取
all_apis = set()
page = 1
while True:
    params = {'q': SEARCH_QUERY, 'per_page': PER_PAGE, 'page': page}
    resp = requests.get(API_URL, headers=HEADERS, params=params)
    if resp.status_code != 200:
        print(f"API error: {resp.text}")
        break
    data = resp.json()
    items = data.get('items', [])
    if not items:
        break

    for item in items:
        raw_url = item['html_url'].replace('/blob/', '/raw/')  # 获取 raw URL
        try:
            file_resp = requests.get(raw_url, timeout=10)
            if file_resp.status_code == 200:
                json_data = json.loads(file_resp.text)
                extracted = extract_apis_from_json(json_data)
                all_apis.update(extracted)
        except Exception as e:
            print(f"Error processing {raw_url}: {e}")
        time.sleep(2)  # 避免速率限制

    page += 1
    time.sleep(5)  # 分页延迟

# 加载原有 test.json
try:
    with open('test.json', 'r', encoding='utf-8') as f:
        existing = json.load(f)
    existing_apis = {item['baseUrl'] for item in existing}
except:
    existing = []
    existing_apis = set()

# 合并新发现的，去重，测试可用
available_apis = []
for api in all_apis - existing_apis:  # 只添加新发现的
    if test_api(api):
        available_apis.append(api)
    time.sleep(1)  # 测试延迟

# 生成新 JSON（原有 + 新可用，按 priority 排序）
output = existing.copy()
priority = max([item['priority'] for item in existing] + [0]) + 1
for api in sorted(available_apis):
    parsed = urlparse(api)
    id_name = parsed.netloc.replace('.', '_')  # 简单生成 id 和 name，如 www_example_com
    output.append({
        "id": id_name,
        "name": id_name.replace('_', ' '),  # 美化 name
        "baseUrl": api,
        "group": "normal",  # 默认 normal，可根据需要分类
        "enabled": True,
        "priority": priority
    })
    priority += 1

# 保存到 test.json
with open('test.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=4)

print(f"Updated test.json with {len(available_apis)} new APIs.")