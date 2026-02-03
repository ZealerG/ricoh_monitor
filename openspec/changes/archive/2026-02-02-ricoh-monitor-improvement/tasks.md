# 任务清单：理光映像 GR 商品监控脚本改进

## 实施顺序（零决策，机械执行）

### Task 1: 环境变量配置模块
**文件**: `ricoh_email_monitor.py` 顶部
**操作**: 替换硬编码配置为环境变量读取

```python
import os

# 配置读取
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.126.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
RECEIVER_EMAILS = os.environ.get("RECEIVER_EMAILS", "").split(",")
CID = int(os.environ.get("CID", "9"))
KEYWORD = os.environ.get("KEYWORD", "GR")
STATE_PATH = os.environ.get("STATE_PATH", "./ricoh_email_monitor.state.json")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))
```

### Task 2: User-Agent 池
**文件**: `ricoh_email_monitor.py`
**操作**: 添加 UA 池常量

```python
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]
```

### Task 3: 状态管理模块
**文件**: `ricoh_email_monitor.py`
**操作**: 添加状态加载/保存函数

```python
import json
import time

def load_state():
    """加载状态文件，返回默认值如果不存在"""
    default = {"version": 1, "last_success_ts": 0, "last_ids": [], "cooldown_until": 0, "ua_index": 0}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save_state(state):
    """保存状态到文件"""
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"警告: 无法保存状态文件: {e}")
```

### Task 4: 重写 fetch_store_names 函数
**文件**: `ricoh_email_monitor.py`
**操作**: 添加完整 Headers、重试逻辑、Session 管理

```python
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def create_session(ua_index):
    """创建带重试的 Session"""
    session = requests.Session()
    session.trust_env = False

    retry = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504, 429])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=1, pool_maxsize=2)
    session.mount("https://", adapter)

    ua = USER_AGENTS[ua_index % len(USER_AGENTS)]
    session.headers.update({
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://newsite.ricn-mall.com/",
        "Origin": "https://newsite.ricn-mall.com",
    })
    return session

def fetch_products(session, cid, page=1, size=20):
    """请求商品列表，返回 (goods_list, total_count) 或抛出异常"""
    url = "https://newsite.ricn-mall.com/api/pc/get_products"
    params = {"cid": cid, "page": page, "size": size}

    resp = session.get(url, params=params, timeout=(5, 10))
    resp.raise_for_status()

    data = resp.json().get("data", {})
    goods = data.get("list", [])
    total = data.get("count", 0)
    return goods, total
```

### Task 5: 核心 run() 函数
**文件**: `ricoh_email_monitor.py`
**操作**: 实现主逻辑（冷却检查、去重通知、状态更新）

```python
def run():
    """主运行函数"""
    state = load_state()

    # 检查 403 冷却
    if time.time() < state.get("cooldown_until", 0):
        print(f"处于冷却期，跳过请求（剩余 {int(state['cooldown_until'] - time.time())}秒）")
        return {"status": "cooldown"}

    # 创建 Session
    session = create_session(state.get("ua_index", 0))
    state["ua_index"] = (state.get("ua_index", 0) + 1) % len(USER_AGENTS)

    # 抓取所有商品
    all_goods = []
    page = 1
    try:
        while True:
            goods, total = fetch_products(session, CID, page)
            all_goods.extend(goods)
            print(f">>> 第 {page} 页: 本页 {len(goods)} 条，累计 {len(all_goods)}/{total} 条")

            if not goods or len(all_goods) >= total:
                break
            page += 1
            time.sleep(1.8 + random.uniform(-0.6, 0.6))  # 分页间隔
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            print("403 Forbidden，进入冷却期")
            state["cooldown_until"] = int(time.time()) + 6 * 3600  # 6小时冷却
            save_state(state)
            return {"status": "403_cooldown"}
        raise

    # 更新成功时间
    state["last_success_ts"] = int(time.time())

    # 筛选 GR 商品
    matched = [g for g in all_goods if KEYWORD in g.get("store_name", "")]

    # 去重：仅通知新商品
    known_ids = set(state.get("last_ids", []))
    new_goods = [g for g in matched if g.get("store_name", "") not in known_ids]

    if new_goods:
        # 构造邮件
        subject = f"提醒：理光映像商城上新包含"{KEYWORD}"的商品"
        body = "以下是新上架的商品：\n\n"
        for g in new_goods:
            name = g.get("store_name", "未知")
            goods_id = g.get("goods_id", "")
            link = f"https://newsite.ricn-mall.com/goods_detail?goods_id={goods_id}" if goods_id else ""
            body += f"- {name}\n  链接: {link}\n\n"

        # 发送邮件
        for receiver in RECEIVER_EMAILS:
            if receiver.strip():
                try:
                    send_email(subject, body, SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, receiver.strip())
                    print(f"已发送邮件至 {receiver.strip()}")
                except Exception as e:
                    print(f"发送邮件失败 ({receiver}): {e}")

        # 更新已通知列表
        new_ids = [g.get("store_name", "") for g in new_goods]
        state["last_ids"] = (state.get("last_ids", []) + new_ids)[-200:]  # FIFO 保留200条
    else:
        print(f"未发现新的"{KEYWORD}"商品")

    save_state(state)
    return {"status": "ok", "new_count": len(new_goods)}
```

### Task 6: 云函数入口 + 双模式支持
**文件**: `ricoh_email_monitor.py` 底部
**操作**: 替换 `if __name__ == "__main__"` 块

```python
# 云函数入口
def handler(event, context):
    return run()

# 本地/青龙入口
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="理光映像 GR 商品监控")
    parser.add_argument("--loop", action="store_true", help="Daemon 模式：持续运行")
    args = parser.parse_args()

    if args.loop:
        print("进入 Daemon 模式，按 Ctrl+C 退出")
        try:
            while True:
                run()
                interval = POLL_INTERVAL + random.randint(0, 5)
                print(f"等待 {interval} 秒...")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n已退出")
    else:
        run()
```

### Task 7: 删除硬编码敏感信息
**文件**: `ricoh_email_monitor.py`
**操作**: 移除原脚本中的 `SENDER_PASSWORD = 'xxx'` 等硬编码

### Task 8: 创建 .env.example 示例文件
**文件**: `ricoh_email_monitor.env.example`
**内容**:
```
SMTP_SERVER=smtp.126.com
SMTP_PORT=465
SMTP_USER=your_email@126.com
SMTP_PASSWORD=your_smtp_password
RECEIVER_EMAILS=email1@qq.com,email2@qq.com
CID=9
KEYWORD=GR
STATE_PATH=./ricoh_email_monitor.state.json
POLL_INTERVAL=30
```

## 验证检查清单

- [x] 环境变量读取正确
- [x] UA 池轮换正常
- [x] 403 冷却逻辑生效
- [x] 去重通知正常（同一商品不重复发邮件）
- [x] 状态文件正确保存/加载
- [x] Daemon 模式正常运行
- [x] 云函数入口可调用
- [x] 邮件包含商品链接

## 审查修复记录

### Codex 审查发现 (2026-02-02)
1. **[Critical] f-string 引号问题** - 已修复：使用单引号包裹含中文引号的 f-string
2. **[High] 网络异常处理** - 已修复：添加 `RequestException` 捕获
3. **[High] 状态文件类型校验** - 已修复：`load_state()` 添加类型归一化
4. **[Medium] 去重键** - 已修复：改用 `goods_id`（回退到 `store_name`）

### Gemini 审查发现
1. **云函数状态丢失** - 已知限制：云函数需外部存储，当前仅适合青龙/本地
2. **类型提示** - 未修复（非关键）
