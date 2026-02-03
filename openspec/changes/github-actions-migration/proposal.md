# 提案：理光映像监控脚本迁移至 GitHub Actions

## 背景

用户需要高频监控理光映像商城 GR 官翻品上新，当前脚本因 IP 被封失效。GitHub Actions 提供免费的运行环境且每次运行 IP 不同，可规避封禁问题。

## 约束集

### 硬约束
1. **GitHub Actions cron 最小粒度**: 5 分钟，且不精确（可能延迟 1-10 分钟）
2. **每次运行是全新环境**: 文件系统临时，状态无法本地持久化
3. **公开仓库免费**: 私有仓库有分钟配额限制（2000 分钟/月）
4. **workflow 单次最长运行**: 6 小时
5. **Secrets 管理**: 敏感信息必须通过 GitHub Secrets 配置

### 软约束
1. 用户要求尽可能高频（官翻品秒没）
2. 脚本需保持兼容（本地/青龙仍可运行）
3. 状态去重仍需保留

### 方案选择

#### 方案 A: 纯 cron 调度（5 分钟间隔）
- **频率**: 每 5 分钟
- **优点**: 简单，无需外部依赖
- **缺点**: 延迟大（实际可能 6-15 分钟），对抢购不够及时
- **状态持久化**: GitHub Gist 或 Actions Cache

#### 方案 B: repository_dispatch + 外部触发（推荐）
- **频率**: 可达 1 分钟（由 cron-job.org 触发）
- **优点**: 高频、精确、免费
- **缺点**: 需要额外配置外部服务
- **状态持久化**: GitHub Gist API

#### 方案 C: 混合方案
- **频率**: 5 分钟 cron + 外部触发备用
- **优点**: 双保险
- **缺点**: 复杂度高

### 推荐方案: B（repository_dispatch + cron-job.org）

## 需求

### R1: GitHub Actions Workflow
- 创建 `.github/workflows/ricoh-monitor.yml`
- 支持 `repository_dispatch` 和 `workflow_dispatch` 触发
- 备用 cron 调度（每 5 分钟）

### R2: 状态持久化（Gist 方案）
- 创建私有 Gist 存储 `ricoh_monitor_state.json`
- 脚本改造：读写 Gist 替代本地文件
- 需要 `gist` 权限的 PAT

### R3: Secrets 配置
- `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- `RECEIVER_EMAILS`
- `GIST_ID`, `GIST_TOKEN`（用于状态持久化）
- `DISPATCH_TOKEN`（用于 repository_dispatch，需 repo 权限）

### R4: 外部触发配置
- 在 cron-job.org 创建定时任务
- 每 1-2 分钟调用 GitHub API 触发 workflow
- URL: `POST https://api.github.com/repos/{owner}/{repo}/dispatches`

### R5: 脚本兼容性
- 检测运行环境（GitHub Actions vs 本地）
- 本地使用文件状态，Actions 使用 Gist
- 保持 `--loop` 模式可用

## 成功判据

1. GitHub Actions 每 1-2 分钟触发一次监控
2. 状态正确持久化到 Gist，不重复通知
3. 检测到上新后邮件通知延迟 < 2 分钟
4. 本地/青龙运行不受影响

## 实施依赖

### 外部服务
- cron-job.org 账号（免费）
- GitHub Gist（免费）
- GitHub Personal Access Token（需 `repo` + `gist` 权限）

### 文件变更
1. `ricoh_email_monitor.py` - 添加 Gist 状态读写
2. `.github/workflows/ricoh-monitor.yml` - 新增
3. `README.md` - 部署说明（可选）
