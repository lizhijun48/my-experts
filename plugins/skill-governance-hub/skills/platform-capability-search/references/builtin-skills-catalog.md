# 官方内置技能目录（builtin-skills-catalog）

> 用途：四层检索的**第 1 层（零安装，优先级最高）**。模型背不出这份清单，推荐前必读。
> 数据基准：2026-09-26 实测（macOS 路径）。客户端升级后内置可能增减，拿不准时重新扫目录。

## 目录路径

- macOS：`/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/resources/builtin-skills/`
- Windows：应用安装目录的 `Resources` 下同类结构

## ⚠️ 最容易漏推的一类：带隐藏开关的设计技能

以下 6 个 `ardot-*` 技能带 `disable-model-invocation: true`，**不出现在常规技能列表里**，
但目录里存在、可被引用。用户提设计类需求时必须主动想起来：

| 技能 | 干什么 | 用户会怎么说 |
|---|---|---|
| ardot-poster | 海报 / 宣传单 / 横幅 / 封面 / Logo / 插画 | "帮我做张海报""活动横幅" |
| ardot-slides | 幻灯片设计稿（注意：**不是** .pptx 文件） | "帮我设计一套演示页面" |
| ardot-ui-design | UI 界面：网页 / Web 应用 / 后台 / 落地页 | "画一个产品界面""做落地页设计" |
| ardot-design-to-code | 设计稿转前端代码 / 从网站提取设计系统 | "把这个设计还原成代码" |
| ardot-design-router | 设计任务分发（意图不明时先走它） | 笼统的"帮我做个设计" |
| ardot-design-core | 全部设计任务的硬规则（随域技能自动注入） | —（不需要主动推） |

**推设计类需求的结论：优先推 ardot 系（零安装、可控性最高），不要一上来就推市场技能。**

## 其余 9 个常规内置技能

| 技能 | 干什么 | 典型触发 |
|---|---|---|
| buddy-multimodal-generation | 文生 3D 模型、图生 3D、图片/视频模板特效 | "生成 3D 模型""给照片加特效" |
| cloudstudio-deploy | 把本地静态站点部署到云端预览 | "把这个网站发布出去看看" |
| expert-manager | 创建/修改/体检 WorkBuddy 专家包 | "帮我做个专家""改我的专家" |
| marketplace-skill-installer | 从推荐市场搜索并安装技能 | "装个 XX 技能" |
| skill-creator | 指导写新技能的规范 | "我想做一个 skill" |
| neodata-financial-search | 自然语言查金融数据（股/基/指数/宏观/外汇） | "查一下茅台的市盈率" |
| wb-finance-skill | 金融场景总入口（行情/财报/估值/量化/回测等） | 金融类问题的第一路由 |
| westock-data | 结构化行情数据（A/H/美/日韩股、ETF、期货、可转债…） | "拉一下沪深300日K" |
| westock-tool | 条件选股 / 选基（filter / strategy / 排行） | "帮我筛高股息 ETF" |

## 检索规则提醒

1. 命中内置 = 标记 ✅ 零安装，优先于一切市场推荐。
2. 内置没命中再往第 2 层（本地已装）走，已装的不重复推。
3. 金融类需求注意路由顺序：wb-finance-skill 是总入口，westock-data / westock-tool 是数据/工具层。
