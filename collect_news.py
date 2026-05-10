import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import re
import time
import hashlib
from datetime import datetime, timezone, timedelta

FEEDS = [
    {'keyword': '정이한',   'keyword_en': 'jungihan',    'url': 'https://www.google.com/alerts/feeds/18149858932748856698/13338804319013329313'},
    {'keyword': '전재수',   'keyword_en': 'jeonjaesu',   'url': 'https://www.google.com/alerts/feeds/18149858932748856698/13383878750521337790'},
    {'keyword': '박형준',   'keyword_en': 'parkhyungjun','url': 'https://www.google.com/alerts/feeds/18149858932748856698/13383878750521335879'},
    {'keyword': '부산시장', 'keyword_en': 'busanmayor',  'url': 'https://www.google.com/alerts/feeds/18149858932748856698/13084999270825031080'},
]

FIREBASE_URL = "https://busan-news-default-rtdb.asia-southeast1.firebasedatabase.app"
MAX_NEWS = 500
KST = timezone(timedelta(hours=9))

def strip_html(text):
    text = re.sub(r'<[^>]+>', '', text or '')
    for old, new in [('&quot;','"'),('&amp;','&'),('&#39;',"'"),('&lt;','<'),('&gt;','>')]:
        text = text.replace(old, new)
    return text.strip()

def format_saved_at():
    now = datetime.now(KST)
    return f"{now.month}/{now.day} {now.hour}:{now.minute:02d}"

def make_id(keyword_en, raw):
    h = hashlib.md5(raw.encode('utf-8')).hexdigest()[:16]
    return f"{keyword_en}_{h}"

def firebase_get(path):
    try:
        url = f"{FIREBASE_URL}/{path}.json"
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"GET 오류: {e}")
        return None

def firebase_put(path, data):
    try:
        url = f"{FIREBASE_URL}/{path}.json"
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(url, data=payload, method='PUT',
                                     headers={'Content-Type': 'application/json; charset=utf-8'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"PUT 오류: {e}")
        return None

def fetch_feed(feed):
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0)'}
    req = urllib.request.Request(feed['url'], headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
    except Exception as e:
        print(f"[{feed['keyword']}] 피드 오류: {e}")
        return []

    ns = {'atom': 'http://www.w3.org/2005/Atom'}
    try:
        root = ET.fromstring(xml_data)
    except Exception as e:
        print(f"[{feed['keyword']}] XML 파싱 오류: {e}")
        return []

    entries = root.findall('atom:entry', ns)
    at = format_saved_at()
    ts = int(time.time() * 1000)
    items = []
    for i, entry in enumerate(entries[:20]):
        title = strip_html(entry.findtext('atom:title', '', ns))
        link_el = entry.find('atom:link', ns)
        link = link_el.get('href', '') if link_el is not None else ''
        content = strip_html(entry.findtext('atom:content', '', ns))
        source_el = entry.find('atom:source', ns)
        source = source_el.findtext('atom:title', 'Google Alerts', ns) if source_el is not None else 'Google Alerts'
        raw_id = entry.findtext('atom:id', link, ns)
        item_id = make_id(feed['keyword_en'], raw_id)
        if not title:
            continue
        items.append({
            'keyword': feed['keyword'],
            'title': title,
            'url': link,
            'desc': content[:120] + ('...' if len(content) > 120 else ''),
            'source': source,
            'savedAt': at,
            'savedTs': ts - i,
            'id': item_id
        })
    print(f"[{feed['keyword']}] {len(items)}개 수집")
    return items

def main():
    print("=== 뉴스 수집 시작 ===")

    existing_news = firebase_get('news') or {}
    # 영문 키만 유효 (한글 키 제거)
    clean_existing = {k: v for k, v in existing_news.items() if not any(ord(c) > 127 for c in k)}
    seen_ids = set(clean_existing.keys())
    print(f"기존 뉴스: {len(clean_existing)}개")

    all_items = []
    for feed in FEEDS:
        items = fetch_feed(feed)
        all_items.extend(items)
        time.sleep(1)

    new_items = [item for item in all_items if item['id'] not in seen_ids]
    print(f"새 뉴스: {len(new_items)}개")

    merged = dict(clean_existing)
    for item in new_items:
        merged[item['id']] = item

    if len(merged) > MAX_NEWS:
        sorted_items = sorted(merged.items(), key=lambda x: x[1].get('savedTs', 0), reverse=True)
        merged = dict(sorted_items[:MAX_NEWS])
        print(f"500개 초과 → {MAX_NEWS}개로 정리")

    firebase_put('news', merged)
    print(f"Firebase 저장: 총 {len(merged)}개")

    now_kst = datetime.now(KST)
    last_collected = f"{now_kst.month}/{now_kst.day} {now_kst.hour}:{now_kst.minute:02d} KST"
    firebase_put('meta', {'lastCollected': last_collected})
    print(f"완료: {last_collected}")
    print("=== 완료 ===")

if __name__ == '__main__':
    main()
