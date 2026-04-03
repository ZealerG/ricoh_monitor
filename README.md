# 理光映像商城监控脚本

监控理光映像商城（https://newsite.ricn-mall.com）的商品库存，支持“商品仍在页面上就持续提醒”或“仅状态变化时提醒”两种模式。

## 功能特性

- 🔍 支持包含词 / 排除词的关键词监控
- 📧 支持 `presence` / `change` 两种提醒模式
- 🔄 支持 GitHub Actions 自动运行（原生 schedule 为每 5 分钟，可配合 `repository_dispatch`）
- 🛡️ 403 自动冷却、UA 轮换等反爬策略
- 📋 GitHub Actions Summary 输出，便于排障
- 🚨 运行异常时自动给第一个收件人发送诊断邮件

## 部署方式

### GitHub Actions（推荐）

1. Fork 本仓库
2. 配置 Actions Secrets 和 Variables（Settings → Secrets and variables → Actions）：

建议区分：

- `Secrets`
  - `GIST_ID`
  - `GIST_PAT`
  - `SMTP_SERVER`
  - `SMTP_PORT`
  - `SMTP_USER`
  - `SMTP_PASSWORD`
  - `RECEIVER_EMAILS`
- `Variables`
  - `CID`
  - `POLL_INTERVAL`
  - `KEYWORD`
  - `KEYWORDS`
  - `EXCLUDE_KEYWORDS`
  - `MATCH_MODE`
  - `ALERT_MODE`
  - `NOTIFY_ZERO_STOCK`

这样 workflow 日志里能看到这些非敏感配置的实际生效值。如果你继续把它们放在 `Secrets` 里，GitHub 可能会把日志里的对应值自动遮罩成 `***`。

| 配置项 | 建议位置 | 说明 |
|--------|----------|------|
| `GIST_ID` | Secret | 存储状态的 Gist ID |
| `GIST_PAT` | Secret | GitHub PAT（需 gist 权限） |
| `SMTP_SERVER` | Secret | SMTP 服务器（如 smtp.126.com） |
| `SMTP_PORT` | Secret | SMTP 端口（如 465） |
| `SMTP_USER` | Secret | 发件人邮箱 |
| `SMTP_PASSWORD` | Secret | SMTP 授权码 |
| `RECEIVER_EMAILS` | Secret | 收件人邮箱（多个用逗号分隔，第一个收件人会接收异常诊断邮件） |
| `CID` | Variable | 商品分类 ID，默认 `9` |
| `POLL_INTERVAL` | Variable | 本地 loop 模式轮询间隔，GitHub Actions 通常用不到 |
| `KEYWORD` | Variable | 单个兼容关键词（如 `GR III`） |
| `KEYWORDS` | Variable | 多个包含词，逗号分隔（推荐，如 `GR III,GR IIIx,HDF`） |
| `EXCLUDE_KEYWORDS` | Variable | 排除词，逗号分隔（如 `RING,金圈,配件`） |
| `MATCH_MODE` | Variable | `any` 或 `all`，默认 `any` |
| `ALERT_MODE` | Variable | `presence` 或 `change`，默认 `presence` |
| `NOTIFY_ZERO_STOCK` | Variable | 是否连 0 库存商品也通知，默认 `false` |

3. 如需比 5 分钟更高的频率，可配置 cron-job.org 触发 `repository_dispatch`

详细步骤参考 workflow 文件中的注释。

### 在日志里看配置

脚本每次运行开始时都会输出一段 `Effective Monitor Config`，其中会显示：

- `CID`
- `KEYWORDS`
- `EXCLUDE_KEYWORDS`
- `MATCH_MODE`
- `ALERT_MODE`
- `NOTIFY_ZERO_STOCK`
- `POLL_INTERVAL`
- `STATE_PATH`
- `RECEIVER_COUNT`
- `PRIMARY_RECEIVER` 的脱敏版本
- SMTP 是否已配置

注意：

- 如果某个值来自 GitHub `Secrets`，GitHub 可能会把日志中的该值替换成 `***`。
- 如果你希望看到明文配置，请把非敏感项放到 `Variables`，不要放在 `Secrets`。

### 抢 GR 推荐配置

如果你主要盯 GR 机身，建议优先配置：

```bash
KEYWORDS="GR III,GR IIIx,HDF"
EXCLUDE_KEYWORDS="RING,金圈,配件"
MATCH_MODE="any"
ALERT_MODE="presence"
NOTIFY_ZERO_STOCK="false"
```

这样能避开 `GR GOLD RING` 这类误报。

## 当前运行策略

当前脚本在 GitHub Actions 上的策略如下：

1. 触发方式
   - workflow 自带 `schedule`，每 5 分钟运行一次。
   - 也支持 `repository_dispatch` 和手动 `workflow_dispatch`。
   - 如果你需要更高频率，可以额外用 cron-job.org 触发 `repository_dispatch`。

2. 状态恢复
   - 每次运行开始前，会尝试从 Gist 读取 `ricoh_monitor_state.json`。
   - 这里保存的是上次成功抓取时间、上次已通知商品快照、403 冷却状态、最近失败通知签名等。

3. 抓取逻辑
   - 脚本会轮换 User-Agent，请求 `https://newsite.ricn-mall.com/api/pc/get_products`。
   - 会分页抓取当前分类下全部商品，而不是只看第一页。
   - 会校验 HTTP 状态码、`Content-Type`、JSON 解析和接口业务状态。

4. 过滤逻辑
   - 先按 `KEYWORDS` / `KEYWORD` 做包含匹配。
   - 再按 `EXCLUDE_KEYWORDS` 排除误报词。
   - 默认只监控有库存商品；如果 `NOTIFY_ZERO_STOCK=true`，则 0 库存也会进入通知范围。

5. 通知逻辑
   - `ALERT_MODE=presence`：只要商品还出现在页面上，每次轮询都会给全部收件人发提醒邮件。
   - `ALERT_MODE=change`：只有“命中商品快照发生变化”时才给全部收件人发提醒邮件。
   - `change` 模式下，变化包含：新商品出现、库存变化、价格变化。

6. 异常处理
   - 如果遇到 `config_error`、`http_error`、`network_error`、`response_error`、`email_error` 或 `403_cooldown`，脚本会尽量给 `RECEIVER_EMAILS` 的第一个地址发送一封诊断邮件。
   - 诊断邮件会包含错误类型、错误信息、关键词配置、GitHub Actions 运行信息、最近成功时间、冷却状态等。
   - 同一类失败不会每 5 分钟都发，会按“错误签名变化立即发，否则每 6 小时最多再发一次”的策略节流。
   - 如果 SMTP 本身故障，异常诊断邮件也可能发不出去，这种情况会在 Action 日志和 Summary 中体现。

7. 403 策略
   - 遇到 403 时不会直接停 6 小时。
   - 现在使用递增冷却：从 15 分钟开始翻倍，最大 2 小时。
   - 冷却状态也会写回 Gist，避免下一次运行继续硬撞接口。

8. 状态持久化
   - 无论本次运行成功还是失败，workflow 都会尝试把最新 state 保存回 Gist。
   - 这样即使失败，也不会丢失冷却信息和去重信息。

### 本地运行

```bash
# 设置环境变量
export SMTP_SERVER="smtp.126.com"
export SMTP_PORT="465"
export SMTP_USER="your_email@126.com"
export SMTP_PASSWORD="your_smtp_password"
export RECEIVER_EMAILS="receiver@example.com"
export KEYWORDS="GR III,GR IIIx,HDF"
export EXCLUDE_KEYWORDS="RING,金圈,配件"
export ALERT_MODE="presence"

# 单次运行
python3 ricoh_email_monitor.py

# 持续运行（每 30 秒检查一次）
python3 ricoh_email_monitor.py --loop
```

## 邮件通知示例

```
提醒：理光映像商城 "GR III, GR IIIx, HDF" 商品状态有变化

本次新增或变化商品: 1 个

- 官翻品 RICOH GR IIIx HDF
  价格: ¥5999.00
  库存: 3
  电脑端: https://newsite.ricn-mall.com/goods_detail/114
  手机端: https://newsite.ricn-mall.com/pages/goods_details/index?id=114
```

## 异常通知示例

```
告警：Ricoh Monitor 运行异常

理光监控脚本运行异常。

异常状态: response_error
错误信息: 接口返回了非 JSON 内容: text/html; snippet=<html>...
主告警接收人: email1@qq.com
监控关键词: GR III, GR IIIx, HDF
排除关键词: RING, 金圈, 配件
匹配模式: any
通知零库存: 否
CID: 9
状态文件: ricoh_monitor_state.json
GITHUB_REPOSITORY: yourname/ricoh_monitor
运行链接: https://github.com/yourname/ricoh_monitor/actions/runs/123456789
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `ricoh_email_monitor.py` | 主脚本 |
| `ricoh_email_monitor.env.example` | 环境变量示例 |
| `requirements.txt` | Python 依赖 |
| `.github/workflows/ricoh-monitor.yml` | GitHub Actions 配置 |

## License

MIT
