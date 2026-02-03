# 理光映像商城监控脚本

监控理光映像商城（https://newsite.ricn-mall.com）的商品库存，有货时自动发送邮件通知。

## 功能特性

- 🔍 监控指定关键词的商品库存
- 📧 有货时自动发送邮件通知（含价格、库存、链接）
- 🔄 支持 GitHub Actions 自动运行（每 2 分钟检查一次）
- 🛡️ 403 自动冷却、UA 轮换等反爬策略

## 部署方式

### GitHub Actions（推荐）

1. Fork 本仓库
2. 配置 Repository Secrets（Settings → Secrets and variables → Actions）：

| Secret | 说明 |
|--------|------|
| `GIST_ID` | 存储状态的 Gist ID |
| `GIST_PAT` | GitHub PAT（需 gist 权限） |
| `SMTP_SERVER` | SMTP 服务器（如 smtp.126.com） |
| `SMTP_PORT` | SMTP 端口（如 465） |
| `SMTP_USER` | 发件人邮箱 |
| `SMTP_PASSWORD` | SMTP 授权码 |
| `RECEIVER_EMAILS` | 收件人邮箱（多个用逗号分隔） |
| `KEYWORD` | 监控关键词（如 `RICOH GR III`） |

3. 配置 cron-job.org 每 2 分钟触发 `repository_dispatch`

详细步骤参考 workflow 文件中的注释。

### 本地运行

```bash
# 设置环境变量
export SMTP_SERVER="smtp.126.com"
export SMTP_PORT="465"
export SMTP_USER="your_email@126.com"
export SMTP_PASSWORD="your_smtp_password"
export RECEIVER_EMAILS="receiver@example.com"
export KEYWORD="RICOH GR III"

# 单次运行
python3 ricoh_email_monitor.py

# 持续运行（每 30 秒检查一次）
python3 ricoh_email_monitor.py --loop
```

## 邮件通知示例

```
提醒：理光映像商城"RICOH GR III"商品有货了！

以下商品有货：

- 官翻品 RICOH GR IIIx HDF
  价格: ¥5999.00
  库存: 3
  电脑端: https://newsite.ricn-mall.com/goods_detail/114
  手机端: https://newsite.ricn-mall.com/pages/goods_details/index?id=114
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
