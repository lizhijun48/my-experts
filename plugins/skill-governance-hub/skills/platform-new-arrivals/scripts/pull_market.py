#!/usr/bin/env python3
"""新货周报取数脚本（platform-new-arrivals 附带）

面向任意用户：路径全部动态展开，绝不打印令牌，绝不硬编码用户名。
用法：
  python3 pull_market.py            # 全量拉取并写入当日缓存
  python3 pull_market.py --from-cache  # 只读当日缓存（不存在则报错退出码 2）
输出：JSON 摘要打到 stdout（供 agent 读取），完整快照写入缓存文件。
退出码：0 成功 / 1 取数失败 / 2 缓存不存在
"""
import re, glob, base64, json, sys, os, datetime, urllib.request

HOST = 'https://copilot.tencent.com'
CACHE_DIR = os.path.expanduser('~/.workbuddy/cache/new-arrivals')
TODAY = datetime.date.today().isoformat()
CACHE_FILE = os.path.join(CACHE_DIR, f'snapshot-{TODAY}.json')


def die(code, msg):
    print(json.dumps({'ok': False, 'error': msg}, ensure_ascii=False))
    sys.exit(code)


def get_token():
    """从本地客户端日志抓有效令牌；只在内存中使用，绝不输出。"""
    best = None
    for p in glob.glob(os.path.expanduser('~/.workbuddy/logs/**/*.log'), recursive=True):
        try:
            data = open(p, 'rb').read()
        except Exception:
            continue
        for m in re.finditer(rb'Bearer (eyJ[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+)', data):
            t = m.group(1).decode()
            try:
                pl = t.split('.')[1]
                pl += '=' * (-len(pl) % 4)
                exp = json.loads(base64.urlsafe_b64decode(pl))['exp']
            except Exception:
                continue
            if not best or exp > best[0]:
                best = (exp, t)
    return best[1] if best else None


def post(token, path, body):
    req = urllib.request.Request(HOST + path, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json',
                                          'Authorization': 'Bearer ' + token,
                                          'Origin': HOST, 'Referer': HOST})
    return json.loads(urllib.request.urlopen(req, timeout=60).read().decode())


def main():
    if '--from-cache' in sys.argv:
        if os.path.exists(CACHE_FILE):
            print(open(CACHE_FILE, encoding='utf-8').read())
            return
        die(2, '当日缓存不存在: ' + CACHE_FILE)

    token = get_token()
    if not token:
        die(1, '未能从本地日志获取有效令牌（客户端未登录或日志不可读）')

    rows, page = [], 1
    while True:
        try:
            d = post(token, '/v2/operation-platform/market/expert/list',
                     {'page': page, 'page_size': 100}) .get('data') or {}
        except Exception as e:
            die(1, f'第 {page} 页请求失败: {type(e).__name__}')
        batch = d.get('experts') or []
        if not batch:
            break
        rows.extend(batch)
        total = d.get('total_count') or d.get('total') or 0
        if (total and len(rows) >= total) or len(batch) < 100 or page > 200:
            break
        page += 1

    pulled_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    def to_bj(s):
        if not s:
            return None
        try:
            dt = datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
        except Exception:
            return None
        if dt.tzinfo is None:
            return dt
        return dt.astimezone(datetime.timezone(datetime.timedelta(hours=8))).replace(tzinfo=None)

    recent = []
    now = datetime.datetime.now()
    for r in rows:
        bj = to_bj(r.get('created_at'))
        if bj and (now - bj).days <= 7:
            recent.append({
                'name': r.get('display_name_zh'),
                'profession': r.get('profession_zh'),
                'use_count': r.get('use_count') or 0,
                'created_at': bj.strftime('%Y-%m-%d'),
                'source': r.get('source'),
                'expert_type': r.get('expert_type'),
            })
    recent.sort(key=lambda x: x['use_count'], reverse=True)

    summary = {
        'ok': True,
        'pulled_at': pulled_at,
        'total_experts': len(rows),
        'recent_7d_count': len(recent),
        'recent_top20': recent[:20],
        'note': 'created_at 已 +8 转北京时间；调用量为 use_count 累计口径',
    }
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
