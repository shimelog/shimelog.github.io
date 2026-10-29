#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""推しの締切 自動更新パイプライン（EBiDAN 各グループの公式サイト＋公式通販 MAILIVIS のメンバー・ユニット別ショップ）

  python3 pipeline.py check PAGE.html WORK   新着・変更のあった告知を WORK/new/*.txt に保存し、一覧を表示
  python3 pipeline.py merge PAGE.html WORK   WORK/extracted.json を告知本文と照合し、PAGE.html を更新

状態（既読の告知とそのハッシュ、掲載中の予定）はすべて PAGE.html の DATA に入っている。
読み取り（告知本文 → 予定の構造化）はこのスクリプトでは行わない。check と merge の間で別途行う。
"""
import sys, os, re, json, html, time, hashlib, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

UA = "Mozilla/5.0 (compatible; oshi-schedule-prototype)"
GROUPS = {"超特急": ["カイ", "リョウガ", "タクヤ", "ユーキ", "タカシ", "シューヤ", "マサヒロ", "アロハ", "ハル"],
          "M!LK": ["佐野勇斗", "塩﨑太智", "曽野舜太", "山中柔太朗", "吉田仁人"],
          "SUPER★DRAGON": ["志村玲於", "古川毅", "ジャン海渡", "飯島颯", "伊藤壮吾", "田中洸希", "池田彪馬", "松村和哉", "柴崎楽"],
          "ONE N' ONLY": ["TETTA", "REI", "EIKU", "HAYATO", "NAOYA"],
          "原因は自分にある。": ["大倉空人", "小泉光咲", "桜木雅哉", "長野凌大", "武藤潤", "杢代和人", "吉澤要人"],
          "Lienel": ["芳賀柊斗", "近藤駿太", "高岡ミロ", "森田璃空", "武田創世", "高桑真之"]}
KINDS = {"チケット": ["受付開始", "申込締切", "当落発表", "入金締切", "一般発売", "リセール締切", "配席発表"],
         "リリース・グッズ": ["発売日", "配信開始", "受付開始", "販売開始", "予約締切", "販売締切", "特典締切", "応募締切"],
         "応募・企画": ["応募締切", "当選発表"]}
NG_NOTE = "告知本文と照合できませんでした。公式の告知で確認してください"
KEEP_PAST_DAYS = 7          # 過ぎた予定を残す日数
RECHECK_DAYS = 30           # 既読の告知を再取得して変更を確認する期間（掲載日から）
END_MARKS = ("BACK", "関連記事", "Tweet", "シェア", "一覧ページに戻る")


def now_jst():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=9)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
    time.sleep(1.0)  # サイトに負荷をかけないよう1秒あける
    return body


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def main_lines(h):
    b = re.sub(r"<(script|style).*?</\1>", "", h, flags=re.S)
    m = re.search(r"<main.*?</main>", b, re.S)
    b = m.group(0) if m else b
    b = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h\d>|</tr>|</dd>|</dt>", "\n", b)
    t = html.unescape(re.sub(r"<[^>]+>", "", b)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t　]+", " ", l).strip() for l in t.split("\n")]
    lines = [l for l in lines if l]
    for i, l in enumerate(lines):          # ページ末尾の「関連記事」などは本文に含めない
        # 共有ボタンが本文より前にあるサイトもあるので、本文らしい行がいくつか出てからの印だけを終わりとみなす
        if l in END_MARKS and i > 5 and sum(len(x) >= 20 for x in lines[:i]) >= 3:
            return lines[:i]
    return lines


# ---------- 一覧の巡回 ----------
def list_bullettrain():
    base, out = "https://bullettrain.jp", {}
    for path in ("/news/23/", "/news/23/?page=2", "/news/list/23/24"):
        b = re.sub(r"<(script|style).*?</\1>", "", get(base + path), flags=re.S)
        for href, body in re.findall(r'<li[^>]*>\s*<a href="(/news/detail/\d+)">(.*?)</a>\s*</li>', b, re.S):
            cat = re.search(r'class="category">(.*?)<', body, re.S)
            date = re.search(r'class="date">\s*(\d{4})/(\d\d)/(\d\d)', body)
            tit = re.search(r'<div class="tit">(.*?)</div>\s*(?:<p class="date"|</div>|$)', body, re.S)
            span = re.search(r'<div class="tit">.*?<span>(.*?)</span>', body, re.S)
            tags = [clean(t) for t in re.findall(r'class="tag[^"]*">(.*?)<', body)]
            title = clean(span.group(1)) if span else clean(re.sub(r'<div class="tag-wrap">.*?</div>', "", tit.group(1), flags=re.S)) if tit else ""
            e = out.setdefault(base + href, {"group": "超特急", "title": title, "cats": [], "pub": "", "site_tags": tags})
            e["cats"].append(clean(cat.group(1)) if cat else ("TICKET" if "list/23/24" in path else ""))
            if date: e["pub"] = "-".join(date.groups())
    return out


def list_milk():
    base, out = "https://sd-milk.com", {}
    for path in ("/contents/news", "/contents/news?page=2", "/contents/news/ticket"):
        h = get(base + path)
        for href, body in re.findall(r'<a href="(/contents/\d+)"[^>]*class="c_contents-list-anchor">(.*?)</a>', h, re.S):
            t = re.search(r"<h2[^>]*>(.*?)</h2>", body, re.S)
            d = re.search(r'datetime="(\d{4}-\d\d-\d\d)', body)
            e = out.setdefault(base + href, {"group": "M!LK", "title": clean(t.group(1)) if t else "", "cats": [], "pub": d.group(1) if d else "", "site_tags": []})
            e["cats"] += [clean(x) for x in re.findall(r'class="tag">(.*?)<', body)]
    return out


def list_links(base, paths, group, link_re):
    """お知らせ一覧から、告知ページへのリンク・掲載日・タイトルを拾う（サイトごとに作りが違うので、リンクの形だけ指定する）"""
    out = {}
    for path in paths:
        h = re.sub(r"<(script|style).*?</\1>", "", get(base + path), flags=re.S)
        for href, body in re.findall(r'<a href="(' + link_re + r')(?:\?[^"]*)?"[^>]*>(.*?)</a>', h, re.S):
            d = re.search(r"(20\d\d)[./-](\d\d)[./-](\d\d)", body)
            t = re.search(r"<h[23][^>]*>(.*?)</h[23]>", body, re.S)
            title = clean(t.group(1)) if t else clean(re.sub(r"20\d\d[./-]\d\d[./-]\d\d|posted|NEW", " ", clean(body)))
            title = re.sub(r"\s*NEW$", "", title)
            if not title:
                continue
            cats = [clean(x) for x in re.findall(r'class="[^"]*(?:label-category|list-tag)[^"]*">(.*?)<', body)]
            e = out.setdefault(base + href, {"group": group, "title": title, "cats": [], "pub": "-".join(d.groups()) if d else "", "site_tags": []})
            e["cats"] += cats
    return out


def list_lienel():
    return list_links("https://lienel.jp", ("/contents/news", "/contents/news/page/2", "/contents/news/ticket"), "Lienel", r"/contents/\d+")


def list_onenonly():
    return list_links("https://one-n-only.jp", ("/contents/news", "/contents/news/page/2", "/contents/news/ticket"), "ONE N' ONLY", r"/contents/\d+")


def list_genjibu():
    return list_links("https://genjibu.jp", ("/news/1/", "/news/1/?page=2", "/news/11/"), "原因は自分にある。", r"/news/detail/\d+")


def list_superdragon():
    """SUPER★DRAGON は WordPress のフィード（RSS）から拾う。掲載日時は UTC なので日本時間に直す"""
    out = {}
    s = get("https://super-dragon.jp/news/feed/")
    for it in re.findall(r"<item>(.*?)</item>", s, re.S)[:30]:
        link = re.search(r"<link>(.*?)</link>", it)
        t = re.search(r"<title>(.*?)</title>", it, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", it)
        if not link or not t:
            continue
        pub = ""
        if d:
            try:
                pub = (datetime.strptime(d.group(1).strip()[:25], "%a, %d %b %Y %H:%M:%S") + timedelta(hours=9)).strftime("%Y-%m-%d")
            except ValueError:
                pass
        out[link.group(1).strip()] = {"group": "SUPER★DRAGON", "title": clean(re.sub(r"<!\[CDATA\[|\]\]>", "", t.group(1))), "cats": [], "pub": pub, "site_tags": []}
    return out


# MAILIVIS（スターダスト公式通販）のショップのうち、超特急・M!LK に関係するもの。メンバー個人やユニットのショップは members を付ける
MAILIVIS_SHOPS = {
    "3-chahan": ("超特急", ["シューヤ", "マサヒロ"]),
    "3-takamatsu-aloha": ("超特急", ["アロハ"]),
    "6-matsuo-takashi": ("超特急", ["タカシ"]),
    "1-kusakawa-takuya": ("超特急", ["タクヤ"]),
    "5-hideout404": ("超特急", ["リョウガ", "ユーキ"]),
    "6-milk": ("M!LK", []),
    "2-sano-hayato": ("M!LK", ["佐野勇斗"]),
    "2-sono-shunta": ("M!LK", ["曽野舜太"]),
    "7-yamanaka-jyutaro": ("M!LK", ["山中柔太朗"]),
}


PARTIAL_ERRORS = []


def list_mailivis():
    """各ショップのトピック（販売のお知らせ）一覧。掲載から RECHECK_DAYS 日を過ぎたものは対象にしない"""
    base, out = "https://mailivis.jp", {}
    oldest = (now_jst() - timedelta(days=RECHECK_DAYS)).strftime("%Y-%m-%d")
    for code, (group, members) in MAILIVIS_SHOPS.items():
        try:
            h = get(f"{base}/shop/topic/topicdetaillist.aspx?genre={code}")
        except urllib.error.HTTPError as ex:
            if ex.code != 404:                 # トピックが1件もないショップは 404 を返す
                PARTIAL_ERRORS.append(f"MAILIVIS {code}: {ex}")
            continue
        except Exception as ex:
            PARTIAL_ERRORS.append(f"MAILIVIS {code}: {ex}")
            continue
        m = re.search(r"<main.*?</main>", h, re.S)
        for href, body in re.findall(r'<a href="(/shop/t/t\d+/)">(.*?)</a>', m.group(0) if m else h, re.S):
            t = re.search(r'block-top-topic--heading">(.*?)</p>', body, re.S)
            d = re.search(r'txt-date">\s*(\d{4})\.(\d\d)\.(\d\d)', body)
            pub = "-".join(d.groups()) if d else ""
            if pub and pub < oldest:
                continue
            e = out.setdefault(base + href, {"group": group, "title": clean(t.group(1)) if t else "", "cats": ["MAILIVIS"], "pub": pub, "site_tags": []})
            e["site_tags"] = sorted(set(e["site_tags"]) | set(members))
    return out


def skip(e):
    """締切や発売日が載る見込みのない告知は読まない"""
    cats = set(c for c in e["cats"] if c)
    if e["group"] == "M!LK" and "sd-milk.com" in e.get("url", ""):
        return bool(cats) and cats <= {"MEDIA"}
    if cats and cats <= {"MEDIA", "RADIO", "MOVIE", "BIRTHDAY"}:
        return True
    return bool(re.search(r"MOVIE更新|WALLPAPER|BLOG更新|ブログ更新|発送完了|発送について|会員証|メンテナンス|放送決定|掲載決定|オンエア", e["title"]))


# ---------- ページ内の DATA ----------
DATA_RE = re.compile(r"const DATA = (.*?);\nconst WD", re.S)


PAGE_MARK = '<meta name="shimelog-page" content="1">'


def unwrap(h):
    if PAGE_MARK in h and h.lstrip().lower().startswith("<!doctype html>"):
        return h                                   # GitHub Pages 版：完全なHTML文書のまま扱う
    """Artifact から取得し直したページは公開時の枠（<!doctype html>…<body> と </body></html>）で包まれている。
    そのまま再公開すると枠が二重になるので、元のソース（<title> で始まる）だけを取り出す"""
    if h.lstrip().startswith("<title>"):
        return h.strip() + "\n"
    m = re.match(r"\s*<!doctype html><html><head>.*?</head><body>\n?", h, re.S | re.I)
    e = re.search(r"\n?</body></html>\s*$", h, re.I)
    if not m or not e or not h[m.end():].lstrip().startswith("<title>"):
        sys.exit("ページの枠の形式が想定と違います。二重に包んでしまうおそれがあるので中止します。公開はしないでください。")
    return h[m.end():e.start()].strip() + "\n"


def load_page(path):
    h = unwrap(open(path, encoding="utf-8").read())
    m = DATA_RE.search(h)
    if not m:
        sys.exit("PAGE.html に DATA が見つかりません。ページの構造が変わっています。中止します。")
    return h, json.loads(m.group(1).replace("<\\/", "</"))


def save_page(path, h, data):
    m = DATA_RE.search(h)
    js = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out = h[:m.start(1)] + js + h[m.end(1):]
    if PAGE_MARK in h:
        if not out.lower().startswith("<!doctype html>") or "</html>" not in out:
            sys.exit("出力するページの形式が不正です。中止します。公開はしないでください。")
    elif not out.startswith("<title>") or "<!doctype" in out.lower() or "</body>" in out.lower():
        sys.exit("出力するページの形式が不正です。中止します。公開はしないでください。")
    open(path, "w", encoding="utf-8").write(out)


SLUG = {"bullettrain.jp": "bt", "sd-milk.com": "mk", "mailivis.jp": "mv", "super-dragon.jp": "sd", "one-n-only.jp": "oo", "genjibu.jp": "gj", "lienel.jp": "ln"}


def slug(url):
    pre = next((v for k, v in SLUG.items() if k in url), "xx")
    return pre + "-" + url.rstrip("/").split("/")[-1]


def body_hash(lines):
    return hashlib.sha1("\n".join(lines).encode("utf-8")).hexdigest()[:16]


# ---------- check ----------
def cmd_check(page, work):
    _, data = load_page(page)
    known = data.get("articles", {})
    os.makedirs(os.path.join(work, "new"), exist_ok=True)
    listing, errors, down = {}, [], []
    # 1つのサイトが落ちていても、ほかのサイトの更新は続ける
    sources = (("超特急公式サイト", list_bullettrain), ("M!LK公式サイト", list_milk), ("SUPER★DRAGON公式サイト", list_superdragon),
               ("ONE N' ONLY公式サイト", list_onenonly), ("原因は自分にある。公式サイト", list_genjibu), ("Lienel公式サイト", list_lienel),
               ("MAILIVIS", list_mailivis))
    for name, fn in sources:
        try:
            listing.update(fn())
        except Exception as ex:
            errors.append(f"{name} の一覧を取得できませんでした（今回はこのサイトを飛ばします）: {ex}")
            down.append(name)
    errors += PARTIAL_ERRORS
    if len(down) == len(sources):
        sys.exit("どのサイトの一覧も取得できませんでした。中止します。公開はしないでください。")
    today = now_jst()
    upcoming_urls = {e["url"] for e in data["events"] if e["at"] >= today.strftime("%Y-%m-%dT%H:%M")}
    seen, todo = {}, []
    for url, e in listing.items():
        k = known.get(url)
        e["url"] = url
        if skip(e):
            continue
        recent = not e["pub"] or e["pub"] >= (today - timedelta(days=RECHECK_DAYS)).strftime("%Y-%m-%d")
        if not k and not recent:
            continue                               # 掲載から時間のたった未読の告知（グループ追加直後など）は読まない
        if k and not recent and url not in upcoming_urls:
            seen[url] = k["hash"]; continue        # 古い既読の告知は再取得しない
        try:
            lines = main_lines(get(url))
        except Exception as ex:
            errors.append(f"{url}: {ex}"); continue
        hsh = body_hash(lines)
        seen[url] = hsh
        if k and k.get("hash") == hsh:
            continue
        tags = e["site_tags"]
        if e["group"] == "超特急" and "bullettrain.jp" in url:  # 詳細ページ冒頭（掲載日より上）にサイトが付けたメンバーのタグがある
            idx = next((i for i, l in enumerate(lines[:12]) if re.fullmatch(r"20\d\d/\d\d/\d\d", l)), 0)
            tags = [m for m in GROUPS["超特急"] if m in lines[:idx]] or [m for m in GROUPS["超特急"] if m in tags]
        fn = os.path.join(work, "new", slug(url) + ".txt")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(f"URL: {url}\nグループ: {e['group']}\n掲載日: {e['pub']}\nカテゴリ: {', '.join(sorted(set(c for c in e['cats'] if c)))}\n"
                    f"サイトが付けたメンバーのタグ: {', '.join(tags) or 'なし'}\n状態: {'変更あり（前回読んだ内容から更新された）' if k else '新着'}\n"
                    f"タイトル: {e['title']}\n----- 本文 -----\n" + "\n".join(lines) + "\n")
        todo.append({"url": url, "file": fn, "group": e["group"], "title": e["title"], "chars": sum(map(len, lines))})
    json.dump({"seen": seen, "todo": todo, "errors": errors, "checked_at": today.strftime("%Y-%m-%dT%H:%M")},
              open(os.path.join(work, "check.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"一覧にある告知 {len(listing)}件 / 読み取りが必要 {len(todo)}件 / 取得エラー {len(errors)}件")
    for t in todo: print(f"  {t['file']}  ({t['chars']}字) {t['group']} {t['title'][:50]}")
    for er in errors: print("  取得エラー:", er)
    if not todo: print("NO_NEW")


# ---------- 照合 ----------
Z = str.maketrans("０１２３４５６７８９：／～", "0123456789:/〜")


def norm(s):
    return re.sub(r"\s+", "", s.translate(Z))


def dt_in_source(iso, text, need_time=True):
    """抽出した日時が本文に実在するか。月日（＋時刻）が隣り合って書かれていることを確認する"""
    d = datetime.strptime(iso, "%Y-%m-%dT%H:%M")
    cands = [(d.month, d.day, d.hour, d.minute)]
    p = d - timedelta(days=1)
    cands.append((p.month, p.day, d.hour + 24, d.minute))      # 「26:00」表記
    for mo, da, h, mi in cands:
        date = rf"(?<!\d)0?{mo}\s*[月/.]\s*0?{da}(?!\d)日?"
        pat = date + (rf"\s*(?:[（(][^）)]{{1,4}}[）)])?\s*0?{h}\s*:\s*{mi:02d}" if need_time else "")
        if re.search(pat, text): return True
        if not need_time: break
    return False


def validate(ev, group, text, tags):
    probs = []
    ntext = norm(text)
    cat = ev.get("cat")
    if cat not in KINDS or ev.get("kind") not in KINDS[cat]: probs.append(f"kind/cat が不正: {ev.get('kind')}/{cat}")
    try:
        datetime.strptime(ev["at"], "%Y-%m-%dT%H:%M")
        if ev.get("start"): datetime.strptime(ev["start"], "%Y-%m-%dT%H:%M")
    except Exception:
        return ["at/start の形式が不正"], True
    if not dt_in_source(ev["at"], text, need_time=not ev.get("allday")): probs.append(f"日時 {ev['at']} が本文にない")
    if ev.get("start") and not dt_in_source(ev["start"], text): probs.append(f"開始 {ev['start']} が本文にない")
    if ev.get("method"):
        if ev["method"] not in ("先着", "抽選"): probs.append(f"method が不正: {ev['method']}")
        elif ev["method"] not in text: probs.append(f"「{ev['method']}」の記載が本文にない")
    for m in ev.get("members", []):
        if m not in GROUPS[group]: probs.append(f"メンバー名が不正: {m}")
        elif m not in tags and m not in text: probs.append(f"メンバー {m} が本文にない")
    for q in ev.get("checks", []):
        if norm(q) not in ntext: probs.append(f"照合語句が本文にない: {q}")
    for g in ev.get("tokuten") or []:
        for r in g["rows"]:
            for q in r.get("check", []):
                if norm(q) not in ntext: probs.append(f"特典の照合語句が本文にない: {q}")
    return probs, False


# ---------- カレンダー（購読用 .ics） ----------
SITE = "https://shimelog.github.io"
CAL = {
    "超特急": ("bt", {"カイ": "kai", "リョウガ": "ryoga", "タクヤ": "takuya", "ユーキ": "yuki", "タカシ": "takashi", "シューヤ": "shuya", "マサヒロ": "masahiro", "アロハ": "aloha", "ハル": "haru"}),
    "M!LK": ("milk", {"佐野勇斗": "sano", "塩﨑太智": "shiozaki", "曽野舜太": "sono", "山中柔太朗": "yamanaka", "吉田仁人": "yoshida"}),
    "SUPER★DRAGON": ("sd", {"志村玲於": "shimura", "古川毅": "furukawa", "ジャン海渡": "jean", "飯島颯": "iijima", "伊藤壮吾": "ito", "田中洸希": "tanaka", "池田彪馬": "ikeda", "松村和哉": "matsumura", "柴崎楽": "shibasaki"}),
    "ONE N' ONLY": ("oo", {"TETTA": "tetta", "REI": "rei", "EIKU": "eiku", "HAYATO": "hayato", "NAOYA": "naoya"}),
    "原因は自分にある。": ("genjibu", {"大倉空人": "okura", "小泉光咲": "koizumi", "桜木雅哉": "sakuragi", "長野凌大": "nagano", "武藤潤": "muto", "杢代和人": "mokudai", "吉澤要人": "yoshizawa"}),
    "Lienel": ("lienel", {"芳賀柊斗": "haga", "近藤駿太": "kondo", "高岡ミロ": "takaoka", "森田璃空": "morita", "武田創世": "takeda", "高桑真之": "takakuwa"}),
}
STARTS_K = ("受付開始", "一般発売", "販売開始")


def ics_text(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_fold(line):
    b = line.encode("utf-8")
    if len(b) <= 74:
        return line
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode("utf-8")) > 73:
            out.append(cur); cur = ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n ".join(out)


def ics_event(e, stamp):
    at = datetime.strptime(e["at"], "%Y-%m-%dT%H:%M")
    uid = hashlib.sha1((e["url"] + "|" + e["kind"] + "|" + e["at"] + "|" + e.get("label", "")).encode("utf-8")).hexdigest()[:20] + "@shimelog"
    who = e["group"] + ("（" + "・".join(e["members"]) + "）" if e.get("members") else "")
    tail = "・" + e["method"] if e.get("method") else ""
    lines = ["BEGIN:VEVENT", "UID:" + uid, "DTSTAMP:" + stamp]
    if e.get("allday"):
        lines += ["DTSTART;VALUE=DATE:" + at.strftime("%Y%m%d"), "DTEND;VALUE=DATE:" + (at + timedelta(days=1)).strftime("%Y%m%d")]
    else:
        utc = at - timedelta(hours=9)
        st, en = (utc, utc + timedelta(minutes=30)) if e["kind"] in STARTS_K else (utc - timedelta(minutes=30), utc)
        lines += ["DTSTART:" + st.strftime("%Y%m%dT%H%M%SZ"), "DTEND:" + en.strftime("%Y%m%dT%H%M%SZ")]
    summary = f"【{e['kind']}{tail}】{who} {e.get('short') or e['title']}"
    desc = "\n".join(x for x in [e["title"], e.get("label", ""), e.get("event", ""), e.get("info", ""), e.get("note", ""), "公式の告知：" + e["url"], "しめろぐ（非公式）：" + SITE] if x)
    lines += ["SUMMARY:" + ics_text(summary), "DESCRIPTION:" + ics_text(desc), "URL:" + e["url"]]
    if not e.get("allday") and (e["kind"] in STARTS_K or "締切" in e["kind"]):
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + ics_text(summary), "TRIGGER:-PT1H", "END:VALARM"]
    lines.append("END:VEVENT")
    return lines


def write_calendars(page, events, today):
    d = os.path.join(os.path.dirname(os.path.abspath(page)), "cal")
    os.makedirs(d, exist_ok=True)
    stamp = (today - timedelta(hours=9)).strftime("%Y%m%dT%H%M%SZ")
    feeds = {}
    for g, (gs, ms) in CAL.items():
        ge = [e for e in events if e["group"] == g]
        feeds[gs] = (f"しめろぐ｜{g}（全員）", ge)
        for m, msl in ms.items():
            feeds[f"{gs}-{msl}"] = (f"しめろぐ｜{g}（{m}）", [e for e in ge if not e.get("members") or m in e["members"]])
    for name, (cal_name, evs) in feeds.items():
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//shimelog//JA", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
                 "X-WR-CALNAME:" + ics_text(cal_name), "X-WR-TIMEZONE:Asia/Tokyo", "X-WR-CALDESC:" + ics_text("公式の告知から拾った締切（非公式）。申し込む前に必ず公式の告知を確認してください。"),
                 "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
        for e in evs:
            lines += ics_event(e, stamp)
        lines.append("END:VCALENDAR")
        with open(os.path.join(d, name + ".ics"), "w", encoding="utf-8", newline="") as f:
            f.write("\r\n".join(ics_fold(l) for l in lines) + "\r\n")
    return len(feeds)


# ---------- merge ----------
def cmd_merge(page, work):
    h, data = load_page(page)
    chk = json.load(open(os.path.join(work, "check.json"), encoding="utf-8"))
    xp = os.path.join(work, "extracted.json")
    ext = json.load(open(xp, encoding="utf-8")) if os.path.exists(xp) else {}
    articles = data.get("articles", {})
    events = data["events"]
    today = now_jst()
    report = {"added": 0, "ng": [], "missing": [], "dropped": []}
    done_urls = set()
    for t in chk["todo"]:
        url = t["url"]
        if url not in ext:
            report["missing"].append(url); continue          # 読み取り結果がない告知は既読にせず、次回また対象にする
        src = open(t["file"], encoding="utf-8").read()
        text = re.sub(r"\s+", " ", src.split("----- 本文 -----", 1)[1].translate(Z))
        tags = [x.strip() for x in re.search(r"サイトが付けたメンバーのタグ: (.*)", src).group(1).split(",")]
        old_links = {(g["edition"], r["store"]): r["url"] for e in events if e["url"] == url for g in e.get("tokuten") or [] for r in g["rows"] if r.get("url")}
        new = []
        for ev in ext[url].get("events", []):
            probs, fatal = validate(ev, t["group"], text, tags)
            if fatal:
                report["dropped"].append(f"{url}: {probs}"); continue
            if probs: report["ng"].append(f"{url} {ev.get('kind')} {ev.get('at')}: " + " / ".join(probs))
            o = {"group": t["group"], "cat": ev["cat"], "title": ev["title"], "short": (ev.get("short") or "")[:20], "kind": ev["kind"], "at": ev["at"], "start": ev.get("start") or None,
                 "allday": bool(ev.get("allday")), "method": ev.get("method") if ev.get("method") in ("先着", "抽選") else "", "label": ev.get("label", ""), "event": ev.get("event", ""), "info": ev.get("info", ""),
                 "note": NG_NOTE if probs else "", "url": url, "members": [m for m in ev.get("members", []) if m in GROUPS[t["group"]]]}
            if ev.get("tokuten"):
                o["tokuten"] = [{"edition": g["edition"], "rows": [dict({"store": r["store"], "text": r["text"]}, **({"url": old_links[(g["edition"], r["store"])]} if (g["edition"], r["store"]) in old_links else {})) for r in g["rows"]]} for g in ev["tokuten"]]
            new.append(o)
        events = [e for e in events if e["url"] != url] + new
        report["added"] += len(new)
        done_urls.add(url)
    # 既読の記録を更新（読み取りできなかった告知は記録しない）
    for url, hsh in chk["seen"].items():
        if url in report["missing"]: continue
        articles[url] = {"hash": hsh, "listed": today.strftime("%Y-%m-%d")}
    limit = (today - timedelta(days=KEEP_PAST_DAYS)).strftime("%Y-%m-%dT%H:%M")
    events = sorted((e for e in events if e["at"] >= limit), key=lambda e: (e["at"], e["group"]))
    live = {e["url"] for e in events}
    old = (today - timedelta(days=45)).strftime("%Y-%m-%d")
    articles = {u: a for u, a in articles.items() if a.get("listed", "") >= old or u in live}
    data.update(events=events, articles=articles, groups=GROUPS, fetched_at=today.strftime("%Y-%m-%dT%H:%M"))
    if PAGE_MARK in h:
        data["cal"] = {g: {"slug": gs, "members": ms} for g, (gs, ms) in CAL.items()}
    save_page(page, h, data)
    if PAGE_MARK in h:
        print(f"カレンダー {write_calendars(page, events, today)}件を書き出しました")
    print(f"読み取った告知 {len(done_urls)}件 / 追加・更新した予定 {report['added']}件 / 掲載中の予定 {len(events)}件 / 取得日時 {data['fetched_at']}")
    for k, label in (("ng", "照合NG（「要確認」の注記つきで掲載）"), ("dropped", "形式不正で不掲載"), ("missing", "読み取り結果なし（次回に再試行）")):
        for x in report[k]: print(f"  {label}: {x}")
    for er in chk.get("errors", []): print("  取得エラー:", er)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("check", "merge"):
        sys.exit(__doc__)
    (cmd_check if sys.argv[1] == "check" else cmd_merge)(sys.argv[2], sys.argv[3])
