# 任务清单：GitHub Actions 迁移

## 实施顺序（零决策，机械执行）

### Task 1: 创建 GitHub Actions Workflow 文件 ✅
**文件**: `.github/workflows/ricoh-monitor.yml`
**状态**: 已完成（经双模型审查并修复）
**内容**:
```yaml
name: Ricoh GR Monitor

on:
  repository_dispatch:
    types: [monitor_trigger]
  workflow_dispatch:
  schedule:
    - cron: '*/5 * * * *'  # 备用：每5分钟

concurrency:
  group: ricoh-monitor
  cancel-in-progress: false

env:
  GIST_ID: ${{ secrets.GIST_ID }}
  STATE_FILE: ricoh_monitor_state.json

jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests

      - name: Restore state from Gist
        env:
          GH_TOKEN: ${{ secrets.GIST_PAT }}
        run: |
          gh gist view $GIST_ID -f $STATE_FILE > $STATE_FILE 2>/dev/null || echo '{}' > $STATE_FILE
          cat $STATE_FILE

      - name: Run monitor
        env:
          SMTP_SERVER: ${{ secrets.SMTP_SERVER }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
          RECEIVER_EMAILS: ${{ secrets.RECEIVER_EMAILS }}
          STATE_PATH: ${{ env.STATE_FILE }}
        run: python ricoh_email_monitor.py

      - name: Save state to Gist
        if: always()
        env:
          GH_TOKEN: ${{ secrets.GIST_PAT }}
        run: |
          if [ -f $STATE_FILE ]; then
            gh gist edit $GIST_ID -f $STATE_FILE $STATE_FILE
          fi
```

### Task 2: 创建 GitHub Gist 存储状态
**手动操作**:
1. 访问 https://gist.github.com
2. 创建私有 Gist，文件名 `ricoh_monitor_state.json`，内容 `{}`
3. 记录 Gist ID（URL 最后一段）

### Task 3: 创建 GitHub Personal Access Tokens
**手动操作**:
1. 访问 https://github.com/settings/tokens
2. 创建 Token 1 (GIST_PAT): 权限 `gist`
3. 创建 Token 2 (DISPATCH_TOKEN): 权限 `repo`
4. 安全保存两个 Token

### Task 4: 配置 Repository Secrets
**手动操作** (Settings → Secrets and variables → Actions):
| Secret 名称 | 值 |
|-------------|-----|
| `GIST_ID` | Gist ID |
| `GIST_PAT` | Token 1 |
| `SMTP_SERVER` | smtp.126.com |
| `SMTP_PORT` | 465 |
| `SMTP_USER` | 你的邮箱 |
| `SMTP_PASSWORD` | SMTP 密码 |
| `RECEIVER_EMAILS` | 收件人（逗号分隔） |

### Task 5: 配置 cron-job.org
**手动操作**:
1. 注册 https://cron-job.org
2. 创建新任务:
   - URL: `https://api.github.com/repos/{你的用户名}/{仓库名}/dispatches`
   - Method: POST
   - Headers:
     - `Authorization`: `Bearer {DISPATCH_TOKEN}`
     - `Accept`: `application/vnd.github.v3+json`
     - `User-Agent`: `ricoh-monitor-cron`
   - Body: `{"event_type": "monitor_trigger"}`
   - Schedule: Every 2 minutes
   - Enable failure notifications

### Task 6: 验证测试
**操作**:
1. 手动触发 workflow (Actions → Run workflow)
2. 检查 Gist 状态是否更新
3. 等待 cron-job.org 自动触发
4. 确认邮件通知正常

## 验证检查清单

- [x] Workflow 文件语法正确
- [ ] Gist 读写正常（需手动验证）
- [ ] Secrets 配置完整（需手动配置）
- [ ] cron-job.org 触发成功（需手动配置）
- [ ] 状态去重正常（需运行验证）
- [ ] 邮件通知正常（需运行验证）
- [ ] 并发控制生效（需运行验证）
