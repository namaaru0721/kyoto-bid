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
FORCE_OVERWRITE = True

# 「種目」が以下に完全一致する案件のみを対象とする
ALWAYS_TARGET_TYPES = ["管工事", "機械設備工事"]


def extract_project_type(text):
    """
    行のテキストから「種目」欄を抽出する。
    形式: <公告日(YYYY.MM.DD)> <入札No.> <種目> <案件名...> <期日>
    種目は日付・入札No.の直後にある、空白を含まない1トークン。
    """
    m = re.match(r'^\d{4}\.\d{2}\.\d{2}\s+\S+\s+(\S+)\s+', text)
    if m:
        return m.group(1)
    return None


def is_target(text):
    project_type = extract_project_type(text)
    if project_type is None:
        return False, None
    if project_type in ALWAYS_TARGET_TYPES:
        return True, f"種目「{project_type}」は対象"
    return False, None


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
                        if len(text) <= 5:
                            continue

                        matched, reason = is_target(text)
                        if matched:
                            print(f"[該当] {reason} : {text[:150]}")
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
            header = "【京都市単独・交通局】「管工事」監視を開始しました"
            send_in_batches(header, current)
    else:
        new_items = {k: v for k, v in current.items() if k not in saved}
        if new_items:
            header = f"【京都市単独・交通局】新着案件を検知 ({len(new_items)}件)"
            send_in_batches(header, new_items)
            
        save_data(current)

if __name__ == "__main__":
    run()
