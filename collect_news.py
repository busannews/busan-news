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
MAX_NEWS = 200
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

# Firebase 요청 공통 함수
def firebase_request(path, method='GET', data=None):
    safe_path = urllib.parse.quote(path, safe='/')
    url = f"{FIREBASE_URL}/{safe_path}.json"
    payload = None
    headers = {}
    if data is not None:
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json; charset=utf-8'
    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def firebase_get(path):
    try:
        return firebase_request(path, 'GET')
    except Exception as e:
        print(f"GET 오류 ({path}): {e}")
        return None

def firebase_patch(path, data):
    try:
        return firebase_request(path, 'PATCH', data)
    except Exception as e:
        print(f"PATCH 오류 ({path}): {e}")

def firebase_put(path, data):
    try:
        return firebase_request(path, 'PUT', data)
    except Exception as e:
        print(f"PUT 오류 ({path}): {e}")

def firebase_delete(path):
    try:
        return firebase_request(path, 'DELETE')
    except Exception as e:
        print(f"DELETE 오류 ({path}): {e}")

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

    # 기존 seenIds 가져오기
    seen_data = firebase_get('seenIds') or {}
    seen_ids = set(seen_data.keys())
    print(f"기존 수집된 ID 수: {len(seen_ids)}")

    # 모든 피드 수집
    all_items = []
    for feed in FEEDS:
        items = fetch_feed(feed)
        all_items.extend(items)
        time.sleep(1)

    # 새 항목만 필터링
    new_items = [item for item in all_items if item['id'] not in seen_ids]
    print(f"새 뉴스: {len(new_items)}개")

    if new_items:
        news_patch = {item['id']: item for item in new_items}
        firebase_patch('news', news_patch)
        seen_patch = {item['id']: True for item in new_items}
        firebase_patch('seenIds', seen_patch)
        print(f"Firebase 저장 완료: {len(new_items)}개")

    # 200개 초과시 오래된 것 정리
    all_news = firebase_get('news') or {}
    if len(all_news) > MAX_NEWS:
        sorted_news = sorted(all_news.items(), key=lambda x: x[1].get('savedTs', 0), reverse=True)
        to_delete = sorted_news[MAX_NEWS:]
        print(f"오래된 뉴스 {len(to_delete)}개 정리 중...")
        for key, _ in to_delete:
            firebase_delete(f'news/{key}')
        print("정리 완료")

    # 마지막 수집 시각 업데이트
    now_kst = datetime.now(KST)
    last_collected = f"{now_kst.month}/{now_kst.day} {now_kst.hour}:{now_kst.minute:02d} KST"
    firebase_put('meta', {'lastCollected': last_collected})
    print(f"수집 완료: {last_collected}")
    print("=== 완료 ===")

if __name__ == '__main__':
    main()
