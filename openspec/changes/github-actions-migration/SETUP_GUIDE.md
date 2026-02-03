# GitHub Actions 迁移设置指南

本指南帮助你完成 Ricoh GR 监控脚本迁移到 GitHub Actions 的手动配置步骤。

## 前置条件

- 一个 **公开** 的 GitHub 仓库（公开仓库 Actions 免费无限制）
- 126 邮箱或其他支持 SMTP 的邮箱

---

## Step 1: 创建 GitHub Gist（状态存储）

1. 访问 https://gist.github.com
2. 点击 **New gist**
3. 文件名填写：`ricoh_monitor_state.json`
4. 内容填写：`{}`
5. 选择 **Create secret gist**（私有）
6. 创建后，复制 URL 最后一段作为 **GIST_ID**
   - 例如：`https://gist.github.com/yourname/abc123def456` → GIST_ID 是 `abc123def456`

---

## Step 2: 创建 Personal Access Tokens

访问 https://github.com/settings/tokens → **Generate new token (classic)**

### Token 1: GIST_PAT（Gist 读写权限）
- Note: `ricoh-monitor-gist`
- Expiration: 选择合适的有效期（建议 90 天或更长）
- Scopes: 勾选 `gist`
- 点击 **Generate token** 并复制保存

### Token 2: DISPATCH_TOKEN（触发 workflow 权限）
- Note: `ricoh-monitor-dispatch`
- Expiration: 选择合适的有效期
- Scopes: 勾选 `repo`
- 点击 **Generate token** 并复制保存

⚠️ **重要**: Token 只显示一次，请立即保存到安全的地方！

---

## Step 3: 配置 Repository Secrets

1. 进入你的 GitHub 仓库
2. Settings → Secrets and variables → Actions
3. 点击 **New repository secret**，逐个添加以下 Secrets：

| Secret 名称 | 值 | 说明 |
|-------------|-----|------|
| `GIST_ID` | Step 1 复制的 Gist ID | 状态存储位置 |
| `GIST_PAT` | Token 1 | Gist 读写权限 |
| `SMTP_SERVER` | `smtp.126.com` | SMTP 服务器 |
| `SMTP_PORT` | `465` | SMTP 端口 |
| `SMTP_USER` | 你的 126 邮箱地址 | 发件人 |
| `SMTP_PASSWORD` | SMTP 授权码 | 不是登录密码！|
| `RECEIVER_EMAILS` | 收件人邮箱（多个用逗号分隔） | 通知目标 |

### 关于 126 邮箱 SMTP 授权码
1. 登录 https://mail.126.com
2. 设置 → POP3/SMTP/IMAP
3. 开启 SMTP 服务
4. 获取授权码（这才是 SMTP_PASSWORD）

---

## Step 4: 配置 cron-job.org（高频触发）

1. 注册 https://cron-job.org（免费）
2. 登录后点击 **CREATE CRONJOB**
3. 填写以下信息：

**Basic 配置**：
- Title: `Ricoh GR Monitor`
- URL: `https://api.github.com/repos/{用户名}/{仓库名}/dispatches`
  - 例如：`https://api.github.com/repos/zealerg/scripts/dispatches`

**Schedule 配置**：
- 选择 **Every 2 minutes**（或根据需要调整）

**Advanced 配置**：
- Enable job: ✅
- Request method: `POST`

**Headers**（点击 Add header）：
```
Authorization: Bearer {你的 DISPATCH_TOKEN}
Accept: application/vnd.github.v3+json
User-Agent: ricoh-monitor-cron
```

**Request body**：
```json
{"event_type": "monitor_trigger"}
```

**Notifications**：
- 建议开启 **Notify me of failures**

4. 点击 **CREATE** 保存

---

## Step 5: 验证测试

### 5.1 手动触发测试
1. 进入仓库的 **Actions** 页面
2. 选择 **Ricoh GR Monitor** workflow
3. 点击 **Run workflow** → **Run workflow**
4. 等待运行完成，检查日志

### 5.2 检查 Gist 状态
1. 访问你的 Gist 页面
2. 确认 `ricoh_monitor_state.json` 内容已更新

### 5.3 等待 cron-job.org 自动触发
1. 等待 2 分钟
2. 检查 Actions 页面是否有新的运行记录
3. 如果没有，检查 cron-job.org 的执行日志

### 5.4 确认邮件通知
- 如果检测到 GR 商品上新，应收到邮件通知

---

## 故障排除

### Workflow 没有触发
- 检查 DISPATCH_TOKEN 是否有 `repo` 权限
- 检查 cron-job.org 的 URL 是否正确
- 查看 cron-job.org 的执行日志

### Gist 读写失败
- 检查 GIST_PAT 是否有 `gist` 权限
- 检查 GIST_ID 是否正确

### 邮件发送失败
- 检查 SMTP 配置是否正确
- 确认使用的是 SMTP 授权码而非登录密码
- 检查收件人邮箱格式

### 403 Forbidden（被封）
- 脚本会自动进入 6 小时冷却期
- 查看 Gist 中的 `cooldown_until` 字段

---

## 验证检查清单

- [ ] Workflow 文件已推送到仓库
- [ ] Gist 创建成功，GIST_ID 正确
- [ ] 两个 PAT 创建成功，权限正确
- [ ] 所有 7 个 Secrets 配置完成
- [ ] cron-job.org 任务创建成功
- [ ] 手动触发 workflow 成功
- [ ] Gist 状态正常更新
- [ ] cron-job.org 自动触发成功
- [ ] 邮件通知正常（可通过修改关键词测试）
