#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""理光映像 GR 商品监控脚本 - 监控商城上新并邮件通知"""

import os
import json
import time
import random
import argparse
import requests
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============ 配置（环境变量读取） ============
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.126.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
RECEIVER_EMAILS = [e.strip() for e in os.environ.get("RECEIVER_EMAILS", "").split(",") if e.strip()]
CID = int(os.environ.get("CID", "9"))
KEYWORD = os.environ.get("KEYWORD", "GR")
STATE_PATH = os.environ.get("STATE_PATH", "./ricoh_email_monitor.state.json")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))
NOTIFY_ZERO_STOCK = os.environ.get("NOTIFY_ZERO_STOCK", "false").lower() == "true"

# ============ User-Agent 池 ============
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

# ============ 状态管理 ============
def load_state():
    default = {"version": 1, "last_success_ts": 0, "last_ids": [], "cooldown_until": 0, "ua_index": 0}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default.copy()
    # 类型校验与归一化
    if not isinstance(state, dict):
        return default.copy()
    for key, val in default.items():
        if key not in state or not isinstance(state[key], type(val)):
            state[key] = val
    return state

def save_state(state):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"警告: 无法保存状态文件: {e}")

# ============ HTTP 请求 ============
def create_session(ua_index):
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
    url = "https://newsite.ricn-mall.com/api/pc/get_products"
    params = {"cid": cid, "page": page, "size": size}
    resp = session.get(url, params=params, timeout=(5, 10))
    resp.raise_for_status()
    data = resp.json().get("data", {})
    goods = data.get("list", [])
    total = data.get("count", 0)
    return goods, total

# ============ 邮件通知 ============
def send_email(subject, body, smtp_server, smtp_port, sender_email, sender_password, receiver_email):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = sender_email
    msg["To"] = receiver_email
    with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, [receiver_email], msg.as_string())

# ============ 主运行函数 ============
def run():
    state = load_state()

    # 检查 403 冷却
    if time.time() < state.get("cooldown_until", 0):
        remaining = int(state["cooldown_until"] - time.time())
        print(f"处于冷却期，跳过请求（剩余 {remaining} 秒）")
        return {"status": "cooldown", "remaining": remaining}

    # 创建 Session 并轮换 UA
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
            time.sleep(1.8 + random.uniform(-0.6, 0.6))
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 403:
            print("403 Forbidden，进入 6 小时冷却期")
            state["cooldown_until"] = int(time.time()) + 6 * 3600
            save_state(state)
            return {"status": "403_cooldown"}
        print(f"HTTP 错误: {e}")
        save_state(state)
        return {"status": "http_error", "error": str(e)}
    except requests.exceptions.RequestException as e:
        print(f"网络请求失败: {e}")
        save_state(state)
        return {"status": "network_error", "error": str(e)}

    state["last_success_ts"] = int(time.time())

    # 筛选匹配关键词的商品（NOTIFY_ZERO_STOCK=true 时包含无货商品）
    if NOTIFY_ZERO_STOCK:
        matched = [g for g in all_goods if KEYWORD in g.get("store_name", "")]
    else:
        matched = [g for g in all_goods if KEYWORD in g.get("store_name", "") and g.get("stock", 0) > 0]

    if matched:
        subject = f'提醒：理光映像商城"{KEYWORD}"商品有货了！'
        body = "以下商品有货：\n\n"
        for g in matched:
            name = g.get("store_name", "未知")
            product_id = g.get("id", "")
            stock = g.get("stock", "未知")
            price = g.get("price", "未知")
            pc_link = f"https://newsite.ricn-mall.com/goods_detail/{product_id}" if product_id else ""
            mobile_link = f"https://newsite.ricn-mall.com/pages/goods_details/index?id={product_id}" if product_id else ""
            body += f"- {name}\n  价格: ¥{price}\n  库存: {stock}\n  电脑端: {pc_link}\n  手机端: {mobile_link}\n\n"

        for receiver in RECEIVER_EMAILS:
            try:
                send_email(subject, body, SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, receiver)
                print(f"已发送邮件至 {receiver}")
            except Exception as e:
                print(f"发送邮件失败 ({receiver}): {e}")
    else:
        print(f'未发现有货的"{KEYWORD}"商品')

    # 记录当前匹配商品（仅用于状态追踪）
    state["last_goods"] = [{
        "id": str(g.get("id", "")),
        "name": g.get("store_name", ""),
        "price": g.get("price", ""),
        "stock": g.get("stock", 0),
        "ts": int(time.time())
    } for g in matched][-50:]

    save_state(state)
    return {"status": "ok", "matched_count": len(matched)}

# ============ 云函数入口 ============
def handler(event, context):
    return run()

# ============ 本地/青龙入口 ============
if __name__ == "__main__":
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
