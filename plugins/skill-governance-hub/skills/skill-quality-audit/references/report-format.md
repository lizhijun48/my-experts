# 输出格式（report-format）

本文件说明体检器的文本报告、JSON 结构与退出码口径。判据见 `check-spec.md`。

## 一、文本报告

```
==================================================================
技能质量体检报告（只读 · 纯标准库）  体检器 v1.4.8
==================================================================

--- [1/3] 技能名  (目录) ---
    路径: <绝对路径>
    等级 A   分数 94   BLOCKER 0  MAJOR 0  MINOR 2  INFO 0   通过检查 31 项
    [MINOR] D2  description 未见触发场景提示（触发词/何时使用）
           修复: 补一句触发词，提升唤起命中率
    [MINOR] F6  category 非小写英文枚举键（实际 '...'）...
           修复: 改用平台约定的小写分类键
    （另有 N 条低于 <级别> 的项未显示）

==================================================================
汇总
==================================================================
技能                      类型   等级   分数   BLOCKER   MAJOR   MINOR
<label>                   目录   A      94     0         0       2
------------------------------------------------------------------
合计: 3 个目标 · BLOCKER 0 · MAJOR 1 · MINOR 2 · INFO 0
AUDIT: PASS   (EXIT 0)
```

带 `--profile upload` 时，在 `AUDIT:` 行之后追加闸门段落，并以闸门结论作为退出码：

```
==================================================================
上传闸门（--profile upload：命中任一必修项即不得上传）
==================================================================
  [BLOCKER] skill-dev-standard  F7
        author 为占位值或空（实际 'your-name'）
UPLOAD GATE: FAIL   (EXIT 1)
```

无必修项时打印 `未命中任何必修项。` 且 `UPLOAD GATE: PASS (EXIT 0)`。

约定：

- 目标类型显示为「目录 / zip / 专家包 / 专家zip」，由包内是否含 `SKILL.md` 或 `.codebuddy-plugin/plugin.json` 自动判定。
- 每个目标一段，缺陷按「级别 → 编号 → 文案」排序，同一目标内顺序稳定。
- 汇总表按 BLOCKER 数降序排列（同分时顺序仍确定），便于先看最差的。
- 中文按显示宽度对齐，不截断技能名。
- 不打印时间戳，保证**同输入同输出**。

## 二、JSON 结构

```json
{
  "audit_version": "1.4.8",
  "strict": false,
  "profile": "upload",
  "upload_blocked": 1,
  "targets": [
    {
      "label": "技能名",
      "kind": "目录",
      "path": "<绝对路径，斜杠统一为 />",
      "score": 94,
      "grade": "A",
      "passed": 31,
      "findings": [
        {"sev": "MINOR", "id": "D2", "msg": "…", "fix": "…"}
      ]
    }
  ],
  "summary": {
    "total": 3,
    "severity": {"BLOCKER": 0, "MAJOR": 1, "MINOR": 2, "INFO": 0},
    "fail": false
  }
}
```

字段说明：

- `sev`：`BLOCKER` / `MAJOR` / `MINOR` / `INFO`。
- `id`：检查项编号，对应 `check-spec.md`，便于跨报告比对同一类问题的数量变化。
- `passed`：通过项计数，随检查路径变化，仅供横向参考，不参与评分。
- `profile`：`full`（默认）或 `upload`。
- `upload_blocked`：命中必修项的条数；`full` 档下恒为 0。
- `targets` 与 `findings` 均有序，JSON 以 `sort_keys=True` 写出，保证字节可复现。

## 三、退出码

| 码 | 含义 |
|---|---|
| 0 | 通过（`--profile upload` 下由必修项是否命中决定） |
| 1 | 不通过 |
| 2 | 用法错误（未给路径、路径不存在、选项取值非法） |

说明：

- 默认（`full`）档：分数低不等于退出码非零——只有 BLOCKER（及 `--strict` 下的 MAJOR）才判不通过。
- `--profile upload` 档：退出码改由**必修项集合**（见 `check-spec.md` 第四节）决定，**取代**上面的规则，因此可以出现「`AUDIT: PASS` 但 `UPLOAD GATE: FAIL`」。
- `--min-sev` 只影响**显示**，不影响退出码。
- `--quiet` 只影响**显示**，不影响 JSON 与退出码。

## 四、阅读建议

1. 先看汇总表的 BLOCKER 列：非零的包一律不要直接上传。
2. 再看 MAJOR：多为包与源码已分叉（C5/C6）、YAML 致命写法（S4/S5）、验证证据缺失（E1/E2）。
3. MINOR 里的 F1 若是「缺 description_en / description_zh」，属于批量可修的字段问题。
4. INFO 一律当线索而非结论，需人工判断（举例语境、知识文档里的命令示例、命名同族）。
5. 上传前跑 `--profile upload`：它才是「能不能提交」的最终判据，全量档的 PASS 不代表闸门 PASS。
6. 修完重跑，用同一份 JSON 对比同类 `id` 的数量变化，作为修复进度的客观依据。
