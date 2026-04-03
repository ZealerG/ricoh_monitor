#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""理光映像商品监控脚本 - 监控商城库存并邮件通知。"""

import argparse
import json
import os
import random
import smtplib
import sys
import time
import traceback
from email.header import Header
from email.mime.text import MIMEText
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import requests


STATE_VERSION = 2
DEFAULT_SMTP_SERVER = "smtp.126.com"
DEFAULT_SMTP_PORT = 465
DEFAULT_CID = 9
DEFAULT_KEYWORD = "GR"
DEFAULT_STATE_PATH = "./ricoh_email_monitor.state.json"
DEFAULT_POLL_INTERVAL = 30
MAX_GOODS_HISTORY = 50
MAX_COOLDOWN_SECONDS = 2 * 3600
BASE_403_COOLDOWN_SECONDS = 15 * 60
FAILURE_NOTIFY_INTERVAL_SECONDS = 6 * 3600


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


def parse_bool(value, default=False):
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def parse_int(value, default):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return default


def parse_csv_env(value):
    if not value:
        return []
    normalized = str(value).replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def normalize_text(value):
    return " ".join(str(value or "").strip().lower().split())


def load_config():
    include_keywords = parse_csv_env(os.environ.get("KEYWORDS") or os.environ.get("KEYWORD", DEFAULT_KEYWORD))
    exclude_keywords = parse_csv_env(os.environ.get("EXCLUDE_KEYWORDS", ""))
    match_mode = os.environ.get("MATCH_MODE", "any").strip().lower() or "any"
    if match_mode not in {"any", "all"}:
        match_mode = "any"

    return {
        "smtp_server": os.environ.get("SMTP_SERVER", DEFAULT_SMTP_SERVER).strip(),
        "smtp_port": parse_int(os.environ.get("SMTP_PORT"), DEFAULT_SMTP_PORT),
        "smtp_user": os.environ.get("SMTP_USER", "").strip(),
        "smtp_password": os.environ.get("SMTP_PASSWORD", "").strip(),
        "receiver_emails": parse_csv_env(os.environ.get("RECEIVER_EMAILS", "")),
        "cid": parse_int(os.environ.get("CID"), DEFAULT_CID),
        "include_keywords": include_keywords,
        "include_keywords_normalized": [normalize_text(item) for item in include_keywords if normalize_text(item)],
        "exclude_keywords": exclude_keywords,
        "exclude_keywords_normalized": [normalize_text(item) for item in exclude_keywords if normalize_text(item)],
        "match_mode": match_mode,
        "state_path": os.environ.get("STATE_PATH", DEFAULT_STATE_PATH).strip() or DEFAULT_STATE_PATH,
        "poll_interval": parse_int(os.environ.get("POLL_INTERVAL"), DEFAULT_POLL_INTERVAL),
        "notify_zero_stock": parse_bool(os.environ.get("NOTIFY_ZERO_STOCK"), default=False),
        "request_connect_timeout": 5,
        "request_read_timeout": 10,
        "smtp_timeout": 20,
    }


def validate_config(config):
    errors = []
    if not config["include_keywords_normalized"]:
        errors.append("KEYWORD 或 KEYWORDS 至少需要配置一个关键词")
    if not config["receiver_emails"]:
        errors.append("RECEIVER_EMAILS 不能为空")
    if not config["smtp_user"]:
        errors.append("SMTP_USER 不能为空")
    if not config["smtp_password"]:
        errors.append("SMTP_PASSWORD 不能为空")
    if config["smtp_port"] <= 0:
        errors.append("SMTP_PORT 必须是正整数")
    if config["cid"] <= 0:
        errors.append("CID 必须是正整数")
    if config["poll_interval"] <= 0:
        errors.append("POLL_INTERVAL 必须是正整数")
    return errors


def mask_email(value):
    email = str(value or "").strip()
    if "@" not in email:
        return "***" if email else "-"
    local_part, domain = email.split("@", 1)
    if not local_part:
        return f"***@{domain}"
    if len(local_part) <= 2:
        masked_local = local_part[0] + "*"
    else:
        masked_local = local_part[0] + "*" * (len(local_part) - 2) + local_part[-1]
    return f"{masked_local}@{domain}"


def print_effective_config(config):
    print("=== Effective Monitor Config ===")
    print(f"CID={config['cid']}")
    print(f"KEYWORDS={config['include_keywords'] or []}")
    print(f"EXCLUDE_KEYWORDS={config['exclude_keywords'] or []}")
    print(f"MATCH_MODE={config['match_mode']}")
    print(f"NOTIFY_ZERO_STOCK={config['notify_zero_stock']}")
    print(f"POLL_INTERVAL={config['poll_interval']}")
    print(f"STATE_PATH={config['state_path']}")
    print(f"RECEIVER_COUNT={len(config['receiver_emails'])}")
    print(f"PRIMARY_RECEIVER={mask_email(config['receiver_emails'][0]) if config['receiver_emails'] else '-'}")
    print(f"SMTP_SERVER_SET={bool(config['smtp_server'])}")
    print(f"SMTP_PORT={config['smtp_port']}")
    print(f"SMTP_USER_SET={bool(config['smtp_user'])}")
    print(f"SMTP_PASSWORD_SET={bool(config['smtp_password'])}")
    print("=== End Effective Monitor Config ===")


def default_state():
    return {
        "version": STATE_VERSION,
        "last_success_ts": 0,
        "cooldown_until": 0,
        "ua_index": 0,
        "consecutive_403": 0,
        "last_alert_goods": {},
        "last_goods": [],
        "last_failure_signature": "",
        "last_failure_notify_ts": 0,
        "last_result": "",
    }


def load_state(state_path):
    state = default_state()
    try:
        with open(state_path, "r", encoding="utf-8") as file_handle:
            loaded = json.load(file_handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return state

    if not isinstance(loaded, dict):
        return state

    state.update(loaded)

    if not isinstance(state.get("last_alert_goods"), dict):
        state["last_alert_goods"] = {}
    if not isinstance(state.get("last_goods"), list):
        state["last_goods"] = []

    normalized_alert_goods = {}
    for product_id, item in state["last_alert_goods"].items():
        if isinstance(item, dict):
            normalized_item = normalize_snapshot(item)
            normalized_alert_goods[normalized_item["id"] or str(product_id)] = normalized_item
    state["last_alert_goods"] = normalized_alert_goods
    state["version"] = STATE_VERSION
    state["consecutive_403"] = parse_int(state.get("consecutive_403"), 0)
    state["ua_index"] = parse_int(state.get("ua_index"), 0)
    state["cooldown_until"] = parse_int(state.get("cooldown_until"), 0)
    state["last_success_ts"] = parse_int(state.get("last_success_ts"), 0)
    state["last_failure_signature"] = str(state.get("last_failure_signature", ""))
    state["last_failure_notify_ts"] = parse_int(state.get("last_failure_notify_ts"), 0)
    state["last_result"] = str(state.get("last_result", ""))

    return state


def save_state(state, state_path):
    try:
        with open(state_path, "w", encoding="utf-8") as file_handle:
            json.dump(state, file_handle, ensure_ascii=False, indent=2, sort_keys=True)
    except IOError as exc:
        print(f"警告: 无法保存状态文件: {exc}")


def create_session(ua_index):
    session = requests.Session()
    session.trust_env = False
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods={"GET"},
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=1, pool_maxsize=2)
    session.mount("https://", adapter)
    ua = USER_AGENTS[ua_index % len(USER_AGENTS)]
    session.headers.update(
        {
            "User-Agent": ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://newsite.ricn-mall.com/",
            "Origin": "https://newsite.ricn-mall.com",
        }
    )
    return session


def fetch_products(session, config, page=1, size=20):
    url = "https://newsite.ricn-mall.com/api/pc/get_products"
    params = {"cid": config["cid"], "page": page, "size": size}
    response = session.get(
        url,
        params=params,
        timeout=(config["request_connect_timeout"], config["request_read_timeout"]),
    )
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    if "json" not in content_type.lower():
        snippet = response.text[:200].replace("\n", " ").strip()
        raise ValueError(f"接口返回了非 JSON 内容: {content_type or 'unknown'}; snippet={snippet}")

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        snippet = response.text[:200].replace("\n", " ").strip()
        raise ValueError(f"JSON 解析失败: {exc}; snippet={snippet}") from exc

    if payload.get("status") != 200:
        raise ValueError(f"接口业务状态异常: status={payload.get('status')} msg={payload.get('msg')}")

    data = payload.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("接口 data 字段不是对象")

    goods = data.get("list", [])
    total = parse_int(data.get("count"), 0)
    if not isinstance(goods, list):
        raise ValueError("接口 list 字段不是数组")
    return goods, total


def stock_value(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def product_id_of(product):
    candidates = [
        product.get("id"),
        product.get("goods_id"),
        product.get("store_name"),
    ]
    for value in candidates:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""


def normalize_snapshot(product):
    return {
        "id": product_id_of(product),
        "name": str(product.get("name") or product.get("store_name") or "").strip(),
        "price": str(product.get("price", "")).strip(),
        "stock": stock_value(product.get("stock", 0)),
    }


def matches_keywords(product_name, config):
    normalized_name = normalize_text(product_name)
    if not normalized_name:
        return False

    include_terms = config["include_keywords_normalized"]
    if include_terms:
        if config["match_mode"] == "all":
            include_match = all(term in normalized_name for term in include_terms)
        else:
            include_match = any(term in normalized_name for term in include_terms)
    else:
        include_match = True

    if not include_match:
        return False

    return not any(term in normalized_name for term in config["exclude_keywords_normalized"])


def filter_goods(all_goods, config):
    matched = [product for product in all_goods if matches_keywords(product.get("store_name", ""), config)]
    if config["notify_zero_stock"]:
        return matched
    return [product for product in matched if stock_value(product.get("stock", 0)) > 0]


def snapshot_goods(goods):
    snapshot = {}
    for product in goods:
        normalized = normalize_snapshot(product)
        if normalized["id"]:
            snapshot[normalized["id"]] = normalized
    return snapshot


def changed_goods(current_goods, previous_snapshot):
    changed = []
    for product in current_goods:
        normalized = normalize_snapshot(product)
        previous = previous_snapshot.get(normalized["id"])
        if previous != normalized:
            changed.append(normalized)
    return changed


def list_goods(goods):
    return [normalize_snapshot(product) for product in goods][:MAX_GOODS_HISTORY]


def format_goods_lines(goods):
    lines = []
    normalized_goods = [normalize_snapshot(item) for item in goods]
    for item in normalized_goods:
        product_id = item["id"]
        pc_link = f"https://newsite.ricn-mall.com/goods_detail/{product_id}" if product_id else ""
        mobile_link = f"https://newsite.ricn-mall.com/pages/goods_details/index?id={product_id}" if product_id else ""
        lines.append(
            f"- {item['name']}\n"
            f"  价格: ¥{item['price']}\n"
            f"  库存: {item['stock']}\n"
            f"  电脑端: {pc_link}\n"
            f"  手机端: {mobile_link}\n"
        )
    return "\n".join(lines).strip()


def build_email_content(current_goods, changed, config):
    normalized_current_goods = [normalize_snapshot(item) for item in current_goods]
    normalized_changed = [normalize_snapshot(item) for item in changed]
    keyword_label = ", ".join(config["include_keywords"])
    if config["exclude_keywords"]:
        keyword_label = f"{keyword_label}（排除: {', '.join(config['exclude_keywords'])}）"

    subject = f'提醒：理光映像商城 "{keyword_label}" 商品状态有变化'
    body_parts = [
        f"监控关键词: {keyword_label}",
        f"匹配模式: {config['match_mode']}",
        f"通知零库存: {'是' if config['notify_zero_stock'] else '否'}",
        "",
        f"本次新增或变化商品: {len(normalized_changed)} 个",
        format_goods_lines(normalized_changed),
        "",
        f"当前命中的监控商品: {len(normalized_current_goods)} 个",
        format_goods_lines(normalized_current_goods),
    ]
    return subject, "\n".join(part for part in body_parts if part)


def send_email(subject, body, config, receivers=None):
    receivers = receivers or config["receiver_emails"]
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = Header(subject, "utf-8")
    message["From"] = config["smtp_user"]
    message["To"] = ", ".join(receivers)

    with smtplib.SMTP_SSL(config["smtp_server"], config["smtp_port"], timeout=config["smtp_timeout"]) as server:
        server.login(config["smtp_user"], config["smtp_password"])
        server.sendmail(config["smtp_user"], receivers, message.as_string())


def compute_403_cooldown(state):
    consecutive = parse_int(state.get("consecutive_403"), 0) + 1
    state["consecutive_403"] = consecutive
    return min(BASE_403_COOLDOWN_SECONDS * (2 ** (consecutive - 1)), MAX_COOLDOWN_SECONDS)


def github_run_url():
    server_url = os.environ.get("GITHUB_SERVER_URL", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    if server_url and repository and run_id:
        return f"{server_url}/{repository}/actions/runs/{run_id}"
    return ""


def format_unix_ts(timestamp):
    value = parse_int(timestamp, 0)
    if value <= 0:
        return "-"
    return time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(value))


def failure_signature(result):
    status = str(result.get("status", "")).strip()
    error = normalize_text(result.get("error", ""))
    return f"{status}|{error}"


def should_send_failure_email(state, result):
    status = result.get("status", "")
    if status in {"ok", "cooldown"}:
        return False

    signature = failure_signature(result)
    now = int(time.time())
    last_signature = state.get("last_failure_signature", "")
    last_notify_ts = parse_int(state.get("last_failure_notify_ts"), 0)
    if signature != last_signature:
        return True
    return now - last_notify_ts >= FAILURE_NOTIFY_INTERVAL_SECONDS


def build_failure_email_content(result, config, state):
    first_receiver = config["receiver_emails"][0] if config["receiver_emails"] else "-"
    body_lines = [
        f"理光监控脚本运行异常。",
        "",
        f"异常状态: {result.get('status', 'unknown')}",
        f"错误信息: {result.get('error', '-')}",
        f"主告警接收人: {first_receiver}",
        f"监控关键词: {', '.join(config['include_keywords'])}",
        f"排除关键词: {', '.join(config['exclude_keywords']) or '-'}",
        f"匹配模式: {config['match_mode']}",
        f"通知零库存: {'是' if config['notify_zero_stock'] else '否'}",
        f"CID: {config['cid']}",
        f"状态文件: {config['state_path']}",
        f"matched_count: {result.get('matched_count', 0)}",
        f"changed_count: {result.get('changed_count', 0)}",
        "",
        f"上次成功时间: {format_unix_ts(state.get('last_success_ts', 0))}",
        f"当前冷却截止: {format_unix_ts(state.get('cooldown_until', 0))}",
        f"连续 403 次数: {state.get('consecutive_403', 0)}",
        "",
        f"GITHUB_REPOSITORY: {os.environ.get('GITHUB_REPOSITORY', '-')}",
        f"GITHUB_WORKFLOW: {os.environ.get('GITHUB_WORKFLOW', '-')}",
        f"GITHUB_EVENT_NAME: {os.environ.get('GITHUB_EVENT_NAME', '-')}",
        f"GITHUB_REF: {os.environ.get('GITHUB_REF', '-')}",
        f"GITHUB_RUN_ID: {os.environ.get('GITHUB_RUN_ID', '-')}",
        f"GITHUB_RUN_ATTEMPT: {os.environ.get('GITHUB_RUN_ATTEMPT', '-')}",
        f"运行链接: {github_run_url() or '-'}",
    ]
    traceback_text = str(result.get("traceback", "")).strip()
    if traceback_text:
        body_lines.extend(["", "Traceback:", traceback_text])
    return (
        "告警：Ricoh Monitor 运行异常",
        "\n".join(body_lines),
    )


def notify_failure_if_needed(result, config, state):
    if not config["receiver_emails"]:
        return
    if not config["smtp_user"] or not config["smtp_password"]:
        return
    if not should_send_failure_email(state, result):
        return

    receiver = config["receiver_emails"][0]
    subject, body = build_failure_email_content(result, config, state)
    try:
        send_email(subject, body, config, receivers=[receiver])
        state["last_failure_signature"] = failure_signature(result)
        state["last_failure_notify_ts"] = int(time.time())
        print(f"已向首个收件人发送异常通知: {receiver}")
    except Exception as exc:
        print(f"发送异常通知失败 ({receiver}): {exc}")


def append_github_summary(result, config):
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    lines = [
        "## Ricoh Monitor Summary",
        "",
        f"- status: `{result.get('status', 'unknown')}`",
        f"- keywords: `{', '.join(config['include_keywords'])}`",
        f"- exclude_keywords: `{', '.join(config['exclude_keywords']) or '-'}`",
        f"- matched_count: `{result.get('matched_count', 0)}`",
        f"- changed_count: `{result.get('changed_count', 0)}`",
    ]
    if "error" in result:
        lines.append(f"- error: `{result['error']}`")
    if "remaining" in result:
        lines.append(f"- cooldown_remaining_seconds: `{result['remaining']}`")
    lines.extend(
        [
            f"- cid: `{config['cid']}`",
            f"- match_mode: `{config['match_mode']}`",
            f"- notify_zero_stock: `{config['notify_zero_stock']}`",
            f"- poll_interval: `{config['poll_interval']}`",
            f"- receiver_count: `{len(config['receiver_emails'])}`",
            f"- primary_receiver: `{mask_email(config['receiver_emails'][0]) if config['receiver_emails'] else '-'}`",
        ]
    )

    try:
        with open(summary_path, "a", encoding="utf-8") as file_handle:
            file_handle.write("\n".join(lines) + "\n")
    except OSError as exc:
        print(f"警告: 无法写入 GITHUB_STEP_SUMMARY: {exc}")


def exit_code_for(result):
    failing_statuses = {"config_error", "email_error", "http_error", "network_error", "response_error", "processing_error"}
    return 1 if result.get("status") in failing_statuses else 0


def run():
    config = load_config()
    state = load_state(config["state_path"])
    print_effective_config(config)
    config_errors = validate_config(config)
    if config_errors:
        message = "; ".join(config_errors)
        state["last_result"] = "config_error"
        state["last_goods"] = []
        print(f"配置错误: {message}")
        result = {"status": "config_error", "error": message, "matched_count": 0, "changed_count": 0}
        notify_failure_if_needed(result, config, state)
        save_state(state, config["state_path"])
        append_github_summary(result, config)
        return result

    now = int(time.time())

    if now < state.get("cooldown_until", 0):
        remaining = state["cooldown_until"] - now
        print(f"处于冷却期，跳过请求（剩余 {remaining} 秒）")
        result = {"status": "cooldown", "remaining": remaining, "matched_count": 0, "changed_count": 0}
        append_github_summary(result, config)
        return result

    session = create_session(state.get("ua_index", 0))
    state["ua_index"] = (state.get("ua_index", 0) + 1) % len(USER_AGENTS)

    all_goods = []
    page = 1
    try:
        while True:
            goods, total = fetch_products(session, config, page=page)
            all_goods.extend(goods)
            print(f">>> 第 {page} 页: 本页 {len(goods)} 条，累计 {len(all_goods)}/{total} 条")
            if not goods or len(all_goods) >= total:
                break
            page += 1
            time.sleep(1.8 + random.uniform(-0.6, 0.6))
    except requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 403:
            cooldown_seconds = compute_403_cooldown(state)
            state["cooldown_until"] = int(time.time()) + cooldown_seconds
            state["last_result"] = "403_cooldown"
            print(f"403 Forbidden，进入 {cooldown_seconds} 秒冷却期")
            result = {"status": "403_cooldown", "matched_count": 0, "changed_count": 0}
            notify_failure_if_needed(result, config, state)
            save_state(state, config["state_path"])
            append_github_summary(result, config)
            return result

        state["last_result"] = "http_error"
        print(f"HTTP 错误: {exc}")
        result = {
            "status": "http_error",
            "error": str(exc),
            "matched_count": 0,
            "changed_count": 0,
            "traceback": traceback.format_exc(),
        }
        notify_failure_if_needed(result, config, state)
        save_state(state, config["state_path"])
        append_github_summary(result, config)
        return result
    except requests.exceptions.RequestException as exc:
        state["last_result"] = "network_error"
        print(f"网络请求失败: {exc}")
        result = {
            "status": "network_error",
            "error": str(exc),
            "matched_count": 0,
            "changed_count": 0,
            "traceback": traceback.format_exc(),
        }
        notify_failure_if_needed(result, config, state)
        save_state(state, config["state_path"])
        append_github_summary(result, config)
        return result
    except ValueError as exc:
        state["last_result"] = "response_error"
        print(f"接口响应异常: {exc}")
        result = {
            "status": "response_error",
            "error": str(exc),
            "matched_count": 0,
            "changed_count": 0,
            "traceback": traceback.format_exc(),
        }
        notify_failure_if_needed(result, config, state)
        save_state(state, config["state_path"])
        append_github_summary(result, config)
        return result

    state["last_success_ts"] = int(time.time())
    state["cooldown_until"] = 0
    state["consecutive_403"] = 0
    state["last_failure_signature"] = ""
    state["last_failure_notify_ts"] = 0

    current_goods = filter_goods(all_goods, config)
    previous_alert_goods = state.get("last_alert_goods", {})
    changed = changed_goods(current_goods, previous_alert_goods)

    matched_count = len(current_goods)
    changed_count = len(changed)

    if changed:
        try:
            subject, body = build_email_content(current_goods, changed, config)
            send_email(subject, body, config)
            print(f"已发送邮件至 {', '.join(config['receiver_emails'])}")
            state["last_alert_goods"] = snapshot_goods(current_goods)
        except Exception as exc:
            state["last_goods"] = list_goods(current_goods)
            state["last_result"] = "processing_error"
            print(f"通知流程失败: {exc}")
            result = {
                "status": "processing_error",
                "error": str(exc),
                "matched_count": matched_count,
                "changed_count": changed_count,
                "traceback": traceback.format_exc(),
            }
            notify_failure_if_needed(result, config, state)
            save_state(state, config["state_path"])
            append_github_summary(result, config)
            return result
    else:
        print(f'未发现需要通知的商品，当前命中 {matched_count} 个')
        state["last_alert_goods"] = snapshot_goods(current_goods)

    state["last_goods"] = list_goods(current_goods)
    state["last_result"] = "ok"
    save_state(state, config["state_path"])

    result = {"status": "ok", "matched_count": matched_count, "changed_count": changed_count}
    append_github_summary(result, config)
    return result


def handler(event, context):
    return run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="理光映像商品监控")
    parser.add_argument("--loop", action="store_true", help="Daemon 模式：持续运行")
    args = parser.parse_args()

    if args.loop:
        print("进入 Daemon 模式，按 Ctrl+C 退出")
        try:
            while True:
                result = run()
                if result.get("status") not in {"ok", "cooldown", "403_cooldown"}:
                    print(f"本次运行状态: {result['status']}")
                interval = load_config()["poll_interval"] + random.randint(0, 5)
                print(f"等待 {interval} 秒...")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n已退出")
    else:
        sys.exit(exit_code_for(run()))
