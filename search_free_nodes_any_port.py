import json
import requests
import time
import os
import re

# ==================== 配置区 ====================
GH_TOKEN = os.environ.get('GH_TOKEN')
if not GH_TOKEN:
    print("错误：请先设置环境变量 GH_TOKEN")
    print("示例：export GH_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    exit(1)

HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept': 'application/vnd.github.v3+json',
    'X-GitHub-Api-Version': '2022-11-28'  # 明确使用文档版本，避免默认旧版
}

# 最稳定的查询写法（先用这个跑通，成功后再逐步加条件）
SEARCH_QUERY = 'trojan extension:txt'          # 极简版，几乎不会报 422
# 推荐进阶版（如果上面成功，换成这个再跑）
# SEARCH_QUERY = 'trojan OR vless extension:txt'
# 再进阶（端口匹配版）
# SEARCH_QUERY = 'trojan :\\d{4,} extension:txt'

API_URL = 'https://api.github.com/search/code'
PER_PAGE = 50   # 调小一点，减少单次压力

# ==================== 测试函数 ====================
def test_node(ip_port):
    """简单测试端口是否能连通，优先 HTTPS"""
    if ':' not in ip_port:
        return False, "格式错误"
    
    ip, port = ip_port.split(':', 1)
    url_https = f"https://{ip}:{port}"
    
    try:
        r = requests.get(url_https, timeout=7, verify=False)
        return True, f"HTTPS 连通 ({r.status_code})"
    except Exception as e:
        err = str(e)[:80]
        try:
            url_http = f"http://{ip}:{port}"
            r_http = requests.get(url_http, timeout=7)
            return True, f"HTTP 连通 ({r_http.status_code})"
        except Exception as eh:
            return False, f"失败 - HTTPS: {err} | HTTP: {str(eh)[:50]}"

# ==================== 提取 IP:端口 ====================
def extract_ip_ports(text):
    nodes = set()
    # 匹配 IPv4:端口 和 [IPv6]:端口
    pattern = r'((?:\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})|\[(?:[0-9a-fA-F:]+)\]):(\d{1,5})'
    for ip, port in re.findall(pattern, text):
        p = int(port)
        if 1 <= p <= 65535 and p >= 1024:  # 避免系统保留端口
            nodes.add(f"{ip}:{port}")
    return nodes

# ==================== 主程序 ====================
print("开始搜索 GitHub 公开节点配置...")
print(f"当前查询: {SEARCH_QUERY}\n")

all_nodes = set()
page = 1
total_pages = 1  # 先假设

while page <= total_pages:
    params = {
        'q': SEARCH_QUERY,
        'per_page': PER_PAGE,
        'page': page
    }
    
    try:
        resp = requests.get(API_URL, headers=HEADERS, params=params, timeout=15)
        print(f"页 {page} 请求状态: {resp.status_code}")
        
        if resp.status_code != 200:
            print("错误响应内容：")
            print(resp.text[:600])
            break
            
        data = resp.json()
        items = data.get('items', [])
        
        if 'total_count' in data:
            total_count = data['total_count']
            total_pages = (total_count + PER_PAGE - 1) // PER_PAGE
            print(f"总匹配数约 {total_count}，预计页数 {total_pages}")
        
        if not items:
            print("本页无结果，结束搜索")
            break
        
        for idx, item in enumerate(items, 1):
            html_url = item.get('html_url', '')
            raw_url = html_url.replace('/blob/', '/raw/') if html_url else ''
            
            if not raw_url:
                continue
                
            print(f"  [{idx}] 处理: {raw_url}")
            
            try:
                file_resp = requests.get(raw_url, timeout=12)
                if file_resp.status_code == 200:
                    found = extract_ip_ports(file_resp.text)
                    if found:
                        all_nodes.update(found)
                        print(f"      发现 {len(found)} 个节点")
                else:
                    print(f"      文件下载失败 {file_resp.status_code}")
            except Exception as e:
                print(f"      异常: {str(e)[:100]}")
            
            time.sleep(1.2)  # 避免触发二级限速
        
        page += 1
        time.sleep(4)  # 页面间延迟
        
    except Exception as e:
        print(f"请求异常: {str(e)}")
        break

print(f"\n搜索结束，共收集到 {len(all_nodes)} 个唯一 IP:端口")

# 简单测试前 20 个（可选全部测试，但免费节点不稳定，建议手动选）
print("\n测试前 20 个节点（或全部如果少于20）：")
tested = []
for node in list(all_nodes)[:20]:
    ok, msg = test_node(node)
    status = "可用" if ok else "不可用"
    print(f"{node:22} → {status}  {msg}")
    tested.append((node, ok, msg))
    time.sleep(1.3)

# 保存结果（简单 txt + json）
with open('found_nodes.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(sorted(all_nodes)))

with open('found_nodes.json', 'w', encoding='utf-8') as f:
    json.dump({
        "query": SEARCH_QUERY,
        "count": len(all_nodes),
        "tested": tested,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }, f, ensure_ascii=False, indent=2)

print("\n结果已保存到 found_nodes.txt 和 found_nodes.json")
print("建议：把 found_nodes.txt 导入 Clash / v2rayN 等客户端进一步验证")
