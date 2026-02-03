# 设计文档：理光映像 GR 商品监控脚本改进

## 技术决策（零决策点）

### 1. 反爬策略
| 参数 | 值 | 说明 |
|------|-----|------|
| UA 池大小 | 12 | 桌面浏览器 UA（Chrome/Edge/Firefox，Windows/macOS） |
| UA 轮换策略 | 按任务轮询 | index 持久化到 state |
| Headers 组合 | 完整浏览器头 | Accept, Accept-Language, Accept-Encoding, Connection, Referer, Origin |
| Referer | `https://newsite.ricn-mall.com/` | 指向页面而非 API |
| Session 管理 | `requests.Session()` | 单次任务复用连接 |
| 请求超时 | (5s, 10s) | 连接超时, 读取超时 |
| 分页间隔 | 1.8s ± 0.6s | 页间随机延迟 |

### 2. 频率控制
| 参数 | 值 | 说明 |
|------|-----|------|
| 基础间隔 | 30s | 用户确认 |
| 抖动范围 | 0-5s | 随机附加延迟 |
| Daemon 模式 | `--loop` 参数启用 | 内部 while True + sleep |
| Cron 模式 | 默认 | 运行一次即退出 |

### 3. 重试策略
| 场景 | 策略 | 参数 |
|------|------|------|
| 网络超时/5xx/429 | 指数退避重试 | base=2s, factor=2, max=20s, retries=3, jitter=30% |
| 403 Forbidden | 不重试，进入冷却 | cooldown=6h，连续3次升级到24h |
| SMTP 失败 | 简单重试 | 2次，间隔10s/30s |

### 4. 状态管理
| 字段 | 类型 | 说明 |
|------|------|------|
| version | int | 状态文件版本号，当前=1 |
| last_success_ts | int | 上次成功请求时间戳 |
| last_ids | List[str] | 已通知商品 ID/名称，最多200条 FIFO |
| cooldown_until | int | 403 冷却截止时间戳 |
| ua_index | int | UA 轮换索引 |

**存储路径**:
- 环境变量 `STATE_PATH`，默认 `./ricoh_email_monitor.state.json`
- 云函数回退: `/tmp/ricoh_email_state.json`
- 若不可写: `STATE_BACKEND=none`（接受重复通知风险）

### 5. 邮件通知
| 参数 | 值 |
|------|-----|
| 去重窗口 | 6h（同一商品不重复通知） |
| 收件人 | 环境变量 `RECEIVER_EMAILS`（逗号分隔） |
| 内容增强 | 包含商品详情页链接 |

### 6. 运行入口
```python
# 云函数入口
def handler(event, context):
    return run()

# 本地/青龙入口
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="Daemon mode")
    args = parser.parse_args()
    if args.loop:
        while True:
            run()
            time.sleep(30 + random.randint(0, 5))
    else:
        run()
```

### 7. 环境变量清单
| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| SMTP_SERVER | 是 | - | SMTP 服务器地址 |
| SMTP_PORT | 是 | - | SMTP 端口 |
| SMTP_USER | 是 | - | SMTP 用户名 |
| SMTP_PASSWORD | 是 | - | SMTP 密码 |
| RECEIVER_EMAILS | 是 | - | 收件人（逗号分隔） |
| CID | 否 | 9 | 商品分类 ID |
| KEYWORD | 否 | GR | 匹配关键词 |
| STATE_PATH | 否 | ./ricoh_email_monitor.state.json | 状态文件路径 |
| POLL_INTERVAL | 否 | 30 | 轮询间隔（秒） |

## PBT 属性（Property-Based Testing）

### P1: 幂等性 - 重复运行不重复通知
- **不变量**: 对于相同商品列表，连续调用 `run()` 只发送一次邮件
- **伪造策略**: 模拟 API 返回固定商品列表，验证邮件发送次数 ≤ 1

### P2: 单调性 - 状态时间戳递增
- **不变量**: `last_success_ts` 只增不减
- **伪造策略**: 随机时序调用，验证 state.last_success_ts >= previous

### P3: 边界 - 已通知列表大小有界
- **不变量**: `len(last_ids) <= 200`
- **伪造策略**: 生成超过200个商品，验证列表 FIFO 淘汰

### P4: 往返 - 状态序列化完整
- **不变量**: `load(save(state)) == state`
- **伪造策略**: 随机生成 state，验证 JSON 序列化/反序列化等价

### P5: 冷却单调性 - 403 冷却期内跳过请求
- **不变量**: 当 `time.time() < cooldown_until` 时，不发起 HTTP 请求
- **伪造策略**: 设置 cooldown_until 为未来时间，验证无网络调用

### P6: 通知去重窗口
- **不变量**: 同一商品在 6h 内只发送一次邮件
- **伪造策略**: 模拟短时间内多次检测到同一商品，验证邮件计数

## 风险与缓解

| 风险 | 概率 | 缓解措施 |
|------|------|----------|
| 当前 IP 已被封禁 | 高 | 换 IP 运行（新服务器/云函数） |
| WAF 指纹识别 | 中 | 使用完整 Headers，必要时考虑 cloudscraper |
| API 结构变更 | 低 | 结构校验 + schema_failure 告警 |
| 邮件发送失败 | 低 | 重试 + 下次任务再尝试 |
