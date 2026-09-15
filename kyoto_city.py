import json, os, requests, re
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin

WEBHOOK_URL = "https://webhook.worksmobile.com/message/98a5731f-7764-4495-9bc6-521fa876bcb5"

TARGET_URLS = [
    "https://www2.nyusatsu.city.kyoto.lg.jp/keiyaku/ebid/kouji/koukoku_kouji2026.htm",
    "https://www2.nyusatsu.city.kyoto.lg.jp/kotsu/ebid/kouji/koukoku_kouji2026.htm"
]
CACHE_FILE = "kyoto_city_cache.json"

# 強制再通知フラグ（Trueで全件強制送信）
FORCE_OVERWRITE = False

INCLUDE_KEYWORDS = ["管工事", "機械", "設備", "空調", "衛生", "給排水", "ダクト", "ボイラー", "ポンプ"]

def is_target(text):
    for inc in INCLUDE_KEYWORDS:
        if inc in text:
            return True
    return False

def load_data():
    if not FORCE_OVERWRITE and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

def save_data(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def send_line(text):
    try:
        res = requests.post(WEBHOOK_URL, json={"title": "京都市入札(単独・交通局)", "body": {"text": text}})
        print(f"LINE送信ステータス: {res.status_code}")
    except Exception as e:
        print(f"LINE送信エラー: {e}")

def send_in_batches(header, items_dict):
    items = list(items_dict.items())
    batch_size = 5
    for i in range(0, len(items), batch_size):
        chunk = items[i:i + batch_size]
        msg = f"{header} ({i+1}~{i+len(chunk)}件 / 全{len(items)}件)\n\n"
        for title, url in chunk:
            msg += f"・{title}\n{url}\n\n"
        send_line(msg)

def run():
    saved = load_data()
    is_first = len(saved) == 0 or FORCE_OVERWRITE
    current = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        for start_url in TARGET_URLS:
            try:
                page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)

                rows = page.locator("tr").all()
                for row in rows:
                    try:
                        text = re.sub(r'\s+', ' ', row.inner_text()).strip()
                        if len(text) > 5 and is_target(text):
                            links = row.locator("a").all()
                            if links:
                                href = links[0].get_attribute("href")
                                url = urljoin(start_url, href)
                            else:
                                url = start_url
                                
                            current[text] = url
                    except:
                        continue

            except Exception as e:
                print(f"エラー発生 ({start_url}): {e}")
                
        browser.close()

    print(f"【判定結果】該当案件数: {len(current)}件")

    if is_first:
        save_data(current)
        if current:
            header = "【京都市単独・交通局】「管工事・設備」監視を開始しました"
            send_in_batches(header, current)
    else:
        new_items = {k: v for k, v in current.items() if k not in saved}
        if new_items:
            header = f"【京都市単独・交通局】新着案件を検知 ({len(new_items)}件)"
            send_in_batches(header, new_items)
            
        save_data(current)

if __name__ == "__main__":
    run()
