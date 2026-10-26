# 专家包配置分支（来源：§七 D 类）

> 本文件由源资产原文程序化提取，保持原样以零信息丢失；口径以原文为准。


## 七、D 类：Expert 专家包配置分支


实证结构（以本专家包为准）：

```
.codebuddy-plugin/plugin.json   # 专家核心配置
agents/{name}.md                # Agent 定义 + 系统提示词
avatars/{name}.png              # 头像，512×512，≤500KB
README.md
```

- **plugin.json 关键字段**：name、expertType、version、description、author、agents、agentName、displayName（zh/en）、profession（zh/en）、displayDescription（zh/en）、avatar、categoryId、defaultInitPrompt、quickPrompts、tags。
- **`agents/{name}.md` 的必填字段集（实测，踩过两轮驳回）**：**不只 `plugin.json` 有必填项**——agent md 也有必填字段集：**`name` / `description` / `displayName` / `profession` / `maxTurns`**。缺任何一个，平台都报 `解析失败：agents/xxx.md: <字段> 字段为必填`。**别只配好 plugin.json 就交付。**
- **agent md 的 frontmatter 同样走严格 YAML 解析**：`---` 成对、空格缩进、值含冒号加双引号、**不得有字面量 `/n`**。团队成员的 `agents/*.md` 属**严格**档，交付前必跑真 YAML 解析关口。
- **平台校验事实（来自真实提交，实测）**：`tags` **必须恰好 3 个**，多一个或少一个都会**解析失败、无法上传**（已在实际提交中复现）。每个 tag 为 `{"en": "...", "zh": "..."}` 对象。给专家包配置 tags 时按 3 个设计，并在交付前数一遍。**其他字段是否有数量限制目前无实测结论，不要臆测**——遇到平台报错时以报错原文为准并反馈给我更新。
- **命名红线（强制）**：展示名称、头衔、描述**只写功能**，不得出现"官方、平台、客服、管理员"等冒充性表述，不得冠平台品牌开头。例：profession 用"技能与专家包开发工程师"，不可用"WorkBuddy官方技能顾问"。
- **描述一致性红线**：displayDescription 不得承诺审核结果或收益（避免"提升一次过审上架率"这类效果承诺，改为描述具体服务内容）。
- **头像规范**：512×512、≤500KB（本包实测 512×512 / 311KB 达标）。**不达标会被驳回或显示异常**；补救：用图像工具 resize 到 512×512 并压缩至 ≤500KB 后重新打包。
- ⭐ **zip 顶层形态有两套，别互套**（实测，全库对照确认）：
  - **单专家（`expertType: agent`）= 裸根**：解压即见 `agents/`、`avatars/`、`references/`、`.codebuddy-plugin/`，**无顶层包名目录**（全库 20+ 一致，含在售 `pcb-rescuer-1.0.1.zip`）；
  - **专家团（`expertType: team`）= 带顶层**：`<包名>/agents/…`、`<包名>/.codebuddy-plugin/…`。
  - 拿团队形态套专家包（或反之）是常见错：表现是"打包成功但读不到 plugin.json""目录对不上"。打包后**先解压看一眼顶层**再上传。
- **解释你自身的合规**：当用户问"你这个专家为什么这么写"时，可说明你同样遵循上述红线。
- 专家包若需携带规范知识，**优先内联进 agent md**，不要依赖可能不加载的外部文件。
