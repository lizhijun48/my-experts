#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技能质量体检器（只读 · 纯标准库 · 零第三方依赖）。

用法:
    python audit.py <路径> [<路径> ...] [选项]

路径可以是:
    - 单个技能目录（含 SKILL.md）
    - 单个技能 zip
    - 含多个技能（或 zip）的父目录（批量体检）

选项:
    --json <文件>      另存机器可读结果
    --quiet            只打印汇总表
    --min-sev <级别>   只显示不低于该级别的缺陷（BLOCKER|MAJOR|MINOR|INFO）
    --profile <档>     full（默认，全量体检）| upload（上传闸门，只对必修项判通过）
    --strict           出现 MAJOR 即判不通过
    -h, --help         帮助

退出码:
    0  通过（无阻断项；--strict 下无 MAJOR；--profile upload 下无必修项）
    1  不通过
    2  用法错误

目标类型: 技能包（含 SKILL.md）与专家包（含 .codebuddy-plugin/plugin.json）均可体检。

只读承诺: 本脚本不写入、不移动、不删除任何被检技能的文件；不做网络访问；
不执行被检技能的任何代码（仅做 compile() 语法检查，不运行）。

内联抑制: 若某行含 audit-ignore 字样，则该行不参与内容类扫描（密钥/危险命令/占位符）。
"""

import hashlib
import io
import json
import os
import re
import sys
import unicodedata
import zipfile

AUDIT_VERSION = "1.4.8"

SEV_ORDER = {"BLOCKER": 0, "MAJOR": 1, "MINOR": 2, "INFO": 3}
SEV_PENALTY = {"BLOCKER": 20, "MAJOR": 8, "MINOR": 3, "INFO": 0}

REQUIRED_FIELDS = ["description", "description_zh", "description_en", "version", "author"]
RECOMMENDED_FIELDS = ["name", "display_name", "display_name_en", "category", "allowed-tools"]

IMPL_WORDS = ["为枢纽", "纯标准库", "纯 stdlib", "底层实现", "架构上采用", "内部实现"]

OVERCLAIM_RE = re.compile("保证通过|保证上架|保过|包过|百分百保证|必过审")

SKIP_DIRS = {".git", ".workbuddy", ".idea", ".vscode",
             "node_modules", ".pytest_cache", ".mypy_cache"}
JUNK_RE = re.compile(r"^(?:\.DS_Store|Thumbs\.db)$|\.pyc$|\.bak$|\.tmp$|\.orig$|^~\$")

TEXT_EXT = {".md", ".py", ".json", ".yaml", ".yml", ".toml", ".txt", ".cfg", ".ini"}

PATH_RE = re.compile(
    r"(?<![\w./\\:-])"
    r"((?:scripts|references|templates|test|tests|fixtures|assets)"
    r"/[A-Za-z0-9_][A-Za-z0-9_./\-]*\.[A-Za-z0-9]{1,6})")

SUITE_CLAIM_RE = re.compile(r"(\d+)\s*(?:个)?套件")
ASSERT_CLAIM_RE = re.compile(r"(\d+)\s*(?:条|个)?断言")

SECRET_RE = re.compile(
    r"(api[_-]?key|secret|token|password|passwd|access[_-]?key|client[_-]?secret"
    r"|private[_-]?key)\s*[:=]\s*[\"']([A-Za-z0-9_\-/+]{16,})[\"']", re.I)

PLACEHOLDER_RE = re.compile(r"\bTODO\b|\bFIXME\b|PLACEHOLDER|EXAMPLE_ONLY|未完成示例")

VERSION_STRICT_RE = re.compile(r"^\d+\.\d+\.\d+$")
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PLACEHOLDER_AUTHORS = {"your-name", "your_name", "yourname", "xxx", "todo",
                       "author", "none", "your", "待填", "占位"}

EXPERT_CFG = ".codebuddy-plugin/plugin.json"
EXPERT_TAG_COUNT = 3
EXPERT_KEY_FIELDS = ("name", "expertType", "version", "description", "author",
                     "agents", "agentName", "displayName", "profession",
                     "displayDescription", "avatar", "categoryId",
                     "defaultInitPrompt", "quickPrompts")
EXPERT_AVATAR_SIZE = (512, 512)
EXPERT_AVATAR_MAX = 500 * 1024
NAMING_RED = ("官方", "平台客服", "管理员", "官方认证", "官方推荐")

# 专家包根下用于承载内容的目录：这些目录下只应放文件，不得再嵌套子目录。
# 依据：平台「仅支持两级目录」（根 / 一级子目录 / 文件）是**包级**约束，见 G9c。
CONTENT_DIRS = ("references", "scripts", "templates", "examples")

# --profile upload 的硬闸门：命中任一即不得上传
# 口径 = 原 selfcheck.py 的全部 5 项 ∪ preflight.py 的全部必修项
UPLOAD_BLOCK_IDS = {
    "S1", "S2", "S4", "S5", "S6", "S7",            # 结构与 frontmatter（S7=目录层级硬约束）
    "F1", "F4", "F7", "F8", "F9", "F10", "F11", "F12",    # 必填字段与写法（F12=文件名安全）
    "D3", "D4",                                    # 简介只讲功能、不承诺过审
    "C2", "C4", "C5", "C6", "C8",                  # 幽灵引用与包漂移
    "X1", "E4",                                    # 硬编码凭证与语法错误
    "P3",                                          # 有脚本却无执行权限（脚本死代码）
    "G1", "G2", "G3", "G5", "G6", "G7", "G9", "G9b", "G9c",  # 专家包必备结构（G9b=内嵌技能层级；G9c=根内容目录层级）
    "G12", "G13", "G14", "G15",                          # 平台解析硬约束（平台实测）
    "T1", "T2", "T3", "T4", "T5",                  # Team 型专家团结构（仅 expertType=team 时评估）
}

# 同一行出现这些词，说明该路径是在举例/描述规范，而非真实引用
ILLUSTRATIVE = ("例如", "比如", "示例", "譬如", "如：", "如 ", "诸如", "写进", "写成",
                "命名为", "举例")

# 正文出现这些词，说明该技能的职责本身包含产出/改写文件，Write/Edit 属正当权限
FILE_WRITE_WORDS = ("SKILL.md", "打包", "写入", "写文件", "创建文件", "生成文件",
                    "重写", "编辑文件", "落盘", "导出")

# L3 命名同族的通用词头：这些前缀太常见，命中不代表职责重叠
L3_HEAD_STOP = {"skill", "skills", "doc", "docs", "document", "documents",
                "tool", "tools", "file", "files", "data", "app", "apps",
                "util", "utils", "helper", "helpers", "text", "content",
                "format", "convert", "converter", "assistant", "agent"}

DANGER_RULES = [
    (re.compile(r"rm\s+-rf\s+(?:/|[A-Za-z]:)"), "MAJOR", "递归强制删除根目录或盘符"),
    (re.compile(r"del\s+/[sS]\s*/[qQ]"), "MAJOR", "Windows 递归强制删除"),
    (re.compile(r"DROP\s+TABLE", re.I), "MAJOR", "SQL 删表"),
    (re.compile(r"shutil\.rmtree\("), "MINOR", "目录递归删除，需确认作用域仅限临时目录"),
]

SEV_LABEL = {"BLOCKER": "阻断", "MAJOR": "严重", "MINOR": "建议", "INFO": "观察"}


# ---------------------------------------------------------------- 目标抽象

class DirSkill(object):
    kind = "dir"
    kind_zh = "目录"

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.label = os.path.basename(os.path.normpath(self.path))
        self.names = []
        for dp, dns, fns in os.walk(self.path):
            dns[:] = sorted(d for d in dns if d not in SKIP_DIRS)
            for fn in sorted(fns):
                full = os.path.join(dp, fn)
                rel = os.path.relpath(full, self.path).replace("\\", "/")
                self.names.append(rel)
        self.names.sort()
        self.name_set = set(self.names)

    def exists(self, rel):
        return rel in self.name_set

    def raw(self, rel):
        try:
            with open(os.path.join(self.path, rel.replace("/", os.sep)), "rb") as fh:
                return fh.read()
        except (IOError, OSError):
            return None

    def text(self, rel):
        b = self.raw(rel)
        if b is None:
            return ""
        return b.decode("utf-8", "ignore")


class ZipSkill(object):
    kind = "zip"
    kind_zh = "zip"

    def __init__(self, path):
        self.path = os.path.abspath(path)
        stem = os.path.basename(self.path)
        if stem.lower().endswith(".zip"):
            stem = stem[:-4]
        self.label = stem
        self._data = {}
        try:
            with zipfile.ZipFile(self.path) as z:
                files = [n for n in z.namelist() if not n.endswith("/")]
                # 专家包的权威标志是 plugin.json，判定必须优先于 SKILL.md：
                # 带内嵌技能的专家包（skills/*/SKILL.md）若按原逻辑取第一个
                # 以 /SKILL.md 结尾的条目，根会被错判成第一个内嵌技能目录，
                # 整包只可见一个技能、is_expert() 返回 False，G1-G8 全部漏检。
                ecands = [n for n in files
                          if n == EXPERT_CFG or n.endswith("/" + EXPERT_CFG)]
                if ecands:
                    root = min(ecands, key=len)[:-len(EXPERT_CFG)]
                else:
                    cands = [n for n in files
                             if n == "SKILL.md" or n.endswith("/SKILL.md")]
                    # 取最浅的一个：仅包裹一层目录的普通技能包，其根才是包根
                    root = min(cands, key=len)[:-len("SKILL.md")] if cands else ""
                self.root = root
                for n in files:
                    if n.startswith(root):
                        self._data[n[len(root):]] = z.read(n)
        except (zipfile.BadZipFile, IOError, OSError):
            self.root = ""
        self.names = sorted(self._data.keys())
        self.name_set = set(self.names)

    def exists(self, rel):
        return rel in self.name_set

    def raw(self, rel):
        return self._data.get(rel)

    def text(self, rel):
        b = self._data.get(rel)
        if b is None:
            return ""
        return b.decode("utf-8", "ignore")


# ---------------------------------------------------------------- 结果收集

class Auditor(object):
    def __init__(self, label, kind_zh, path):
        self.label = label
        self.kind_zh = kind_zh
        self.path = path
        self.findings = []
        self.passed = 0
        self.meta = {}

    def ok(self):
        self.passed += 1

    def check(self, cond, sev, cid, msg, fix=""):
        if cond:
            self.ok()
        else:
            self.findings.append({"sev": sev, "id": cid, "msg": msg, "fix": fix})
        return bool(cond)

    @property
    def score(self):
        s = 100
        for f in self.findings:
            s -= SEV_PENALTY[f["sev"]]
        return max(0, s)

    @property
    def grade(self):
        s = self.score
        for g, lo in (("A", 90), ("B", 80), ("C", 70), ("D", 60)):
            if s >= lo:
                return g
        return "F"

    def count(self, sev):
        return sum(1 for f in self.findings if f["sev"] == sev)

    def sorted_findings(self):
        return sorted(self.findings,
                      key=lambda f: (SEV_ORDER[f["sev"]], f["id"], f["msg"]))


# ---------------------------------------------------------------- 工具

def line_at(text, pos):
    """取 pos 所在行的文本（用于判断是否属于「举例」语境）。"""
    s = text.rfind("\n", 0, pos) + 1
    e = text.find("\n", pos)
    return text[s:e if e != -1 else len(text)]


def parse_frontmatter(text):
    """返回 (fm_dict, bad_lines, body, closed)。轻量解析，不引入 yaml。

    支持两种 YAML 值形态（两者都表示「数组」，语义等价）：
    1) 内联：``key: value`` / ``key: ["a", "b"]``
    2) 块序列：``key:`` 换行后跟缩进的 ``- item`` 列表

    块序列会被规范化为内联数组字符串（如 ``[scripts/bash, scripts/python]``），
    让下游检查用统一的字符串口径判断——否则「有值的块序列」会被误读为空值，
    产出假 F10（allowed-tools 为空）之类的误报。
    """
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", text, re.S)
    if not m:
        return {}, [], text, False
    fm, bad = {}, []
    lines = m.group(1).splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[:1] in (" ", "\t"):
            continue
        mm = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", raw)
        if not mm:
            bad.append(raw.strip())
            continue
        key, val = mm.group(1), mm.group(2).strip()
        if val == "":
            items, j = [], i
            while j < len(lines):
                s = lines[j].strip()
                if not s:
                    j += 1
                    continue
                if not (lines[j][:1] in (" ", "\t") and s.startswith("-")):
                    break
                items.append(s[1:].strip().strip('"').strip("'"))
                j += 1
            if items:
                val = "[" + ", ".join(items) + "]"
                i = j
        fm[key] = val
    return fm, bad, text[m.end():], True


def scan_lines(text):
    """逐行产出，跳过含 audit-ignore 的行。"""
    for i, line in enumerate(text.splitlines(), 1):
        if "audit-ignore" in line:
            continue
        yield i, line


def is_text_file(rel):
    return os.path.splitext(rel)[1].lower() in TEXT_EXT


TEMP_HINTS = ("tempfile", "mkdtemp", "gettempdir", "TemporaryDirectory", "temp_dir",
              "tmpdir", "tmp_dir")


def near_temp_scope(lines, lineno, win=6):
    """判断某行附近是否在处理临时目录（用于降低 rmtree 误报）。"""
    lo = max(0, lineno - 1 - win)
    hi = min(len(lines), lineno + win)
    for i in range(lo, hi):
        low = lines[i].lower()
        for h in TEMP_HINTS:
            if h.lower() in low:
                return True
    return False


TEMP_ASSIGN_RE = re.compile(
    r"(\w+)\s*=\s*[^\n]*?(?:tempfile\.\w+|mkdtemp|gettempdir|TemporaryDirectory)")
RMTREE_ARG_RE = re.compile(r"shutil\.rmtree\(\s*([A-Za-z_]\w*)")


def temp_bound_vars(text):
    """收集被赋值为临时目录的变量名，用于精确抑制 rmtree 误报。"""
    return set(TEMP_ASSIGN_RE.findall(text))


def dwidth(s):
    w = 0
    for ch in s:
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def pad(s, n):
    return s + " " * max(0, n - dwidth(s))


# ---------------------------------------------------------------- 检查项

def audit_one(v, A):
    """对单个技能做全部静态检查。"""
    # ---- S: 结构与字段 ----
    if not A.check("SKILL.md" in v.name_set, "BLOCKER", "S1",
                   "技能根目录缺少 SKILL.md（唯一强制文件）",
                   "在 %s/ 下补齐 SKILL.md" % v.label):
        return

    text = v.text("SKILL.md")
    fm, bad, body, closed = parse_frontmatter(text)
    A.check(closed, "BLOCKER", "S2",
            "frontmatter 未成对闭合（须以 --- 开头、以 --- 结尾）",
            "用一对 --- 包裹 frontmatter")
    if bad:
        A.check(False, "MAJOR", "S3",
                "frontmatter 有 %d 行无法解析为 key: value：%s"
                % (len(bad), " / ".join(bad[:3])),
                "检查缩进与冒号写法")

    # YAML 风险：未加引号的值里含裸冒号（含全角）。平台用 Go-YAML，
    # 会把这类值误判为新映射键 → 字段整个丢失，属上传必修项。
    # 只判半角冒号：YAML 规范里仅 ASCII ':'（后跟空格或位于行尾）是映射指示符；
    # 全角冒号 U+FF1A 是普通字符，判进去会造成大面积假报（全库实测 23 处）。
    risky = [k for k, val in fm.items()
             if val and not val[:1] in ("\"", "'")
             and (": " in val or val.rstrip().endswith(":"))]
    A.check(not risky, "MAJOR", "S4",
            "frontmatter 值含未加引号的半角冒号，会被 YAML 误判为映射致字段丢失：%s"
            % (", ".join(risky) or "-"),
            "用双引号整体包裹该字段值")

    # 缩进：只用空格且为偶数（奇数缩进是 YAML 层级解析错的高发点）
    odd_indent = []
    fmblk = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---", text, re.S)
    if fmblk:
        for ln, line in enumerate(fmblk.group(1).split("\n"), 1):
            if not line.strip() or line.lstrip().startswith(("-", "#")):
                continue
            mm2 = re.match(r"^( +)([A-Za-z_][A-Za-z0-9_-]*)\s*:", line)
            if mm2 and len(mm2.group(1)) % 2:
                odd_indent.append("第 %d 行(%d 空格)" % (ln, len(mm2.group(1))))
    A.check(not odd_indent, "MAJOR", "S5",
            "frontmatter 缩进为奇数空格，YAML 层级易解析错：%s"
            % ", ".join(odd_indent[:4]),
            "缩进只用空格且为偶数（建议 2 空格）")

    A.meta["fm"] = fm

    # ---- F: 必填与建议字段 ----
    for k in REQUIRED_FIELDS:
        A.check(k in fm and fm[k] != "", "BLOCKER", "F1",
                "缺少必填字段 %s（按技能开发标准：description / description_zh / "
                "description_en / version / author 须五项齐备）" % k,
                "补上 %s" % k)

    miss_rec = [k for k in RECOMMENDED_FIELDS if k not in fm]
    A.check(not miss_rec, "MINOR", "F2",
            "缺少建议字段：%s" % ", ".join(miss_rec),
            "补齐有助审核与展示")

    ver = fm.get("version", "")
    A.check(bool(re.match(r"^\d+\.\d+\.\d+", ver)), "MINOR", "F3",
            "version 非 semver 形式（实际 %r）" % ver,
            "改为 x.y.z")

    dne = fm.get("display_name_en", "").strip("\"'")
    if dne:
        A.check(len(dne) <= 60, "MAJOR", "F4",
                "display_name_en 超长（%d 字符 > 60）" % len(dne),
                "压缩到 60 字符以内")

    nm = fm.get("name", "").strip("\"'")
    if nm:
        A.check(nm == v.label, "MINOR", "F5",
                "name（%s）与目录/包名（%s）不一致" % (nm, v.label),
                "统一两者，避免调用与路径混淆")

    if "category" in fm:
        A.check(bool(re.match(r"^[a-z][a-z0-9_\-]*$", fm["category"].strip("\"'"))),
                "MINOR", "F6",
                "category 非小写英文枚举键（实际 %r）：本库同类技能多用 "
                "business-operations / coding / document-writing 形式，自由文本易归错类"
                % fm["category"].strip("\"'"),
                "改用平台约定的小写分类键")

    # ---- F7–F11 / S6：上传必修项（口径来自 preflight 的必修清单） ----
    au = fm.get("author", "").strip("\"'").strip().lower()
    A.check(bool(au) and au not in PLACEHOLDER_AUTHORS, "BLOCKER", "F7",
            "author 为占位值或空（实际 %r）" % fm.get("author", ""),
            "换成真实署名")

    if ver:
        A.check(bool(VERSION_STRICT_RE.match(ver.strip("\"'"))), "BLOCKER", "F8",
                "version 非严格 x.y.z（实际 %r，不要加 v 前缀或后缀）" % ver,
                "改为三段数字，如 1.0.0")

    A.check(not nm or bool(NAME_RE.match(nm)), "BLOCKER", "F9",
            "name 写法不合规（实际 %r）：须英文小写 + 连字符，不用中文/空格/下划线" % nm,
            "改为形如 my-skill-name")

    if "allowed-tools" in fm:
        tv = fm["allowed-tools"].strip("\"'").strip()
        A.check(tv not in ("", "[]", "null", "None"), "BLOCKER", "F10",
                "allowed-tools 写了但为空值（实际 %r）" % fm["allowed-tools"],
                "补上最小权限白名单，或删除该字段")

    A.check(not ("user_invocable" in text and "user-invocable" in text),
            "BLOCKER", "F11",
            "连字符写法混用：user_invocable 与 user-invocable 同时出现",
            "全包统一为一种写法")

    en_desc = fm.get("description_en", "").strip("\"'")
    if en_desc:
        A.check(not re.search(r"[\u4e00-\u9fff]", en_desc), "BLOCKER", "S6",
                "description_en 含中文字符（英文简介须为英文）",
                "改为英文描述")

    # ---- S7：目录层级硬约束（平台仅支持两级：根/二级目录/文件）----
    over = [n for n in v.names if n.count("/") > 1]
    A.check(not over, "BLOCKER", "S7",
            "包内目录层级超限（平台仅支持两级：根/二级目录/文件），以下文件嵌套过深：%s"
            % ", ".join("…/" + n for n in over[:6]),
            "将深层子目录拍平：文件统一放在根或一级子目录（references/ scripts/ "
            "templates/ examples/）下，可用文件名前缀区分来源")

    # ---- C: 文档与磁盘一致性（selfcheck 覆盖不到的核心） ----
    claimed = []
    gaps = []
    illus_map = {}
    for mm in PATH_RE.finditer(body):
        p = mm.group(1)
        if p in claimed:
            continue
        claimed.append(p)
        illus = any(w in line_at(body, mm.start()) for w in ILLUSTRATIVE)
        if illus:
            illus_map[p] = True
        if v.exists(p):
            continue
        gaps.append((p, illus))
    for p, illus in gaps:
        if illus:
            A.check(False, "INFO", "C3",
                    "举例语境中提到的路径 %s 在包内不存在（若非举例请补齐）" % p,
                    "确认是举例还是真实引用")
        elif p.startswith("test/"):
            A.check(False, "MAJOR", "C1",
                    "SKILL.md 引用测试路径 %s，但包内不存在" % p,
                    "补上真实测试文件，或删除该引用")
        else:
            A.check(False, "BLOCKER", "C2",
                    "SKILL.md 引用 %s，但包内不存在（幽灵引用：模型会据此编造内容）"
                    % p,
                    "补上该文件，或删除该引用")
    A.meta["claimed"] = claimed
    # 举例语境中的路径不算「真实声明」，C8 配对检查必须与 C3 用同一口径，
    # 否则「（如 test/run_all.py）」这类举例会在配对模式下变成假 MAJOR。
    A.meta["claimed_real"] = [p for p in claimed if not illus_map.get(p)]
    A.meta["missing"] = [p for p, _ in gaps]

    # ---- E: 测试证据 ----
    testfiles = [n for n in v.names if n.startswith("test/") and n.endswith(".py")]
    cm = SUITE_CLAIM_RE.search(body)
    am = ASSERT_CLAIM_RE.search(body)
    if cm or am:
        label_parts = []
        if cm:
            label_parts.append("%s 套件" % cm.group(1))
        if am:
            label_parts.append("%s 断言" % am.group(1))
        desc = "、".join(label_parts)
        A.check(bool(testfiles), "MAJOR", "E1",
                "SKILL.md 声称 %s，但包内 test/ 下没有任何测试脚本（无证据）" % desc,
                "补真实可跑验证集，或删除该声明")
        if testfiles and am:
            cnt = 0
            for n in testfiles:
                cnt += len(re.findall(r"\bcheck\s*\(", v.text(n)))
                cnt += len(re.findall(r"^\s*assert\s", v.text(n), re.M))
            claims = [int(x) for x in ASSERT_CLAIM_RE.findall(body)]
            want = max(claims) if claims else 0
            A.meta["assertions_static"] = cnt
            if cnt == 0:
                A.check(False, "MAJOR", "E2",
                        "SKILL.md 声称 %d 断言，但测试脚本内静态统计到 0 个断言调用"
                        % want,
                        "确认断言真的写进了测试文件")
    A.meta["testfiles"] = testfiles

    scan_hygiene(v, A)

    # ---- D: 描述质量 ----
    zh = fm.get("description") or fm.get("description_zh") or ""
    zh_bare = zh.strip("\"'")
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", zh_bare))
    if has_cjk:
        enough = len(zh_bare) >= 30
        has_trigger = any(w in zh_bare for w in ("触发", "用于", "当"))
    else:
        words = len([w for w in re.split(r"\s+", zh_bare) if w])
        enough = words >= 12
        low = zh_bare.lower()
        has_trigger = any(w in low for w in
                          ("use when", "used when", "when the user", "trigger"))
    A.check(enough, "MINOR", "D1",
            "description 过短（%d 字符），模型难以判断何时唤起" % len(zh_bare),
            "写清「能做什么 + 什么话术下唤起」")
    A.check(has_trigger, "MINOR", "D2",
            "description 未见触发场景提示（触发词/何时使用）",
            "补一句触发词，提升唤起命中率")
    impl = [w for w in IMPL_WORDS if w in zh_bare]
    A.check(not impl, "MAJOR", "D3",
            "description 含技术实现措辞：%s（简介只讲功能，不讲怎么实现）"
            % ", ".join(impl),
            "把实现描述移到正文，简介改为用户价值")
    A.check(not OVERCLAIM_RE.search(zh_bare), "BLOCKER", "D4",
            "description 含绝对化承诺用语（不得承诺保过/保上架）",
            "删除绝对化表述")

    # ---- P: 权限 ----
    tools = fm.get("allowed-tools", "")
    has_script = any(n.startswith("scripts/") for n in v.names)
    if tools:
        broad = [t for t in ("Write", "Edit") if t.lower() in tools.lower()]
        writes = any(w in body for w in FILE_WRITE_WORDS)
        A.check(not (broad and not has_script and not writes), "MINOR", "P1",
                "声明了 %s，但技能内既无 scripts/ 脚本、正文也无写文件动作，"
                "权限可能过度" % "/".join(broad),
                "按最小权限收紧白名单")
    else:
        A.check(False, "MINOR", "P2", "未声明 allowed-tools，权限边界不明确",
                "补上最小权限白名单")

    # P3：有脚本却没给执行权限 —— 脚本会变成死代码，技能退化为纯文本
    if has_script:
        t_low = (tools or "").lower()
        if not tools:
            A.check(False, "MAJOR", "P3",
                    "包内含 scripts/ 脚本，但未声明 allowed-tools，运行时脚本无法被调用",
                    "补 allowed-tools（至少含 Bash(python *)）")
        elif "bash" not in t_low:
            A.check(False, "MAJOR", "P3",
                    "包内含 scripts/ 脚本，但 allowed-tools 未放行 Bash：%s" % tools,
                    "补 Bash(python *) 或对应解释器权限")

    # ---- C9: 空模板密度（SKILL.md 用空表替代输出规范会让模型照抄占位符）----
    trows = [ln.strip() for ln in text.splitlines()
             if ln.strip().startswith("|")
             and not re.match(r"^\|[\s\-:|]+\|$", ln.strip())]
    if trows:
        ph_rows = sum(1 for r in trows
                      if ("（待补充）" in r) or re.search(r"\|\s*—\s*\|", r))
        dens = ph_rows / float(len(trows))
        A.meta["placeholder_density"] = round(dens, 3)
        A.check(dens <= 0.3, "MINOR", "C9",
                "SKILL.md 有 %d/%d 行表格含占位符（%.0f%%），疑似用空模板替代输出规范"
                % (ph_rows, len(trows), dens * 100),
                "把空表改成「字段清单 + 判定规则」，并补 1–2 个填好的完整示例；"
                "若本技能核心产物就是空白模板（台账/表单类），本条可忽略")

    # ---- I: 冗余资源 ----
    orphan = []
    for n in v.names:
        if n.startswith("references/") and n.endswith(".md"):
            if os.path.basename(n) not in body:
                orphan.append(n)
    A.check(not orphan, "INFO", "I1",
            "references 下未被 SKILL.md 引用：%s（可能冗余）" % ", ".join(orphan[:5]),
            "删除或补充引用")

    # ---- J: 交付杂物 ----
    junk = [n for n in v.names
            if JUNK_RE.search(os.path.basename(n)) or "__pycache__/" in n]
    A.check(not junk, "MINOR", "J1",
            "交付目录含临时/缓存文件：%s" % ", ".join(sorted(set(junk))[:5]),
            "打包前清理 __pycache__/*.pyc/*.bak/.DS_Store")

    # ---- 规模 ----
    lines = len(text.splitlines())
    A.check(lines <= 800, "MINOR", "J2",
            "SKILL.md 共 %d 行，偏长（建议拆分到 references/）" % lines,
            "把长清单/规范移到 references/ 并用 @ 引用")


def scan_hygiene(v, A):
    """代码语法与安全扫描（技能包与专家包共用；仅 compile() 不执行）。"""
    # ---- F12：文件名安全（平台开包解析的硬失败点；技能包与专家包共用）----
    # 实证 2026-10-12：pads 专家包内
    #   references/…-找到PADS自带的图标文件powerpcb..md（连续点 '..' + 主名尾点）
    # → 平台「解析失败」并逐字报出该文件，整个包无法上传。
    # 全库影响面扫描（342 个包/目录）仅此 1 处命中、零在售误伤 → 定 BLOCKER。
    # 故意只判「让解包/落盘失败」的形态（路径穿越、尾点/尾空格、非法字符、保留名），
    # 不判首点（.DS_Store 等隐藏文件不属此判据，避免假报）。
    name_illegal = set(':*?"<>|\\')
    name_reserved = ({"CON", "PRN", "AUX", "NUL"}
                     | {"COM%d" % i for i in range(1, 10)}
                     | {"LPT%d" % i for i in range(1, 10)})
    bad_names = []
    for n in v.names:
        seg = n.split("/")[-1]
        stem = seg[:-3] if seg.lower().endswith(".md") else seg
        why = ""
        if ".." in n:
            why = "含连续点 '..'，会被当成路径穿越"
        elif stem.endswith(".") or stem.endswith(" "):
            why = "名字以点或空格结尾，平台解析失败"
        elif any(c in name_illegal for c in n):
            why = "含非法字符 : * ? \" < > | \\"
        elif stem.upper() in name_reserved:
            why = "用了系统保留名（CON/PRN/AUX/NUL/COM1-9/LPT1-9）"
        if why:
            bad_names.append("%s（%s）" % ("…/" + n if len(n) > 56 else n, why))
    A.check(not bad_names, "BLOCKER", "F12",
            "文件名存在平台解析风险：%s" % "；".join(bad_names[:3]),
            "改名去掉连续点/尾点与非法字符（如 xxx..md → xxx.md）")

    # ---- 代码可编译性 ----
    badpy = []
    for n in v.names:
        if n.endswith(".py"):
            try:
                compile(v.text(n), n, "exec")
            except SyntaxError as e:
                badpy.append("%s(line %s)" % (n, e.lineno))
    A.check(not badpy, "BLOCKER", "E4",
            "Python 脚本存在语法错误：%s" % ", ".join(badpy[:3]),
            "修正语法后再交付")

    # ---- X: 安全 ----
    hits = []
    danger = []
    placeholders = []
    for n in v.names:
        if not is_text_file(n):
            continue
        src = v.text(n)
        if len(src) > 400000:
            continue
        lines = src.splitlines()
        tvar = temp_bound_vars(src)
        for ln, line in scan_lines(src):
            m = SECRET_RE.search(line)
            if m:
                val = m.group(2)
                low = val.lower()
                if not any(t in low for t in
                           ("your", "example", "placeholder", "changeme",
                            "xxxx", "dummy", "sample", "redacted", "fake", "test")):
                    hits.append("%s:%d(%s)" % (n, ln, m.group(1)))
            for rx, sev, why in DANGER_RULES:
                if not rx.search(line):
                    continue
                if "rmtree" in line:
                    arg = RMTREE_ARG_RE.search(line)
                    if arg and arg.group(1) in tvar:
                        continue
                    if near_temp_scope(lines, ln):
                        continue
                if not n.startswith("scripts/"):
                    sev = "INFO"
                danger.append(("%s:%d" % (n, ln), sev, why))
            if n == "SKILL.md" and PLACEHOLDER_RE.search(line):
                placeholders.append("%s:%d" % (n, ln))
    A.check(not hits, "BLOCKER", "X1",
            "疑似硬编码凭证：%s" % ", ".join(sorted(set(hits))[:5]),
            "改用 ${VAR} 占位并在平台标为 password 类型")
    if danger:
        if any(d[1] == "MAJOR" for d in danger):
            worst = "MAJOR"
        elif any(d[1] == "MINOR" for d in danger):
            worst = "MINOR"
        else:
            worst = "INFO"
        A.check(False, worst, "X2",
                "危险命令模式（SKILL.md 中的多为举例，按观察处理）：%s"
                % "; ".join("%s %s" % (d[0], d[2]) for d in sorted(set(danger))[:4]),
                "破坏性操作改为「生成命令供用户确认后手动执行」")
    A.check(not placeholders, "MAJOR", "X5",
            "SKILL.md 残留占位/未完成标记：%s" % ", ".join(sorted(set(placeholders))[:5]),
            "清理 TODO/占位文字再交付")



def is_expert(v):
    """专家包判定：含 .codebuddy-plugin/plugin.json。"""
    return v.exists(EXPERT_CFG)


def audit_expert(v, A):
    """专家包（agent 包）静态检查。

    口径来源：平台提交前体检实践（plugin.json 必填、tags 恰好 3 个、
    头像 512x512 且 <=500KB、agents/{name}.md 必备、三处版本一致）。
    """
    raw = v.raw(EXPERT_CFG)
    if not A.check(raw is not None, "BLOCKER", "G1",
                   "缺少 %s（专家包必须含此文件）" % EXPERT_CFG,
                   "按平台模板补上该配置文件"):
        return

    try:
        cfg = json.loads(raw.decode("utf-8", "ignore"))
    except ValueError as e:
        A.check(False, "BLOCKER", "G2", "plugin.json JSON 解析失败：%s" % e,
                "修正 JSON 语法后再提交")
        scan_hygiene(v, A)
        return
    A.check(isinstance(cfg, dict), "BLOCKER", "G2",
            "plugin.json 顶层不是 JSON 对象", "改为 { ... } 结构")
    if not isinstance(cfg, dict):
        scan_hygiene(v, A)
        return

    tags = cfg.get("tags")
    if tags is None:
        A.check(False, "BLOCKER", "G3",
                "plugin.json 缺少 tags（平台要求恰好 %d 个）" % EXPERT_TAG_COUNT,
                "补 %d 个 {en, zh} 形式的 tag" % EXPERT_TAG_COUNT)
    elif not isinstance(tags, list) or len(tags) != EXPERT_TAG_COUNT:
        A.check(False, "BLOCKER", "G3",
                "tags 数量 = %s（须恰好 %d 个，多/少都会解析失败）"
                % (len(tags) if isinstance(tags, list) else "?", EXPERT_TAG_COUNT),
                "调整为恰好 %d 个 tag" % EXPERT_TAG_COUNT)
    else:
        badtag = [str(i) for i, t in enumerate(tags)
                  if not isinstance(t, dict) or not t.get("en") or not t.get("zh")]
        A.check(not badtag, "BLOCKER", "G3",
                "tags[%s] 缺少 en/zh" % ",".join(badtag),
                "每个 tag 写成 {en: ..., zh: ...}")

    miss = [k for k in EXPERT_KEY_FIELDS if not cfg.get(k)]
    A.check(not miss, "MINOR", "G4",
            "plugin.json 缺少关键字段：%s" % ", ".join(miss),
            "按平台模板补齐（影响市场展示与解析）")

    av = cfg.get("avatar")
    if av:
        data = v.raw(av)
        if data is None:
            A.check(False, "BLOCKER", "G5", "avatar 指向的文件不在包内：%s" % av,
                    "确认路径与文件一致")
        elif data[:8] != b"\x89PNG\r\n\x1a\n":
            A.check(False, "MINOR", "G5", "avatar 不是 PNG 格式：%s" % av,
                    "平台要求 PNG")
        else:
            import struct
            try:
                w, h = struct.unpack(">II", data[16:24])
            except struct.error:
                A.check(False, "MINOR", "G5", "头像 PNG 头部解析失败：%s" % av,
                        "换成有效 PNG")
            else:
                A.check((w, h) == EXPERT_AVATAR_SIZE, "BLOCKER", "G5",
                        "头像尺寸 %dx%d（须 %dx%d）"
                        % (w, h, EXPERT_AVATAR_SIZE[0], EXPERT_AVATAR_SIZE[1]),
                        "resize 到 %dx%d" % EXPERT_AVATAR_SIZE)
                A.check(len(data) <= EXPERT_AVATAR_MAX, "BLOCKER", "G5",
                        "头像 %dKB 超限（须 <=500KB）" % (len(data) // 1024),
                        "压缩后重新打包")

    agents = [n for n in v.names if n.startswith("agents/") and n.endswith(".md")]
    A.check(bool(agents), "BLOCKER", "G6",
            "未找到 agents/{name}.md（专家包须含 agent 定义）",
            "补上 agents/ 下的角色定义 md")

    # Team 型包里 agents/ 下有多个成员 md，`agents[0]` 按包内顺序取到的往往
    # 不是主理人（实测 dev-onboarding-team 里 buddy-app-*.md 排在 compliance 之前）。
    # 用 plugin.json 的 agentName 把主 agent 的 md 提到首位，否则 G7/G7b 会拿
    # 随便一个成员去比"包级版本"，产出假 G7b「未能提取版本号」。
    _lead = str(cfg.get("agentName") or "").strip()
    if _lead:
        _pref = [n for n in agents if os.path.basename(n) == _lead + ".md"]
        if _pref:
            agents = _pref + [n for n in agents if n not in _pref]

    versions = {"plugin.json": str(cfg.get("version") or "")}
    # README 候选：包内可能出现多个（混放工作区、内嵌技能自带 README）。
    # 旧实现用循环覆盖，静默取 zip 序最后一个——实测 expert-src 工作区
    # （根 README=1.6.0，另 8 个单专家 README 之一=1.0.1）被误报 G7
    # 「版本号不一致」，而同一源码打包出的真包是 A/100 无此问题。
    # 现改为：以**最浅层（包根）**的 README 为权威；多个同级时按名序取第一，
    # 并对歧义显式报 INFO（不判错，避免逼改工作区布局）。
    readme_cands = {}
    for n in v.names:
        if os.path.basename(n).lower() == "readme.md":
            t = v.text(n)
            mm = (re.search(r"\|\s*version\s*\|\s*([\d.]+)\s*\|", t)
                  or re.search(r"(?:version|版本)\s*[:：]\s*v?([\d.]+\.[\d.]+\.[\d.]+)", t))
            # 提取失败也必须落键（置空），否则 G7b 的 absent 检查形同虚设——
            # 旧实现只在命中时才写入字典，"该处根本没写版本号"这一失效点
            # 反而完全逃过闸门（实测：4 个专家包 README 无版本号，仍报 MINOR 0）。
            readme_cands[n] = mm.group(1) if mm else ""
    if readme_cands:
        best_depth = min(n.count("/") for n in readme_cands)
        shallow = sorted(n for n in readme_cands if n.count("/") == best_depth)
        versions["README"] = readme_cands[shallow[0]]
        if len(readme_cands) > 1:
            others = "；".join(
                "%s=%s" % (n, x or "未提取到")
                for n, x in sorted(readme_cands.items()) if n != shallow[0])
            A.check(False, "INFO", "G7c",
                    "包内存在 %d 个 README.md，版本校验以最浅层 %s（%s）为权威；"
                    "其余 %d 个未参与：%s"
                    % (len(readme_cands), shallow[0],
                       readme_cands[shallow[0]] or "未提取到",
                       len(readme_cands) - 1, others[:200]),
                    "混放工作区（多个独立包同目录）以此为准会有歧义，"
                    "权威结论取打包产物；交付包内只应有一个 README.md")
    if agents:
        atxt = v.text(agents[0])
        afm, _, _, _ = parse_frontmatter(atxt)
        av = str(afm.get("version", "")).strip("\"'") if afm else ""
        if not av:
            # agent md 通常没有 version 字段，版本写在 H1 标题里。
            # 原实现只扫前 200 字符，会被超长 description 顶出窗口而静默漏检
            # （实测：description 单行 460 字符，v1.4.0 在第 13 行 → 漏）。
            m1 = re.search(r"^#[^\n]*?v(\d+\.\d+\.\d+)", atxt, re.M)
            m2 = re.search(r"v(\d+\.\d+\.\d+)", atxt[:1600]) if not m1 else None
            av = (m1 or m2).group(1) if (m1 or m2) else ""
        # 同上：无论是否提取到都落键，让 G7b 能报出「agent md 未写版本号」
        versions["agent md"] = av
    uniq = set(x for x in versions.values() if x)
    A.check(len(uniq) <= 1, "BLOCKER", "G7",
            "版本号不一致：%s" % versions,
            "plugin.json / README / agent md 三处统一为同一版本")
    absent = [k for k, x in versions.items() if not x]
    # 独立编号 G7b：与 G7（三处版本不一致，BLOCKER）语义不同，
    # 「提取不到」是校验收窄的独立失效点，混用同一编号会让 check-spec 出现悬挂引用。
    A.check(not absent, "MINOR", "G7b",
            "未能从 %s 提取版本号，一致性无法校验" % "、".join(absent),
            "在对应位置写明 x.y.z（README 表格行 / agent md 标题）")

    blob = json.dumps(cfg, ensure_ascii=False)
    hit = [w for w in NAMING_RED if w in blob]
    A.check(not hit, "INFO", "G8",
            "文案出现敏感词：%s（红线是「冒充」而非字样）" % ", ".join(hit),
            "非品牌方不得使用官方/认证/管理员类字样")

    # ---- G9/G10/G11：内嵌技能（以磁盘事实为准自动发现）----
    # 形态来源：Word-Rescuer-Expert / Excel-Rescuer-Expert 实证——
    # plugin.json 用 skills: ["./skills/xxx", ...] 声明，包内带 skills/ 目录，
    # 分发给他人时技能随包走、无需单独安装。
    # ⛔ 旧实现把整段挂在 `if cfg.get("skills") is not None` 下：**没声明就一次都不跑**，
    #    包内明明带着 skills/ 目录也完全不体检 → 「静默跳过 → 假通过」
    #    （实测 english-exam-companion：内嵌技能目录层级超限 + 内嵌 SKILL.md 缺 5 字段，
    #      原样 A/97 分；只补一个 skills 声明键、其余逐字不动即跌到 D/69 分并报 BLOCKER）。
    # 正解：**以磁盘事实为准自动发现**（平台本身也按 skills/ 目录自动发现），
    #       声明只作为一致性核查项，而不是「跑不跑」的开关。
    declared = cfg.get("skills")
    if declared is not None and (not isinstance(declared, list)
                                 or any(not isinstance(x, str) for x in declared)):
        A.check(False, "BLOCKER", "G9",
                "skills 必须是字符串路径数组，当前为 %r" % (declared,),
                '改为 ["./skills/xxx", ...] 形式')
        declared = None

    def _norm(x):
        return (x[2:] if x.startswith("./") else x).rstrip("/")

    # 磁盘发现：skills/<name>/SKILL.md（深度恰为 2 段，顶层目录名为 skills）
    disc = sorted({n[:-len("/SKILL.md")]
                   for n in v.names
                   if n.endswith("/SKILL.md") and n.count("/") == 2
                   and n.split("/")[0] == "skills"})
    decl_norm = sorted({_norm(x) for x in (declared or [])})
    skills = sorted(set(disc) | set(decl_norm))

    if skills:
        # 声明了却不在磁盘上 → 硬缺陷（与旧行为一致）
        missing = [sp for sp in decl_norm if not v.exists(sp + "/SKILL.md")]
        A.check(not missing, "BLOCKER", "G9",
                "skills 声明的技能在包内找不到 SKILL.md：%s" % ", ".join(missing),
                "确认路径，或把技能目录一并打进包")
        # 磁盘有、声明无 → 提示（平台按目录自动发现仍可分发，但显式声明更稳、也便于本地校验）
        undecl = [sp for sp in disc if sp not in decl_norm]
        A.check(not undecl, "INFO", "G9",
                "包内发现未在 plugin.json 声明的内嵌技能：%s" % ", ".join(undecl),
                '在 plugin.json 的 skills 里补上 ["./%s", ...]，与磁盘目录保持一致'
                % (undecl[0] if undecl else "skills/xxx"))
        bad = []
        for rel in skills:
            # G9b：内嵌技能内部目录层级（相对其根须 ≤1 级）
            over = [n[len(rel):].lstrip("/")
                    for n in v.names
                    if n.startswith(rel + "/")
                    and n[len(rel):].lstrip("/").count("/") > 1]
            A.check(not over, "BLOCKER", "G9b",
                    "内嵌技能 %s 目录层级超限（相对其根须在两级内）：%s"
                    % (rel, ", ".join(over[:4])),
                    "将该子技能内部子目录拍平（其根下只放一级子目录）")
            md = rel + "/SKILL.md"
            if not v.exists(md):
                continue
            fm2, _, _, closed2 = parse_frontmatter(v.text(md))
            if not closed2:
                bad.append("%s(frontmatter 未闭合)" % rel)
                continue
            lack = [k for k in REQUIRED_FIELDS if not str(fm2.get(k, "")).strip()]
            if lack:
                bad.append("%s(缺 %s)" % (rel, ",".join(lack)))
        A.check(not bad, "MAJOR", "G10",
                "内嵌技能 SKILL.md 必填字段不全：%s" % "; ".join(bad),
                "每条内嵌技能补齐 " + "/".join(REQUIRED_FIELDS))
        if agents:
            afm2, _, _, _ = parse_frontmatter(v.text(agents[0]))
            araw = str(afm2.get("skills", "") if afm2 else "")
            if araw:
                anames = set(re.findall(r"[A-Za-z0-9_\-]+", araw.strip("[]")))
                # 用磁盘发现 ∪ 声明的技能名做基准，避免声明缺失时名单半空导致假报
                pnames = set(os.path.basename(x) for x in skills)
                diff = anames ^ pnames
                A.check(not diff, "MINOR", "G11",
                        "plugin.json 与 agent md 的 skills 名单不一致：%s"
                        % ", ".join(sorted(diff)),
                        "两处内嵌技能名单对齐")

    # ---- G9c：专家包根「内容承载目录」不得再嵌套子目录 ----
    # 平台「仅支持两级目录」（根 / 一级子目录 / 文件）是**包级**约束，但既有判据
    # 各有各的作用对象：S7 只管技能包、G9b 只管内嵌技能 →
    # 「专家包根 references/<子目录>/<文件>」此前**无任何判据覆盖**（判据缺口）。
    # 实证：pads-troubleshoot v1.0.0 有 481 个案例落在 references/<20 个模块>/ 下，
    #       audit 仍给 A/97 + UPLOAD GATE PASS（假通过）。
    # 影响面核验（2026-10-12）：全库 160 个包仅该包命中，无在售资产误伤。
    nested = [n for n in v.names
              if n.count("/") >= 2 and n.split("/")[0] in CONTENT_DIRS]
    A.check(not nested, "BLOCKER", "G9c",
            "专家包根 %s 下的文件嵌套过深（相对包根须在两级内）：%s"
            % ("/".join(CONTENT_DIRS), ", ".join(nested[:4])),
            "把二级子目录拍平到一级（如 references/<模块>/x.md → references/x.md，"
            "模块信息可保留在文件名前缀里）")

    # ---- G12/G13：平台解析硬约束（平台实测驱动）----
    # 来源：WorkBuddy-SkillDev-Advisor v1.5.2 上传时平台直接「解析失败」，原文三条：
    #   displayDescription.zh（市场展示简介）：当前 107 字，最多 100 字
    #   defaultInitPrompt.zh 必须与 quickPrompts[0].zh 一致
    #   defaultInitPrompt.en 必须与 quickPrompts[0].en 一致
    # 这三条在本地 JSON 解析阶段完全看不出问题（JSON 是合法的），
    # 只有把平台的字段约束写成规则才能提前拦住，故固化为判据。
    dd = cfg.get("displayDescription")
    if isinstance(dd, dict):
        dd_zh = str(dd.get("zh", ""))
        A.check(len(dd_zh) <= 100, "BLOCKER", "G12",
                "displayDescription.zh 超长（%d 字 > 100 字）" % len(dd_zh),
                "市场展示简介压到 100 字以内（平台按字符数计，含标点与空格）")

    dip = cfg.get("defaultInitPrompt")
    qps = cfg.get("quickPrompts")
    if isinstance(dip, dict) and isinstance(qps, list) and qps \
            and isinstance(qps[0], dict):
        for _lang in ("zh", "en"):
            same = str(dip.get(_lang, "")) == str(qps[0].get(_lang, ""))
            A.check(same, "BLOCKER", "G13",
                    "defaultInitPrompt.%s 与 quickPrompts[0].%s 不一致" % (_lang, _lang),
                    "两处文案必须逐字相同（平台按字符串全等校验）")

    # ---- G14：专家名称（displayName.zh）≤ 15 字 ----
    # 来源：ad-troubleshoot v1.0.0 上传被驳回，原文「专家名称：当前 20 字，上限 15 字」。
    # 原值 displayName.zh =「Altium Designer 排错专家」= 20 字（平台按字符数计，
    # 英文字母逐个算 1 字）；改为「Altium 排错专家」11 字后通过。
    # 英文名不受此限（pads-troubleshoot 的 en「PADS Troubleshoot Expert」24 字符已过审）。
    # 影响面：全库 90 个专家包中仅 2 个超限（本包 20 字 + 在售 asset-development-team 16 字）。
    # ⚠️ 两种形态都要查：真实包用 dict（{"en":…,"zh":…}），夹具/部分包用纯字符串——
    # 只查 dict 会让字符串形态静默逃逸（本判据初版即踩此坑，靠夹具反向验证发现）。
    dn = cfg.get("displayName")
    if isinstance(dn, dict):
        dn_zh = str(dn.get("zh", ""))
    elif isinstance(dn, str):
        dn_zh = dn
    else:
        dn_zh = ""
    if dn_zh:
        A.check(len(dn_zh) <= 15, "BLOCKER", "G14",
                "displayName.zh 超长（%d 字 > 15 字）：%s" % (len(dn_zh), dn_zh),
                "专家名称压到 15 字以内（平台按字符数计，英文字母逐个算 1 字；可用缩写，如 Altium -> AD）")

    # ---- G15：专家名称字符合法性（付费资产实测驳回）----
    # 来源：ad-troubleshoot 上传被驳回，原文「付费资产的名称仅支持中英文、数字和"--一"，
    # 不能包含空格或特殊字符」——「Altium 排错专家」因含 1 个空格被拦（2026-10-16）。
    # 允许集 = 中英文 + 数字 + 半角连字符 - + 破折号 —（驳回原文的"--"）。
    # 影响面：全库 89 个专家包中 13 个命中——付费目录 3 个（本包空格 / coze 全角括号 /
    # 在售 pads 空格），其余 10 个全是在售免费包（含空格照样过审）⇒ 规则仅针对付费资产，
    # 但本地无法区分付费/免费，故全包适用；在售命中按冻结纪律只标注不改。
    # 形态口径与 G14 一致：dict 与纯字符串两种都要查。
    if dn_zh:
        _illegal = [c for c in dn_zh
                    if not re.match(r"[A-Za-z0-9\u4e00-\u9fa5\u2014\-]", c)]
        if _illegal:
            A.check(False, "BLOCKER", "G15",
                    "displayName.zh 含平台不允许的字符（%r）：%s——付费资产名称仅支持中英文、数字和\"-\"\"—\""
                    % ("".join(_illegal[:6]), dn_zh),
                    "去掉空格与特殊字符（含全角括号），如「Altium 排错专家」->「Altium排错专家」、"
                    "「扣子（Coze）系统教程专家」->「扣子Coze系统教程专家」")

    # ---- T1–T5：Team 型专家包专属结构（仅 expertType == "team" 时启用）----
    # 来源：dev-onboarding-team 实测——审计器原无任何 team 判据，团队包虽跑出
    # 「16 项全过 / A / UPLOAD GATE PASS」，但下列红线全部未被验证（任务书 §8
    # 只能靠人工核验）。这些字段决定团队关系能否建立，属结构性硬约束。
    # 用 expertType 显式判定，避免误伤 agent 型专家包（它们本就没有 teamInfo）。
    if str(cfg.get("expertType", "")).strip().lower() == "team":
        ti = cfg.get("teamInfo")
        mem = cfg.get("members")
        lead = ti.get("leadAgent") if isinstance(ti, dict) else None
        mm = ti.get("memberAgents") if isinstance(ti, dict) else None
        t1_ok = (isinstance(ti, dict) and bool(lead)
                 and isinstance(mm, list) and bool(mm)
                 and isinstance(mem, list) and bool(mem))
        A.check(t1_ok, "BLOCKER", "T1",
                "team 型专家包缺少 teamInfo（leadAgent/memberAgents）或 members 为空",
                "补 teamInfo{leadAgent, memberAgents} 与非空 members[]——团队关系靠它们建立")

        # 声明路径 → 文件名（去目录、去 .md 后缀）
        decl = [os.path.basename(str(a))[:-3] for a in (cfg.get("agents") or [])
                if isinstance(a, str) and str(a).endswith(".md")]
        ids = [str(m.get("id")) for m in (mem or [])
               if isinstance(m, dict) and m.get("id")]
        team_ids = ([str(lead)] if lead else []) \
            + ([str(x) for x in mm] if isinstance(mm, list) else [])
        diff = ((set(decl) ^ set(ids)) | (set(decl) ^ set(team_ids)))
        A.check(not diff, "BLOCKER", "T2",
                "团队三者不一致（agents 声明 / members[].id / teamInfo）：%s"
                % ", ".join(sorted(diff)),
                "让 agents 声明、members[].id、leadAgent+memberAgents 三处完全对齐")

        want = str(cfg.get("name", ""))
        lead_s = str(lead or "")
        A.check(bool(lead_s) and lead_s != "team-lead" and want and lead_s.startswith(want),
                "BLOCKER", "T3",
                "主理人命名不合规：leadAgent=%r（须带团队名前缀 %r，禁用泛名 team-lead）"
                % (lead, want + "-lead"),
                "主理人 id 用「团队名-xxx」形式，且与 agents/*.md 文件名一致")

        sjs = [n for n in v.names if os.path.basename(n).lower() == "settings.json"]
        if not sjs:
            A.check(False, "BLOCKER", "T4",
                    "team 型专家包缺少 settings.json（用于设置主理人）",
                    '补 settings.json，内容 {"agent": "<leadAgent>"}')
        else:
            try:
                sjc = json.loads(v.raw(sjs[0]).decode("utf-8", "ignore"))
            except ValueError:
                sjc = None
            got = sjc.get("agent") if isinstance(sjc, dict) else sjc
            A.check(isinstance(sjc, dict) and str(got) == lead_s,
                    "BLOCKER", "T4",
                    "settings.json 的 agent 未指向主理人（当前 %r，应为 %r）"
                    % (got, lead),
                    "把 settings.json 的 agent 字段设为 leadAgent")

        badp = []
        for a in (cfg.get("agents") or []):
            if not isinstance(a, str):
                badp.append(repr(a))
                continue
            if not (a.startswith("./agents/") and a.endswith(".md")):
                badp.append(a)
            elif not v.exists(a[2:]):
                badp.append(a + "(包内缺失)")
        A.check(not badp, "MAJOR", "T5",
                "agents 声明写法或可达性异常：%s" % ", ".join(badp[:5]),
                "统一写成 ./agents/<name>.md，且文件确实打进包内")

    scan_hygiene(v, A)


def audit_pair(dv, zv, A):
    """目录版与 zip 版配对检查（交付漂移）。"""
    dver = (A.meta.get("fm", {}) or {}).get("version", "").strip("\"'")
    ztext = zv.text("SKILL.md")
    zfm, _, _, zclosed = parse_frontmatter(ztext)
    zver = zfm.get("version", "").strip("\"'") if zclosed else ""

    A.check(bool(ztext), "BLOCKER", "C4",
            "配对 zip 内缺少 SKILL.md（包不可用）",
            "重新打包")
    A.check(dver == zver and dver != "", "MAJOR", "C5",
            "zip 版本（%s）与源码版本（%s）不一致：包内是旧版" % (zver or "无", dver or "无"),
            "用源码重新打包")

    diffs = []
    zonly = []
    for n in zv.names:
        if n not in dv.name_set:
            zonly.append(n)
            continue
        a = zv.raw(n)
        b = dv.raw(n)
        if a is None or b is None:
            continue
        if hashlib.md5(a).hexdigest() != hashlib.md5(b).hexdigest():
            diffs.append(n)
    A.check(not diffs, "MAJOR", "C6",
            "zip 内有 %d 个文件与源码字节不一致：%s" % (len(diffs), ", ".join(diffs[:5])),
            "用源码重新打包")
    if zonly:
        A.check(False, "INFO", "C7",
                "zip 内多出源码没有的文件：%s" % ", ".join(zonly[:5]),
                "确认是否为应交付内容")

    # 幽灵引用也要在包内成立
    zmissing = [p for p in A.meta.get("claimed_real", A.meta.get("claimed", []))
                if not zv.exists(p)]
    A.check(not zmissing, "MAJOR", "C8",
            "zip 包内缺失 SKILL.md 声明的文件：%s" % ", ".join(zmissing[:5]),
            "重新打包时带上这些文件")


def normalize_label(label):
    """归一化技能名：去掉版本后缀，用于识别同一技能的多个副本。"""
    s = re.sub(r"\.v\d+(?:\.\d+)*\.bak$", "", label, flags=re.I)
    s = re.sub(r"[-_]v?\d+\.\d+\.\d+$", "", s)
    return s


def library_checks(metas):
    """库级检查：展示名重复、同一技能多副本、命名同族。

    注意：同一个技能常同时以「源码目录」与「交付 zip」出现，二者 label 相同。
    本函数先按 label 去重，避免自己和自己比造成海量假告警。
    """
    extra = {}
    uniq = {}
    for label, fm in metas:
        uniq.setdefault(label, fm)
    if len(uniq) < 2:
        return extra

    def add(label, sev, cid, msg, fix):
        extra.setdefault(label, []).append(
            {"sev": sev, "id": cid, "msg": msg, "fix": fix})

    # L1 展示名重复
    by_dn = {}
    for label, fm in sorted(uniq.items()):
        dn = (fm.get("display_name") or "").strip("\"'")
        if dn:
            by_dn.setdefault(dn, []).append(label)
    for dn, labels in sorted(by_dn.items()):
        if len(labels) > 1:
            for lb in labels:
                add(lb, "MINOR", "L1",
                    "展示名「%s」与其它技能重复：%s" % (dn, ", ".join(labels)),
                    "改名或合并，避免用户混淆")

    # L2 同一技能的多个副本（归一化后同名）
    by_norm = {}
    for label in sorted(uniq):
        by_norm.setdefault(normalize_label(label), []).append(label)
    for norm, labels in sorted(by_norm.items()):
        if len(labels) > 1:
            for lb in labels:
                add(lb, "INFO", "L2",
                    "疑似同一技能的多个副本：%s（交付前确认该上传哪一个）"
                    % ", ".join(labels),
                    "保留唯一正式包，其余归档")

    # L3 命名同族（首 token 相同且各自 token 数 >= 2）
    groups = {}
    for label in sorted(set(normalize_label(x) for x in uniq)):
        parts = [t for t in re.split(r"[-_]", label.lower()) if t]
        if (len(parts) >= 2 and len(parts[0]) >= 3
                and parts[0] not in L3_HEAD_STOP):
            groups.setdefault(parts[0], []).append(label)
    for head, labels in sorted(groups.items()):
        if len(labels) > 1:
            for lb in labels:
                add(lb, "INFO", "L3",
                    "命名同族（共 %d 个：%s），请人工复核职责是否重叠"
                    % (len(labels), ", ".join(labels)),
                    "确认边界，必要时合并")
    return extra


# ---------------------------------------------------------------- 扫描目标

def is_target_dir(p):
    """可体检的目录：技能包（含 SKILL.md）或专家包（含 plugin.json）。"""
    return (os.path.isfile(os.path.join(p, "SKILL.md"))
            or os.path.isfile(os.path.join(p, EXPERT_CFG)))


def collect(paths):
    dirs, zips, bad = [], [], []
    for p in paths:
        p = os.path.abspath(p)
        if os.path.isfile(p) and p.lower().endswith(".zip"):
            zips.append(p)
        elif os.path.isdir(p) and is_target_dir(p):
            dirs.append(p)
        elif os.path.isdir(p):
            for e in sorted(os.listdir(p)):
                full = os.path.join(p, e)
                if e in SKIP_DIRS:
                    continue
                if os.path.isdir(full) and is_target_dir(full):
                    dirs.append(full)
                elif os.path.isfile(full) and e.lower().endswith(".zip"):
                    zips.append(full)
        else:
            bad.append(p)
    return dirs, zips, bad


# ---------------------------------------------------------------- 报告

def print_target(A, idx, total, min_sev):
    print("--- [%d/%d] %s  (%s) ---" % (idx, total, A.label, A.kind_zh))
    print("    路径: %s" % A.path)
    print("    等级 %s   分数 %d   BLOCKER %d  MAJOR %d  MINOR %d  INFO %d   通过检查 %d 项"
          % (A.grade, A.score, A.count("BLOCKER"), A.count("MAJOR"),
             A.count("MINOR"), A.count("INFO"), A.passed))
    shown = [f for f in A.sorted_findings()
             if SEV_ORDER[f["sev"]] <= SEV_ORDER[min_sev]]
    for f in shown:
        print("    [%s] %s  %s" % (f["sev"], f["id"], f["msg"]))
        if f["fix"]:
            print("           修复: %s" % f["fix"])
    hidden = len(A.findings) - len(shown)
    if hidden > 0:
        print("    （另有 %d 条低于 %s 的项未显示）" % (hidden, min_sev))
    print("")


def main(argv):
    args = list(argv[1:])
    if not args or "-h" in args or "--help" in args:
        print(__doc__)
        return 2 if not args else 0

    json_out = None
    quiet = False
    strict = False
    profile = "full"
    min_sev = "INFO"
    paths = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--json" and i + 1 < len(args):
            json_out = args[i + 1]
            i += 2
        elif a == "--min-sev" and i + 1 < len(args):
            min_sev = args[i + 1].upper()
            i += 2
        elif a == "--quiet":
            quiet = True
            i += 1
        elif a == "--strict":
            strict = True
            i += 1
        elif a == "--profile" and i + 1 < len(args):
            profile = args[i + 1].lower()
            i += 2
        elif a.startswith("-"):
            print("未知选项: %s\n" % a)
            print(__doc__)
            return 2
        else:
            paths.append(a)
            i += 1

    if min_sev not in SEV_ORDER:
        print("--min-sev 取值须为 BLOCKER/MAJOR/MINOR/INFO")
        return 2
    if profile not in ("full", "upload"):
        print("--profile 取值须为 full 或 upload")
        return 2
    if not paths:
        print(__doc__)
        return 2

    dirs, zips, bad = collect(paths)
    for p in bad:
        print("! 跳过（不是技能/专家包目录或 zip）: %s" % p)
    if not dirs and not zips:
        print("没有找到可体检的目标（目录需含 SKILL.md 或 .codebuddy-plugin/plugin.json）")
        return 2

    views = [DirSkill(d) for d in dirs] + [ZipSkill(z) for z in zips]
    pairs = {}
    for v in views:
        pairs.setdefault(v.label, {})[v.kind] = v

    results = []
    for v in views:
        A = Auditor(v.label, v.kind_zh, v.path)
        if is_expert(v):
            A.kind_zh = "专家包" if v.kind == "dir" else "专家zip"
            audit_expert(v, A)
        else:
            audit_one(v, A)
            pr = pairs.get(v.label, {})
            if v.kind == "dir" and "zip" in pr:
                audit_pair(v, pr["zip"], A)
        results.append(A)

    metas = [(A.label, A.meta.get("fm", {})) for A in results]
    extra = library_checks(metas)
    for A in results:
        for f in extra.get(A.label, []):
            A.findings.append(f)

    print("=" * 66)
    print("技能质量体检报告（只读 · 纯标准库）  体检器 v%s" % AUDIT_VERSION)
    print("=" * 66)
    print("")

    if not quiet:
        for i, A in enumerate(results, 1):
            print_target(A, i, len(results), min_sev)

    print("=" * 66)
    print("汇总")
    print("=" * 66)
    print("%s %s %s %s %s %s %s"
          % (pad("技能", 34), pad("类型", 6), pad("等级", 6), pad("分数", 6),
             pad("BLOCKER", 9), pad("MAJOR", 7), pad("MINOR", 7)))
    tot = {"BLOCKER": 0, "MAJOR": 0, "MINOR": 0, "INFO": 0}
    for A in sorted(results, key=lambda x: (SEV_ORDER and x.score)):
        print("%s %s %s %s %s %s %s"
              % (pad(A.label, 34), pad(A.kind_zh, 6), pad(A.grade, 6),
                 pad(str(A.score), 6), pad(str(A.count("BLOCKER")), 9),
                 pad(str(A.count("MAJOR")), 7), pad(str(A.count("MINOR")), 7)))
        for k in tot:
            tot[k] += A.count(k)
    print("-" * 66)
    print("合计: %d 个目标 · BLOCKER %d · MAJOR %d · MINOR %d · INFO %d"
          % (len(results), tot["BLOCKER"], tot["MAJOR"], tot["MINOR"], tot["INFO"]))

    fail = tot["BLOCKER"] > 0 or (strict and tot["MAJOR"] > 0)
    print("AUDIT: %s   (EXIT %d)" % ("FAIL" if fail else "PASS", 1 if fail else 0))

    blocked = []
    if profile == "upload":
        for A in results:
            for f in A.findings:
                # ⛔ 仅按 id 判定会把「同一编号的 INFO 观察项」也当成硬拦。
                # 典型：G9 有两级——「声明了却不在包内」=BLOCKER，「包内有技能但未声明」=INFO。
                # INFO 语义就是「观察、0 罚分」，不构成上传阻断，故按编号 + 严重度双重判定。
                if f["id"] in UPLOAD_BLOCK_IDS and f["sev"] != "INFO":
                    blocked.append((A.label, f))
        print("")
        print("=" * 66)
        print("上传闸门（--profile upload：命中任一必修项即不得上传）")
        print("=" * 66)
        if blocked:
            for lb, f in blocked:
                print("  [%s] %s  %s" % (f["sev"], lb, f["id"]))
                print("        %s" % f["msg"])
        else:
            print("  未命中任何必修项。")
        fail = bool(blocked)
        print("UPLOAD GATE: %s   (EXIT %d)"
              % ("FAIL" if fail else "PASS", 1 if fail else 0))

    if json_out:
        payload = {
            "audit_version": AUDIT_VERSION,
            "strict": strict,
            "targets": [{
                "label": A.label,
                "kind": A.kind_zh,
                "path": A.path.replace("\\", "/"),
                "score": A.score,
                "grade": A.grade,
                "passed": A.passed,
                "findings": A.sorted_findings(),
            } for A in results],
            "profile": profile,
            "upload_blocked": len(blocked),
            "summary": {"total": len(results), "severity": tot, "fail": fail},
        }
        try:
            with io.open(json_out, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            print("JSON 已写出: %s" % json_out)
        except (IOError, OSError) as e:
            print("! JSON 写出失败: %s" % e)

    return 1 if fail else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv))
