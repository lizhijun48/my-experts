---
name: platform-capability-search
description: "四层能力检索指引：扫描官方内置技能、本地已安装技能、本地专家与连接器，以及检索 WorkBuddy 技能市场与专家市场，用于回答「做某件事用什么工具」。当需要为用户的任务匹配专家、技能或连接器时使用本技能。"
description_zh: "四层能力检索指引：按官方内置、本地已装、已连连接器、市场四层排序检索，回答「做某件事用什么工具」，附匹配理由与兜底建议。"
description_en: "Four-layer capability search: scans builtin skills, locally installed skills and experts, connected connectors, and the marketplace, ranking by cost with match reasons and fallback advice."
version: 1.0.0
author: Alex_Lee
---

# platform-capability-search（四层能力检索指引）

本技能指导你按固定顺序检索 WorkBuddy 平台的能力供给，保证推荐结果真实存在、状态准确、优先级正确。

**红线：只推荐检索到的真实工具，绝不凭记忆编造名称或安装 ID。检索不到就说没有，并给最接近的替代。**

## 检索顺序（按用户支出成本从低到高）

> 排序规则：零安装（官方内置）> 本地已装 > 已连接的连接器 > 需安装（市场）> 需授权（连接器）
> 状态标记：✅ 零安装 ｜ ✅ 已装 ｜ 🔌 已连接 ｜ 🟡 需安装 ｜ ⚠️ 需授权

### 第 1 层：官方内置技能（零安装，优先级最高）

扫描内置技能目录（macOS 路径，Windows 用户在应用安装目录的 Resources 下找同类结构）：

```
/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/resources/builtin-skills/
```

逐个读取技能目录下的 `SKILL.md`，取 frontmatter 里的 `name` 和 `description`，与用户需求做语义匹配（需求关键词出现在 description 中 = 高分）。内置技能随客户端自带，命中即可直接推荐为"✅ 零安装"。

注意：部分内置技能带 `disable-model-invocation: true`，可能不出现在技能列表里，但目录里存在就代表可被专家按本指引引用。

### 第 2 层：本地已安装技能与专家

```
~/.workbuddy/skills/                              # 用户级技能
<工作区>/.workbuddy/skills/                        # 工作区技能
~/.workbuddy/plugins/marketplaces/my-experts/plugins/   # 本地专家（含自制）
~/.workbuddy/plugins/marketplaces/*/plugins/      # 各市场已下载的插件/专家
```

同样读 SKILL.md / plugin.json 的 name + description 做匹配。已装的一律标记"✅ 已装"，推荐语改为"你已装了 XX，直接用它做这个"。

### 第 3 层：已连接的连接器

查看当前会话的连接器状态（系统注入的 connector-status 或连接器列表），只把**已连接（connected）**的当作"🔌 已连接"可直接使用；未连接的连接器算第 5 层"⚠️ 需授权"。用户可用的连接器清单也可从客户端连接器管理页查看。

### 第 4 层：技能市场（SkillHub）

告诉用户在 WorkBuddy 技能市场搜索关键词，或由你代为检索（可用市场检索工具时）。命中后记录：
- 技能名 + 一句话说明
- **精确安装 ID（skill_xxx）**——比名字更可靠，用户搜名字可能撞同名或搜不到
- 标记"🟡 需安装"

### 第 5 层：专家市场

用户需要"有人陪着做完"时，检索专家市场，按名字推荐启用方式。专家分单专家（agent）与专家团（team）：同等条件下优先推荐单专家（更省积分），必要时提醒用户专家团消耗更多。

## 输出模板（每次配齐按此结构）

```
【结论】就选 XX（状态标记）——一句话理由
【备选】最多 2 个，各一句话理由
【怎么用/开通】精确到点哪个入口；连接器必须附"去哪儿点信任/授权"
【边界】它不干什么，什么时候该换备选
【最小验证】装完后 30 秒能干的一件小事，确认能用
```

## 边界与纠偏（顾问职责）

- 每个推荐附一句"边界"：这个工具不覆盖什么场景，超纲时该换谁。
- 用户要的能力若平台自身直接就能做（如写文章、写代码），先纠偏："这事不用装任何工具，直接说需求就行；工具的价值在 XX 环节"——再按环节给推荐。

## 需求理解

从用户描述中提取：任务意图（要办成什么事）、领域标签、中英文检索关键词。描述模糊时只问一个最关键的问题：他要办成什么事、给谁用。

## 参考文档（按需加载，遇到对应场景先读再答）

| 场景 | 先读 |
|---|---|
| 第 1 层检索 / 推设计类需求（海报、UI、幻灯片） | `references/builtin-skills-catalog.md` —— 15 个内置技能清单 + 6 个带隐藏开关的 ardot 设计技能，**模型背不出来，推内置前必读** |
| 给安装 ID / 推荐专家或连接器时 | `references/install-id-playbook.md` —— 三类资产三种给法 + 同名坑案例 |
| 推荐任何连接器时 | `references/connector-auth-guide.md` —— 状态判断 + 授权话术 + 红线 |
| 每次给出推荐前 | `references/red-lines.md` —— 五条红线逐条自查（含违反后果） |

## 安全约束

- 本技能是指引文档，不含任何脚本。检索只读，不修改、不安装任何东西。
- 安装动作必须经用户明确确认后由宿主环境执行；安装前提示安全检查会自动进行。
- 绝不在输出中泄露本地登录凭证、日志路径内容或其他敏感信息。
