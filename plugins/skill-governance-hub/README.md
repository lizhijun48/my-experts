# 技能治理中枢 · Skill Governance Hub

| 项目 | 值 |
|---|---|
| 版本 | 1.0.0 |

技能与专家包的**全生命周期管家**。合并自四个元能力 Agent，功能全提取后原件已清理。

## 生命周期七段

```
找（四层检索）→ 判（值不值得做）→ 造（创作流程）→ 验（静态闸门）→ 测（行为压测）→ 治（五表登记）→ 引（外部资源接口）
```

## 目录结构

```
.codebuddy-plugin/plugin.json          注册（expertType=agent）
agents/skill-governance-hub.md         调度提示词（九章：定位/资产分派/路由/纪律/治理编排/外部引入/边界/交接/首进行为）
avatars/expert.png                     头像 512×512
references/                            9 份规范知识（按需读，非常驻）
  platform-hard-constraints.md           平台硬约束速查（S7/G9b/G12/G13/G14/G15/F12/S4）
  acceptance-standard.md                 四维标准 + 总闸门 + H1/H2/H3 验收
  three-gate-pipeline.md                 三关流水线 + 素材纪律 + 四层副本同步
  expert-package-config.md               专家包配置（agent 必填 5 项 / zip 两套形态 / 头像）
  testing-and-convergence.md             调试测试 + 检查器铁律 + 两类收敛
  audit-checklist.md                     体检 11 项 + 资产冻结纪律
  output-and-boundary.md                 输出规范 + 不做什么 + 知识边界降级
  operation-gates.md                     三态闸口 + 版本备份 + 迭代纪律 + 被审内容安全
  search-and-dispatch.md                 需求分流与推荐模板
skills/                                5 个内置技能（随包分发，无需另装）
  platform-capability-search/            找：四层能力检索（+4 references）
  platform-new-arrivals/                 引：平台新品发现（+pull_market.py）
  skill-authoring/                       判·造：融合技能（10 references + 5 scripts）
  skill-quality-audit/                   验：静态体检 + audit.py 唯一硬闸门
  expert-skill-qa-loop/                  测：行为层压力测试
```

## 三个关键设计

**1. 单一闸门不重复造**
静态结论只认 `skill-quality-audit/scripts/audit.py` 的退出码（0 通过 / 1 必修项 / 2 用法或环境错误）。其余位置一律改为引用，不实现第二套校验器。

**2. 融合而非并列（取两家之长）**
`skill-authoring` 由两份来源合并：
- 取自「技能开发大厂标准」：5 大铁律、Step 0–7、Step 4.5 收敛关卡、H3 A/B ≥20%
- 取自「Skill 制作方法」：三态确认闸口、`skill_ops.py` 确定性操作、环境就绪路由、五阶段自检

并修掉源包一处平台级缺陷：`assets/dependency-kit/` 为三级目录（触发 S7 目录层级超限），已扁平化到 `scripts/`。

**3. 治理是交付的一部分**
定稿不等于完成。必须按 agent 提示词第五节做五表同步（编号 / 目录 / 变更 / 决策 / 来源），否则视为「有技能但查不到」的悬空状态。

## 外部资源引入

G 类请求**必须先出「外部资源引入请求」卡片并取得确认**，再走四道闸：评估（S-072 八镜头）→ 核验（许可证 + preflight）→ 提取（S-025，取方法不取原文）→ 登记（SOURCE-REGISTRY + 五表）。

红线：**绝不自动安装**；绝不复制第三方包体充当自建；融合完成后原件按「功能全提取即删除」清理。

## 与 `suite-dispatcher` 的分工

| 专家 | 侧 | 干什么 |
|---|---|---|
| `suite-dispatcher` | 消费侧（用） | 按业务流程把任务路由到 139 个自建技能 |
| `skill-governance-hub`（本专家） | 供给侧（造、治） | 判定 → 创作 → 验证 → 登记 → 外部引入 |

## 来源与致谢

合并自 `skill-finder`（四层检索逻辑）、`baixiaosheng`（能力配齐与分流模板）、`skill-dev-advisor`（规范流程、平台硬约束实测、`audit.py`）、`skill-smith`（三态闸口、`skill_ops.py`、审查标准）。四个源插件在功能提取完成后已从本地清理，原件备份于工作区。
