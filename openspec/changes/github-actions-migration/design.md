# 设计文档：GitHub Actions 迁移

## 技术决策（零决策点）

### 1. 部署架构
```
cron-job.org (每2分钟)
    ↓ POST https://api.github.com/repos/{owner}/{repo}/dispatches
    ↓ Headers: Authorization: Bearer {DISPATCH_TOKEN}
    ↓ Body: {"event_type": "monitor_trigger"}
GitHub Actions (公开仓库，免费无限制)
    ↓ 触发 workflow
    ↓ 1. gh gist view → 读取状态
    ↓ 2. python ricoh_email_monitor.py → 执行监控
    ↓ 3. gh gist edit → 保存状态
GitHub Gist (私有 Gist，状态持久化)
```

### 2. 触发器配置
| 参数 | 值 |
|------|-----|
| 主触发器 | `repository_dispatch` types: `["monitor_trigger"]` |
| 备用触发器 | `workflow_dispatch`（手动测试） |
| 备用 cron | `*/5 * * * *`（每5分钟，作为外部触发失败的兜底） |
| 并发控制 | `concurrency: { group: ricoh-monitor, cancel-in-progress: false }` |

### 3. Secrets 配置
| Secret 名称 | 用途 | 权限要求 |
|-------------|------|----------|
| `GIST_PAT` | 读写状态 Gist | 经典 PAT: `gist` |
| `DISPATCH_TOKEN` | 触发 workflow (cron-job.org 用) | 经典 PAT: `repo` |
| `SMTP_SERVER` | SMTP 服务器 | - |
| `SMTP_PORT` | SMTP 端口 | - |
| `SMTP_USER` | SMTP 用户名 | - |
| `SMTP_PASSWORD` | SMTP 密码 | - |
| `RECEIVER_EMAILS` | 收件人（逗号分隔） | - |

### 4. Gist 状态管理
| 参数 | 值 |
|------|-----|
| Gist 文件名 | `ricoh_monitor_state.json` |
| 读取命令 | `gh gist view $GIST_ID -f ricoh_monitor_state.json` |
| 写入命令 | `gh gist edit $GIST_ID -f ricoh_monitor_state.json ricoh_monitor_state.json` |
| 失败处理 | 读取失败 → 使用空状态；写入失败 → workflow 失败 |

### 5. 脚本改造
| 改造点 | 方案 |
|--------|------|
| 环境检测 | `os.getenv("GITHUB_ACTIONS") == "true"` |
| 状态路径 | Actions 环境用当前目录 `./ricoh_monitor_state.json`（由 workflow 管理 Gist 读写） |
| 配置读取 | 保持环境变量方式，Actions 通过 Secrets 注入 |

### 6. cron-job.org 配置
| 参数 | 值 |
|------|-----|
| URL | `https://api.github.com/repos/{owner}/{repo}/dispatches` |
| Method | POST |
| Headers | `Authorization: Bearer {DISPATCH_TOKEN}`, `Accept: application/vnd.github.v3+json`, `User-Agent: ricoh-monitor-cron` |
| Body | `{"event_type": "monitor_trigger"}` |
| Schedule | Every 2 minutes |
| Failure notification | 启用 |

### 7. 监控与告警
| 场景 | 处理方式 |
|------|----------|
| Workflow 失败 | GitHub 自动邮件通知 (需开启 repo notifications) |
| 连续 403 | 脚本进入冷却期，下次运行自动跳过 |
| Gist 写入失败 | workflow exit code 非 0，触发 GitHub 通知 |
| cron-job.org 调用失败 | cron-job.org 邮件告警 |

## PBT 属性

### P1: 幂等性 - Gist 状态读写往返
- **不变量**: `load(save(state)) == state`
- **伪造策略**: 随机状态，验证 JSON 序列化往返

### P2: 去重正确性
- **不变量**: 已通知 goods_id 在 24h 内不再通知
- **伪造策略**: 模拟重复商品，验证邮件发送次数 ≤ 1

### P3: 并发安全
- **不变量**: 同一时刻最多一个 workflow 运行
- **伪造策略**: 快速连续触发，验证 GitHub 并发组生效

### P4: 配置完整性
- **不变量**: 缺少必需 Secret 时 workflow 明确失败
- **伪造策略**: 删除某 Secret，验证 workflow 报错而非静默失败
