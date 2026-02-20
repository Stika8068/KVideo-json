import json
import requests
import time
import os
import re
from urllib.parse import urlparse

# GitHub API 配置（必须设置环境变量 GH_TOKEN）
GH_TOKEN = os.environ.get('GH_TOKEN')
if not GH_TOKEN:
    print("请设置环境变量 GH_TOKEN，否则 API 限速很严重")
    exit(1)

HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

# 搜索关键词：不限端口，覆盖常见协议和订阅文件
SEARCH_QUERY = '("trojan" OR "vless" OR "vmess" OR "clash" OR "xray" OR "v2ray" OR "hysteria") (":\\d{2,5}" OR "port" OR "订阅") extension:txt OR extension:yaml OR extension:md OR extension:conf OR extension:base64'

API_URL = 'https://api.github.com/search/code'
PER_PAGE = 100

# 测试节点（支持任意端口，统一优先尝试 HTTPS）
def test_node(ip_port, sni=None):
    ip, port = ip_port.split(':')
    url = f"https://{ip}:{port}"
    
    headers = {}
    if sni:
        headers['Host'] = sni
    
    # 优先尝试 HTTPS（大多数节点都是 TLS）
    try:
        resp = requests.get(url, headers=headers, timeout=6, verify=False)
        status = f"HTTPS OK ({resp.status_code})"
        return True, status
    except requests.exceptions.RequestException as e:
        err_msg = str(e)[:80]
        # HTTPS 失败 → 再尝试 HTTP（覆盖极少数明文节点）
        try:
            http_url = f"http://{ip}:{port}"
            resp_http = requests.get(http_url, headers=headers, timeout=6)
            status_http = f"HTTP OK ({resp_http.status_code})"
            return True, status_http
        except requests.exceptions.RequestException as eh:
            combined_err = f"HTTPS 失败: {err_msg} | HTTP 也失败: {str(eh)[:60]}"
            return False, combined_err

# 从内容提取所有 IP:端口（不限端口）
def extract_nodes_from_content(content):
    nodes = set()
    # IPv4:端口 或 [IPv6]:端口
    pattern = r'((?:\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})|\[(?:[0-9a-fA-F:]+)\]):([1-9]\d{0,4}|[1-5]\d{5}|6[0-4]\d{3}|65[0-4]\d{2}|655[0-2]\d{1}|6553[0-5])'
    matches = re.findall(pattern, content)
    for ip, port in matches:
        # 过滤无效端口（可选：排除 <1024 的系统端口，如果需要可以注释掉）
        if int(port) >= 1024:
            nodes.add(f"{ip}:{port}")
    
    # 额外提取订阅链接（完整 URL）
    sub_pattern = r'(https?://[^\s"\']+\.(txt|yaml|yml|md|conf|sub|base64|json))'
    subs = re.findall(sub_pattern, content)
    for sub in subs:
        nodes.add(sub[0])
    
    return nodes

# 主逻辑：搜索 + 提取 + 测试 + 保存
all_nodes = set()
page = 1
while True:
    params = {'q': SEARCH_QUERY, 'per_page': PER_PAGE, 'page': page}
    resp = requests.get(API_URL, headers=HEADERS, params=params)
    if resp.status_code != 200:
        print(f"GitHub API 错误: {resp.status_code} - {resp.text[:200]}")
        break
    data = resp.json()
    items = data.get('items', [])
    if not items:
        break

    for item in items:
        raw_url = item['html_url'].replace('/blob/', '/raw/')
        try:
            file_resp = requests.get(raw_url, timeout=10)
            if file_resp.status_code == 200:
                content = file_resp.text
                extracted = extract_nodes_from_content(content)
                all_nodes.update(extracted)
                print(f"从 {raw_url} 提取到 {len(extracted)} 个节点/订阅")
        except Exception as e:
            print(f"处理 {raw_url} 出错: {e}")
        time.sleep(1.2)  # 防限速

    page += 1
    time.sleep(4)

# 加载已有数据（nodes.json）
try:
    with open('nodes.json', 'r', encoding='utf-8') as f:
        existing = json.load(f)
    existing_set = {item['node'] for item in existing if 'node' in item}
except:
    existing = []
    existing_set = set()

# 测试新节点
available = []
for node in all_nodes - existing_set:
    alive, info = test_node(node)  # 可扩展：从内容提取 SNI 再传
    status = "可用" if alive else f"不可用 ({info})"
    available.append({
        "node": node,
        "status": status,
        "tested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "GitHub 搜索"
    })
    print(f"测试 {node}: {status}")
    time.sleep(1.2)

# 合并保存（可加 priority、enabled 等字段）
output = existing.copy()
base_priority = max([item.get('priority', 0) for item in existing] + [0]) + 1
for idx, item in enumerate(available):
    output.append({
        "id": item['node'].replace('.', '_').replace(':', '__').replace('[', '').replace(']', ''),
        "node": item['node'],
        "status": item['status'],
        "priority": base_priority + idx,
        "enabled": "可用" in item['status']
    })

with open('nodes.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=4)

print(f"更新完成！新增 {len(available)} 个节点（其中可用约 {sum(1 for n in available if '可用' in n['status'])} 个）。")
