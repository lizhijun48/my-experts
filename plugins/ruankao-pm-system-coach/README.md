# 软考项目管理系统教练 (ruankao-pm-system-coach)

合并自三个软考 Agent（保留原件未删，本插件仅新增）：

- `info-project-manager` — 高项（信息系统项目管理师·高级）
- `ruankao-integration-pm-coach` — 中项（系统集成项目管理工程师·中级）
- `gaoxiang-essay-tutor` — 高项论文辅导

## 设计

单一入口，按"考试级别 × 任务类型"路由，避免多 Agent 切换：

| 意图 | 路由 | 复用 |
|---|---|---|
| 高项 综合/案例/计算/知识域 | 通用 PM 体系（高项口径） | `exam-coaching` 资料 |
| 中项 全程备考 | 中项辅导 | `exam-coaching` skill（考纲即中项） |
| 高项 论文 | 阅卷级 75 分制批改 | `gaoxiang-essay-grader` skill |
| 实战 PM | 方法/工具建议 | 通用框架 |

## 目录

- `agents/ruankao-pm-system-coach.md` — 合并后统一提示词（重写式路由，去商业化）
- `skills/exam-coaching/` — 中项备考资料包（考纲/公式/路径模板），原样复用
- `skills/gaoxiang-essay-grader/` — 高项论文评分（含 score_essay.py + rubric.md），原样复用、仅去掉商业档位话术
- `avatars/expert.png` — 头像

categoryId：10-ProjectQuality（核心能力=项目管理/质量保障备考辅导）。
