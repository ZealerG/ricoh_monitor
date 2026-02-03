# Moodle作业批改助手 - 使用说明

## 功能概述

这是一个专为Maynooth University Moodle平台设计的油猴脚本，用于自动化作业批改流程。

### 主要功能

1. **自动计算分数**：根据学生提交时间自动计算分数
   - 提前40天及以上：100分
   - 提前20-40天：95分
   - 提前20天以内：90分

2. **快捷键支持**：`Ctrl+Enter` 快速填分并提交

3. **一键评分**：点击按钮自动填充分数并跳转到下一个学生

4. **作业切换**：完成当前作业后自动切换到下一个homework

5. **ID自动记录**：访问作业时自动记录作业ID，方便后续切换

## 安装步骤

### 1. 安装Tampermonkey

- **Chrome/Edge**: 访问 [Chrome Web Store](https://chrome.google.com/webstore/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo)
- **Firefox**: 访问 [Firefox Add-ons](https://addons.mozilla.org/en-US/firefox/addon/tampermonkey/)
- **Safari**: 访问 [App Store](https://apps.apple.com/us/app/tampermonkey/id1482490089)

### 2. 安装脚本

1. 点击浏览器工具栏中的Tampermonkey图标
2. 选择"创建新脚本"
3. 删除默认内容，粘贴 `moodle-grading-assistant.user.js` 的完整代码
4. 按 `Ctrl+S` (或 `Cmd+S`) 保存

### 3. 验证安装

访问任意Moodle作业批改页面（URL包含 `action=grader`），右上角应该会出现"📝 批改助手"面板。

## 使用方法

### 基本流程

1. **登录Moodle**并进入作业批改页面
2. 脚本会自动显示控制面板，包含：
   - 提交时间信息
   - 建议分数
   - 操作按钮

3. **评分方式**（任选其一）：
   - 点击"🚀 一键评分并提交"按钮
   - 按 `Ctrl+Enter` 快捷键
   - 点击"✏️ 仅填充分数"后手动提交

4. **切换作业**：
   - 完成当前作业所有学生后，点击"➡️ 切换到下一个作业"

### 首次使用

首次使用时，需要依次访问每个作业（homework8-14）的批改页面，脚本会自动记录每个作业的ID。之后就可以使用"切换到下一个作业"功能。

### 查看ID映射

点击"⚙️ 查看ID映射"按钮，可以查看已记录的作业ID映射关系。

## 配置说明

如需修改评分规则或作业列表，编辑脚本中的 `CONFIG` 对象：

```javascript
const CONFIG = {
    // 分数规则：提交天数 -> 分数
    SCORE_RULES: [
        { minDays: 40, score: 100 },
        { minDays: 20, score: 95 },
        { minDays: 0, score: 90 }
    ],
    // 需要批改的作业列表（按顺序）
    HOMEWORK_LIST: ['homework8', 'homework9', 'homework10', 'homework11', 'homework12', 'homework13', 'homework14'],
    // 快捷键配置
    SHORTCUT_KEY: 'Enter',
    SHORTCUT_MODIFIER: 'ctrlKey'
};
```

## 常见问题

### Q: 脚本没有显示控制面板？

**A**: 检查以下几点：
- 确认Tampermonkey已启用
- 确认URL包含 `action=grader`（必须在批改页面）
- 按 `F12` 打开开发者工具，查看Console是否有错误信息

### Q: 无法识别提交时间？

**A**: 脚本会在Console中输出调试信息。如果提交时间格式与预期不同，可能需要调整 `parseSubmissionDays` 函数。

### Q: 切换作业时提示"未找到ID映射"？

**A**: 需要先手动访问该作业的批改页面，脚本会自动记录ID。或者点击"⚙️ 查看ID映射"检查已记录的作业。

### Q: 如何修改评分规则？

**A**: 编辑脚本中的 `CONFIG.SCORE_RULES` 数组，按照 `{ minDays: X, score: Y }` 格式添加或修改规则。

### Q: 快捷键冲突怎么办？

**A**: 修改 `CONFIG.SHORTCUT_KEY` 和 `CONFIG.SHORTCUT_MODIFIER`。例如改为 `Alt+S`：
```javascript
SHORTCUT_KEY: 's',
SHORTCUT_MODIFIER: 'altKey'
```

## 技术细节

### 页面元素识别

脚本依赖以下HTML元素：

- **提交时间**: `.earlysubmission`, `.latesubmission`, `.ontime`
- **分数输入框**: `input[name="grade"]#id_grade`
- **提交按钮**: `button[name="saveandshownext"]`
- **作业链接**: `a[title^="Assignment: homework"]`

如果Moodle页面结构发生变化，可能需要更新选择器。

### 数据存储

作业ID映射存储在浏览器的 `localStorage` 中，键名为 `moodle_homework_id_mapping`。清除浏览器数据会导致映射丢失，需要重新访问作业页面记录。

## 更新日志

### v1.0.0 (2026-01-21)
- 初始版本
- 实现自动计算分数功能
- 添加快捷键支持
- 实现作业切换功能
- 添加UI控制面板

## 许可证

本脚本仅供教学辅助使用，请遵守学校相关规定。

## 支持

如有问题或建议，请联系脚本作者。
