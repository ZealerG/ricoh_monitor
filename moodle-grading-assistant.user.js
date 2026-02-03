// ==UserScript==
// @name         Moodle作业批改助手
// @namespace    http://tampermonkey.net/
// @version      1.0.0
// @description  自动化Moodle作业批改流程：根据提交时间自动计算分数、快捷键支持、作业切换
// @author       Your Name
// @match        https://moodle.maynoothuniversity.ie/mod/assign/view.php*
// @match        https://moodle.maynoothuniversity.ie/course/view.php*
// @grant        none
// @run-at       document-end
// ==/UserScript==

(function() {
    'use strict';

    // 防止重复初始化
    if (window.__moodleGradingAssistantInitialized) {
        console.log('[Moodle助手] 脚本已初始化，跳过重复执行');
        return;
    }
    window.__moodleGradingAssistantInitialized = false;

    // 配置项
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
        SHORTCUT_KEY: 'Enter', // Ctrl+Enter
        SHORTCUT_MODIFIER: 'ctrlKey',
        // LocalStorage键名
        STORAGE_KEY: 'moodle_homework_id_mapping',
        AUTO_GRADING_KEY: 'moodle_auto_grading_active'
    };

    /**
     * 设置自动批改状态
     */
    function setAutoGrading(active) {
        localStorage.setItem(CONFIG.AUTO_GRADING_KEY, active ? 'true' : 'false');
    }

    /**
     * 获取自动批改状态
     */
    function isAutoGrading() {
        return localStorage.getItem(CONFIG.AUTO_GRADING_KEY) === 'true';
    }

    /**
     * 停止自动批改
     */
    function stopAutoGrading() {
        setAutoGrading(false);
        console.log('[Moodle助手] 自动批改已停止');
    }

    /**
     * 启动自动批改所有学生
     */
    function startAutoGrading() {
        setAutoGrading(true);
        console.log('[Moodle助手] 启动自动批改模式');
        autoGradeSilent();
    }

    /**
     * 获取作业ID映射（从localStorage）
     * @returns {Object} - {homework8: '1005220', homework9: '1005221', ...}
     */
    function getHomeworkIdMapping() {
        try {
            const stored = localStorage.getItem(CONFIG.STORAGE_KEY);
            return stored ? JSON.parse(stored) : {};
        } catch (e) {
            console.error('[Moodle助手] 读取ID映射失败:', e);
            return {};
        }
    }

    /**
     * 保存作业ID映射到localStorage
     * @param {Object} mapping - 映射对象
     */
    function saveHomeworkIdMapping(mapping) {
        try {
            localStorage.setItem(CONFIG.STORAGE_KEY, JSON.stringify(mapping));
            console.log('[Moodle助手] ID映射已保存:', mapping);
        } catch (e) {
            console.error('[Moodle助手] 保存ID映射失败:', e);
        }
    }

    /**
     * 记录当前作业的ID
     */
    function recordCurrentHomeworkId() {
        const homework = getCurrentHomework();
        const urlParams = new URLSearchParams(window.location.search);
        const assignId = urlParams.get('id');

        if (!homework || !assignId) {
            alert('无法识别当前作业或ID');
            return;
        }

        const mapping = getHomeworkIdMapping();
        mapping[homework] = assignId;
        saveHomeworkIdMapping(mapping);

        alert(`已记录: ${homework} -> ID ${assignId}`);
    }

    /**
     * 解析提交时间文本，提取天数
     * @param {string} text - 例如："Assignment was submitted 52 days 21 hours early" 或 "Assignment is overdue by: 7 days 13 hours" 或 "Assignment was submitted 4 days 5 hours late"
     * @returns {number|null} - 提前提交的天数（正数）或逾期天数（负数），如果解析失败返回null
     */
    function parseSubmissionDays(text) {
        if (!text) return null;

        // 检测是否逾期提交 - 格式1: "Assignment is overdue by: 7 days 13 hours"
        if (text.includes('overdue')) {
            const match = text.match(/overdue by:\s*(\d+)\s+days?/i);
            if (match && match[1]) {
                // 逾期返回负数
                return -parseInt(match[1], 10);
            }
            // 默认逾期，返回-1
            return -1;
        }

        // 检测逾期提交 - 格式2: "Assignment was submitted 4 days 5 hours late"
        if (text.includes('late')) {
            const match = text.match(/(\d+)\s+days?.*late/i);
            if (match && match[1]) {
                // 逾期返回负数
                return -parseInt(match[1], 10);
            }
            // 默认逾期，返回-1
            return -1;
        }

        // 检测提前提交
        if (text.includes('early')) {
            const match = text.match(/(\d+)\s+days?/i);
            if (match && match[1]) {
                return parseInt(match[1], 10);
            }
        }

        // 如果只有小时，视为0天
        if (text.includes('hours') && !text.includes('days')) {
            return 0;
        }

        return null;
    }

    /**
     * 根据提交天数计算分数
     * @param {number} days - 提前提交的天数
     * @returns {number} - 计算出的分数
     */
    function calculateScore(days) {
        for (const rule of CONFIG.SCORE_RULES) {
            if (days >= rule.minDays) {
                return rule.score;
            }
        }
        return CONFIG.SCORE_RULES[CONFIG.SCORE_RULES.length - 1].score;
    }

    /**
     * 获取当前页面的提交时间信息
     * @returns {Object|null} - {text: string, days: number, score: number}
     */
    function getSubmissionInfo() {
        // 查找提交时间元素（包括提前提交、逾期提交、按时提交）
        const submissionElement = document.querySelector('.earlysubmission, .latesubmission, .ontime, .overdue');
        console.log('[Moodle助手] 查找提交时间元素:', submissionElement);

        if (!submissionElement) {
            console.log('[Moodle助手] 未找到提交时间信息');
            return null;
        }

        const text = submissionElement.textContent.trim();
        console.log('[Moodle助手] 提交时间文本:', text);

        const days = parseSubmissionDays(text);

        if (days === null) {
            console.log('[Moodle助手] 无法解析提交天数:', text);
            return null;
        }

        const score = calculateScore(days);
        console.log('[Moodle助手] 计算结果 - 天数:', days, '分数:', score);

        return { text, days, score };
    }

    /**
     * 自动填充分数到输入框
     * @param {number} score - 要填充的分数
     */
    function fillGrade(score) {
        const gradeInput = document.querySelector('input[name="grade"]');
        if (!gradeInput) {
            console.error('[Moodle助手] 未找到分数输入框');
            return false;
        }

        gradeInput.value = score.toFixed(2);
        gradeInput.dispatchEvent(new Event('input', { bubbles: true }));
        gradeInput.dispatchEvent(new Event('change', { bubbles: true }));

        console.log(`[Moodle助手] 已填充分数: ${score}`);
        return true;
    }

    /**
     * 点击"保存并显示下一个"按钮
     */
    function clickSaveAndNext() {
        const saveButton = document.querySelector('button[name="saveandshownext"]');
        if (!saveButton) {
            console.error('[Moodle助手] 未找到"保存并显示下一个"按钮');
            return false;
        }

        saveButton.click();
        console.log('[Moodle助手] 已点击"保存并显示下一个"');
        return true;
    }

    /**
     * 自动评分（无确认，用于自动批改）
     */
    function autoGradeSilent() {
        console.log('[Moodle助手] autoGradeSilent 被调用');
        const info = getSubmissionInfo();
        if (!info) {
            console.log('[Moodle助手] 无法获取提交信息，可能已批改完所有学生');
            stopAutoGrading();
            alert('自动批改已完成！\n\n可能所有学生都已批改完成，或者无法获取更多学生信息。');
            return false;
        }

        console.log('[Moodle助手] 自动批改 - 天数:', info.days, '分数:', info.score);
        fillGrade(info.score);
        setTimeout(() => clickSaveAndNext(), 300);
        return true;
    }

    /**
     * 一键自动评分（填分+提交，带确认）
     */
    function autoGrade() {
        const info = getSubmissionInfo();
        if (!info) {
            alert('无法获取提交时间信息，可能已批改完所有学生');
            return;
        }

        fillGrade(info.score);
        setTimeout(() => clickSaveAndNext(), 300);
    }

    /**
     * 检查是否所有学生都已批改完成
     * @returns {boolean}
     */
    function isAllGraded() {
        // 使用文本内容检查
        const headings = document.querySelectorAll('h3');
        for (const h of headings) {
            if (h.textContent.includes('No users selected')) {
                console.log('[Moodle助手] 找到"No users selected"标记');
                return true;
            }
        }
        return false;
    }

    /**
     * 从当前页面查找所有homework及其ID
     * @returns {Array} - [{name: 'homework8', id: '1005220', url: '...'}, ...]
     */
    function findAllHomeworks() {
        const homeworks = [];
        const links = document.querySelectorAll('a');

        for (const link of links) {
            const text = link.textContent.toLowerCase();
            const match = text.match(/homework(\d+)/);
            if (match) {
                const name = `homework${match[1]}`;
                const urlMatch = link.href.match(/id=(\d+)/);
                const id = urlMatch ? urlMatch[1] : null;
                homeworks.push({
                    name: name,
                    id: id,
                    url: link.href
                });
            }
        }

        // 按作业编号排序
        homeworks.sort((a, b) => {
            const aNum = parseInt(a.name.replace('homework', ''));
            const bNum = parseInt(b.name.replace('homework', ''));
            return aNum - bNum;
        });

        console.log('[Moodle助手] 找到的作业列表:', homeworks);
        return homeworks;
    }

    /**
     * 获取当前作业名称
     * @returns {string|null}
     */
    function getCurrentHomework() {
        // 从URL参数中获取当前作业ID
        const urlParams = new URLSearchParams(window.location.search);
        const currentId = urlParams.get('id');

        // 如果没有ID，尝试从链接中查找
        const assignmentLink = document.querySelector('a[title^="Assignment: homework"]');
        if (assignmentLink) {
            const match = assignmentLink.title.match(/Assignment:\s*(homework\d+)/i);
            if (match) {
                console.log('[Moodle助手] 识别到作业:', match[1].toLowerCase());
                return match[1].toLowerCase();
            }
        }

        // 从页面所有homework中查找匹配ID的
        if (currentId) {
            const homeworks = findAllHomeworks();
            for (const hw of homeworks) {
                if (hw.id === currentId) {
                    console.log('[Moodle助手] 通过ID识别到作业:', hw.name);
                    return hw.name;
                }
            }
        }

        // 备用方案：尝试从页面其他位置查找
        const allLinks = document.querySelectorAll('a');
        for (const link of allLinks) {
            const text = link.textContent.toLowerCase();
            const match = text.match(/homework(\d+)/);
            if (match) {
                const homework = `homework${match[1]}`;
                console.log('[Moodle助手] 从链接文本识别到作业:', homework);
                return homework;
            }
        }

        console.log('[Moodle助手] 无法识别当前作业');
        return null;
    }

    /**
     * 切换到下一个作业
     */
    function switchToNextHomework() {
        const current = getCurrentHomework();
        if (!current) {
            alert('无法识别当前作业，请手动切换');
            return;
        }

        const currentIndex = CONFIG.HOMEWORK_LIST.indexOf(current);
        if (currentIndex === -1) {
            alert(`当前作业 ${current} 不在配置列表中`);
            return;
        }

        if (currentIndex >= CONFIG.HOMEWORK_LIST.length - 1) {
            alert('已经是最后一个作业了！');
            return;
        }

        const nextHomework = CONFIG.HOMEWORK_LIST[currentIndex + 1];
        const mapping = getHomeworkIdMapping();
        const nextId = mapping[nextHomework];

        if (!nextId) {
            alert(`未找到 ${nextHomework} 的ID映射\n\n请先访问该作业页面，脚本会自动记录ID`);
            return;
        }

        // 构建下一个作业的URL
        const urlParams = new URLSearchParams(window.location.search);
        urlParams.set('id', nextId);
        // 重置userid参数，让系统自动跳转到第一个学生
        urlParams.delete('userid');

        const nextUrl = `${window.location.origin}${window.location.pathname}?${urlParams.toString()}`;

        if (confirm(`即将切换到: ${nextHomework}\n\n确认跳转？`)) {
            window.location.href = nextUrl;
        }
    }

    /**
     * 查找分数输入框（支持多种选择器）
     * @returns {HTMLElement|null}
     */
    function findGradeInput() {
        const selectors = [
            'input[name="grade"]#id_grade',
            'input[name="grade"]',
            'input[id*="grade"]',
            'input[type="text"][name*="grade"]',
            '#id_grade'
        ];

        for (const selector of selectors) {
            const element = document.querySelector(selector);
            if (element) {
                console.log(`[Moodle助手] 找到分数输入框，选择器: ${selector}`, element);
                return element;
            }
        }

        // 尝试在iframe中查找
        const iframes = document.querySelectorAll('iframe');
        for (const iframe of iframes) {
            try {
                const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                for (const selector of selectors) {
                    const element = iframeDoc.querySelector(selector);
                    if (element) {
                        console.log(`[Moodle助手] 在iframe中找到分数输入框，选择器: ${selector}`, element);
                        return element;
                    }
                }
            } catch (e) {
                // 跨域iframe无法访问
            }
        }

        return null;
    }

    /**
     * 创建UI控制面板
     */
    function createControlPanel() {
        const gradeInput = findGradeInput();

        if (!gradeInput) {
            console.log('[Moodle助手] 未找到分数输入框，控制面板不创建');
            console.log('[Moodle助手] 页面上所有input元素:', document.querySelectorAll('input'));
            return false;
        }

        // 移除旧的控制面板（如果存在）
        const oldPanel = document.getElementById('moodle-grading-assistant');
        if (oldPanel) {
            oldPanel.remove();
            console.log('[Moodle助手] 移除旧的控制面板');
        }

        const panel = document.createElement('div');
        panel.id = 'moodle-grading-assistant';
        panel.style.cssText = `
            position: fixed;
            bottom: 20px;
            left: 20px;
            background: #fff;
            border: 2px solid #0066cc;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 99999;
            min-width: 250px;
            max-height: 400px;
            overflow-y: auto;
            font-family: Arial, sans-serif;
        `;

        // 获取提交信息
        const info = getSubmissionInfo();
        const autoGrading = isAutoGrading();

        panel.innerHTML = `
            <div style="margin-bottom: 10px;">
                <h3 style="margin: 0 0 10px 0; color: ${autoGrading ? '#ff6600' : '#0066cc'}; font-size: 16px;">
                    ${autoGrading ? '🤖 自动批改中...' : '📝 批改助手'}
                </h3>
                ${info ? `
                    <div style="font-size: 13px; margin-bottom: 8px; padding: 8px; background: #f0f8ff; border-radius: 4px;">
                        <div><strong>提交时间:</strong> ${info.days}天前</div>
                        <div><strong>建议分数:</strong> <span style="color: #00aa00; font-size: 16px; font-weight: bold;">${info.score}</span></div>
                    </div>
                ` : `
                    <div style="font-size: 13px; color: #cc0000; margin-bottom: 8px;">
                        ⚠️ 未找到提交时间信息
                    </div>
                `}
            </div>
            ${autoGrading ? `
                <button id="stop-auto-btn" style="
                    width: 100%;
                    padding: 10px;
                    background: #dc3545;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 14px;
                    font-weight: bold;
                    margin-bottom: 8px;
                ">
                    🛑 停止自动批改
                </button>
            ` : `
                <button id="auto-grade-all-btn" style="
                    width: 100%;
                    padding: 10px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 14px;
                    font-weight: bold;
                    margin-bottom: 8px;
                ">
                    🚀 自动批改所有学生
                </button>
                <button id="auto-grade-btn" style="
                    width: 100%;
                    padding: 8px;
                    background: #0066cc;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 13px;
                    margin-bottom: 8px;
                ">
                    ✏️ 评分并跳转下一个
                </button>
            `}
            <button id="fill-grade-btn" style="
                width: 100%;
                padding: 8px;
                background: #28a745;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 13px;
                margin-bottom: 8px;
            ">
                ✏️ 仅填充分数
            </button>
            <button id="next-homework-btn" style="
                width: 100%;
                padding: 8px;
                background: #ffc107;
                color: #333;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 13px;
                margin-bottom: 8px;
            ">
                ➡️ 切换到下一个作业
            </button>
            <button id="show-mapping-btn" style="
                width: 100%;
                padding: 6px;
                background: #6c757d;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
            ">
                ⚙️ 查看ID映射
            </button>
            <div style="margin-top: 10px; font-size: 11px; color: #666; text-align: center;">
                快捷键: Ctrl+Enter
            </div>
        `;

        document.body.appendChild(panel);

        // 绑定按钮事件 - 使用panel.querySelector确保选择正确的元素
        const stopBtn = panel.querySelector('#stop-auto-btn');
        const autoGradeAllBtn = panel.querySelector('#auto-grade-all-btn');
        const autoGradeBtn = panel.querySelector('#auto-grade-btn');
        const fillGradeBtn = panel.querySelector('#fill-grade-btn');
        const nextHomeworkBtn = panel.querySelector('#next-homework-btn');
        const showMappingBtn = panel.querySelector('#show-mapping-btn');

        console.log('[Moodle助手] 绑定按钮事件...', {
            stopBtn: !!stopBtn,
            autoGradeAllBtn: !!autoGradeAllBtn,
            autoGradeBtn: !!autoGradeBtn,
            fillGradeBtn: !!fillGradeBtn,
            nextHomeworkBtn: !!nextHomeworkBtn,
            showMappingBtn: !!showMappingBtn
        });

        if (autoGrading && stopBtn) {
            stopBtn.addEventListener('click', () => {
                console.log('[Moodle助手] 停止按钮被点击');
                stopAutoGrading();
                alert('自动批改已停止');
                location.reload();
            });
        } else if (!autoGrading) {
            if (autoGradeAllBtn) {
                autoGradeAllBtn.addEventListener('click', () => {
                    console.log('[Moodle助手] 自动批改按钮被点击');
                    // 直接开始自动批改，不需要确认
                    console.log('[Moodle助手] 启动自动批改模式...');
                    setAutoGrading(true);
                    // 刷新面板显示停止按钮
                    createControlPanel();
                    // 开始批改第一个学生
                    setTimeout(() => autoGradeSilent(), 500);
                });
            }

            if (autoGradeBtn) {
                autoGradeBtn.addEventListener('click', () => {
                    console.log('[Moodle助手] 评分按钮被点击');
                    autoGrade();
                });
            }
        }

        if (fillGradeBtn) {
            fillGradeBtn.addEventListener('click', () => {
                console.log('[Moodle助手] 填充分数按钮被点击');
                // 重新获取最新的提交信息
                const currentInfo = getSubmissionInfo();
                if (currentInfo) {
                    fillGrade(currentInfo.score);
                } else {
                    alert('无法获取提交时间信息');
                }
            });
        }

        if (nextHomeworkBtn) {
            nextHomeworkBtn.addEventListener('click', () => {
                console.log('[Moodle助手] 切换作业按钮被点击');
                switchToNextHomework();
            });
        }

        if (showMappingBtn) {
            showMappingBtn.addEventListener('click', () => {
                const mapping = getHomeworkIdMapping();
                const mappingText = Object.keys(mapping).length > 0
                    ? Object.entries(mapping).map(([hw, id]) => `${hw}: ${id}`).join('\n')
                    : '暂无ID映射记录';
                alert(`作业ID映射:\n\n${mappingText}\n\n脚本会在访问作业时自动记录ID`);
            });
        }

        console.log('[Moodle助手] 控制面板已创建');
        return true;
    }

    /**
     * 等待评分表单加载完成后创建控制面板
     */
    function waitForGradeForm() {
        console.log('[Moodle助手] 等待评分表单加载...');

        // 检查是否没有选择学生（没有userid参数）
        const urlParams = new URLSearchParams(window.location.search);
        if (!urlParams.get('userid')) {
            console.log('[Moodle助手] 没有userid，尝试自动选择第一个学生...');

            // 查找"Grade"按钮（批改按钮）
            const gradeButtons = document.querySelectorAll('a[href*="action=grader"]');
            if (gradeButtons.length > 0) {
                console.log(`[Moodle助手] 找到 ${gradeButtons.length} 个学生，点击第一个...`);
                gradeButtons[0].click();
                return;
            }

            // 备用方案：查找包含"Grade"文本的链接
            const allLinks = document.querySelectorAll('a');
            for (const link of allLinks) {
                if (link.href.includes('action=grader') && link.href.includes('userid=')) {
                    console.log('[Moodle助手] 找到批改链接，点击...');
                    link.click();
                    return;
                }
            }

            console.log('[Moodle助手] 未找到可批改的学生');
        }

        // 首先检查是否所有学生都已批改完成
        if (isAllGraded()) {
            console.log('[Moodle助手] 检测到"No users selected"，当前作业批改完成');
            stopAutoGrading();

            // 查找下一个作业
            const homeworks = findAllHomeworks();
            const current = getCurrentHomework();
            const currentNum = current ? parseInt(current.replace('homework', '')) : 0;

            // 从localStorage获取所有作业ID
            const mapping = getHomeworkIdMapping();
            const allHomeworks = Object.entries(mapping)
                .map(([name, id]) => ({ name, id, url: `https://moodle.maynoothuniversity.ie/mod/assign/view.php?id=${id}` }))
                .sort((a, b) => {
                    const aNum = parseInt(a.name.replace('homework', ''));
                    const bNum = parseInt(b.name.replace('homework', ''));
                    return aNum - bNum;
                });

            // 找到下一个作业
            const nextHomework = allHomeworks.find(hw => {
                const hwNum = parseInt(hw.name.replace('homework', ''));
                return hwNum > currentNum;
            });

            if (nextHomework) {
                console.log('[Moodle助手] 找到下一个作业:', nextHomework.name);
                alert(`当前作业批改完成！\n\n即将切换到: ${nextHomework.name}\n\n自动批改将继续...`);

                // 构建批改页面的URL
                let nextUrl = nextHomework.url;
                if (nextUrl.includes('?')) {
                    nextUrl += '&action=grader';
                } else {
                    nextUrl += '?action=grader';
                }

                console.log('[Moodle助手] 跳转到:', nextUrl);
                window.location.href = nextUrl;
                return;
            } else {
                alert('所有作业批改完成！');
                return;
            }
        }

        // 首先尝试直接查找
        const gradeInput = findGradeInput();
        if (gradeInput) {
            console.log('[Moodle助手] 评分表单已存在，直接创建控制面板');
            createControlPanel();
            // 如果正在自动批改，继续执行
            if (isAutoGrading()) {
                console.log('[Moodle助手] 继续自动批改...');
                setTimeout(() => autoGradeSilent(), 800);
            }
            return;
        }

        let checkCount = 0;
        const maxChecks = 60; // 最多检查60次（每次1秒）

        // 使用定时器定期检查（更可靠）
        const checkInterval = setInterval(() => {
            checkCount++;

            // 每次检查时也检查是否所有学生已批改完成
            if (isAllGraded()) {
                clearInterval(checkInterval);
                console.log('[Moodle助手] 检测到"No users selected"，当前作业批改完成');
                stopAutoGrading();

                const current = getCurrentHomework();
                const currentNum = current ? parseInt(current.replace('homework', '')) : 0;
                console.log('[Moodle助手] 当前作业:', current, '编号:', currentNum);

                // 从localStorage获取所有作业ID
                const mapping = getHomeworkIdMapping();
                console.log('[Moodle助手] localStorage中的作业映射:', mapping);

                const allHomeworks = Object.entries(mapping)
                    .map(([name, id]) => ({ name, id, url: `https://moodle.maynoothuniversity.ie/mod/assign/view.php?id=${id}` }))
                    .sort((a, b) => {
                        const aNum = parseInt(a.name.replace('homework', ''));
                        const bNum = parseInt(b.name.replace('homework', ''));
                        return aNum - bNum;
                    });

                console.log('[Moodle助手] 所有作业列表:', allHomeworks);

                // 找到下一个作业
                const nextHomework = allHomeworks.find(hw => {
                    const hwNum = parseInt(hw.name.replace('homework', ''));
                    return hwNum > currentNum;
                });

                console.log('[Moodle助手] 下一个作业:', nextHomework);

                if (nextHomework) {
                    console.log('[Moodle助手] 找到下一个作业:', nextHomework.name);
                    alert(`当前作业批改完成！\n\n即将切换到: ${nextHomework.name}\n\n自动批改将继续...`);

                    // 构建批改页面的URL
                    let nextUrl = nextHomework.url;
                    if (nextUrl.includes('?')) {
                        nextUrl += '&action=grader';
                    } else {
                        nextUrl += '?action=grader';
                    }

                    console.log('[Moodle助手] 跳转到:', nextUrl);
                    window.location.href = nextUrl;
                } else {
                    alert('所有作业批改完成！');
                }
                return;
            }

            console.log(`[Moodle助手] 正在查找评分表单... (${checkCount}/${maxChecks})`);

            const gradeInput = findGradeInput();
            if (gradeInput) {
                clearInterval(checkInterval);
                console.log('[Moodle助手] 检测到评分表单已加载，创建控制面板');
                createControlPanel();
                // 如果正在自动批改，继续执行
                if (isAutoGrading()) {
                    console.log('[Moodle助手] 继续自动批改...');
                    setTimeout(() => autoGradeSilent(), 800);
                }
            } else if (checkCount >= maxChecks) {
                clearInterval(checkInterval);
                console.log('[Moodle助手] 等待评分表单超时（60秒）');
                console.log('[Moodle助手] 当前页面的input数量:', document.querySelectorAll('input').length);
            }
        }, 1000);
    }

    /**
     * 注册快捷键
     */
    function registerShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl+Enter: 自动评分
            if (e[CONFIG.SHORTCUT_MODIFIER] && e.key === CONFIG.SHORTCUT_KEY) {
                e.preventDefault();
                autoGrade();
            }
        });

        console.log('[Moodle助手] 快捷键已注册: Ctrl+Enter');
    }

    /**
     * 从课程页面扫描并保存所有homework的ID
     */
    function scanAndSaveHomeworkIds() {
        console.log('[Moodle助手] 扫描课程页面的homework...');

        const homeworks = findAllHomeworks();
        if (homeworks.length === 0) {
            console.log('[Moodle助手] 未找到任何homework');
            return;
        }

        const mapping = getHomeworkIdMapping();
        let newCount = 0;

        for (const hw of homeworks) {
            if (hw.id && !mapping[hw.name]) {
                mapping[hw.name] = hw.id;
                newCount++;
                console.log(`[Moodle助手] 记录: ${hw.name} -> ID ${hw.id}`);
            }
        }

        if (newCount > 0) {
            saveHomeworkIdMapping(mapping);
            console.log(`[Moodle助手] 成功记录 ${newCount} 个作业ID`);

            // 显示提示
            const mappingText = Object.entries(mapping)
                .sort((a, b) => {
                    const aNum = parseInt(a[0].replace('homework', ''));
                    const bNum = parseInt(b[0].replace('homework', ''));
                    return aNum - bNum;
                })
                .map(([hw, id]) => `${hw}: ${id}`)
                .join('\n');

            alert(`已记录 ${newCount} 个作业ID！\n\n${mappingText}\n\n现在可以开始批改，脚本会自动切换作业。`);
        } else {
            console.log('[Moodle助手] 所有作业ID已记录');
        }
    }

    /**
     * 初始化脚本
     */
    function init() {
        if (window.__moodleGradingAssistantInitialized) {
            console.log('[Moodle助手] 已初始化，跳过');
            return;
        }

        console.log('[Moodle助手] 脚本已加载');

        // 检查是否在课程页面
        if (window.location.pathname.includes('/course/view.php')) {
            console.log('[Moodle助手] 检测到课程页面，扫描homework...');
            window.__moodleGradingAssistantInitialized = true;
            // 延迟执行，确保页面加载完成
            setTimeout(() => scanAndSaveHomeworkIds(), 1000);
            return;
        }

        // 检查是否在批改页面
        const urlParams = new URLSearchParams(window.location.search);
        const action = urlParams.get('action');
        const userid = urlParams.get('userid');

        console.log('[Moodle助手] URL参数 - action:', action, 'userid:', userid);

        if (action !== 'grader') {
            console.log('[Moodle助手] 不在批改页面（action != grader），脚本不执行');
            return;
        }

        if (!userid) {
            console.log('[Moodle助手] 没有userid参数，可能不在学生批改页面');
        }

        window.__moodleGradingAssistantInitialized = true;

        // 自动记录当前作业ID
        const homework = getCurrentHomework();
        const assignId = urlParams.get('id');
        if (homework && assignId) {
            const mapping = getHomeworkIdMapping();
            if (!mapping[homework]) {
                mapping[homework] = assignId;
                saveHomeworkIdMapping(mapping);
                console.log(`[Moodle助手] 自动记录: ${homework} -> ID ${assignId}`);
            }
        }

        // 使用定时器等待评分表单加载
        waitForGradeForm();

        // 注册快捷键
        registerShortcuts();

        console.log('[Moodle助手] 初始化完成');
    }

    // 确保页面完全加载后再初始化
    function tryInit() {
        // 重置初始化标志（允许在页面跳转后重新初始化）
        const currentUrl = location.href;
        if (window.__moodleGradingAssistantLastUrl !== currentUrl) {
            window.__moodleGradingAssistantLastUrl = currentUrl;
            window.__moodleGradingAssistantInitialized = false;
            init();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            setTimeout(tryInit, 500);
        });
    } else {
        setTimeout(tryInit, 500);
    }

    // 监听URL变化（应对Moodle的页面导航）
    let lastUrl = location.href;
    setInterval(() => {
        if (location.href !== lastUrl) {
            lastUrl = location.href;
            console.log('[Moodle助手] 检测到URL变化，重新初始化');
            window.__moodleGradingAssistantInitialized = false;
            setTimeout(init, 1000);
        }
    }, 1000);

})();
