import json, os, requests
from playwright.sync_api import sync_playwright

WEBHOOK_URL = "https://webhook.worksmobile.com/message/98a5731f-7764-4495-9bc6-521fa876bcb5"
START_URL = "https://kyoto.efftis.jp/26000/CALS/PPI_P/pages/PPI_P/PiCtBaFi02/PiCtBaFi02start.vm"
CACHE_FILE = "known_links.json"

def load_data():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

def save_data(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False)

def send_line(text):
    requests.post(WEBHOOK_URL, json={"title": "京都府入札(Efftis)", "body": {"text": text}})

def run():
    saved = load_data()
    is_first = len(saved) == 0
    current = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # 1. ページ読み込み
        page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)

        # 2. ドロップダウンから「管」が含まれる項目を自動選択
        select_elem = page.query_selector("select[name='syokusuCD']") or page.query_selector("select")
        if select_elem:
            options = select_elem.query_selector_all("option")
            target_val = None
            for opt in options:
                txt = opt.inner_text()
                if "管" in txt:
                    target_val = opt.get_attribute("value")
                    break
            if target_val:
                select_elem.select_option(value=target_val)

        # 3. 検索ボタンクリック
        submit_btn = page.query_selector("input[type='submit']") or page.query_selector("input[value*='検索']")
        if submit_btn:
            submit_btn.click()
            page.wait_for_load_state("domcontentloaded", timeout=60000)

        # 4. 案件一覧の取得
        for row in page.query_selector_all("tr"):
            a = row.query_selector("a")
            if a:
                title = a.inner_text().strip()
                href = a.get_attribute("href")
                if href and title and len(title) > 2:
                    url = f"https://kyoto.efftis.jp{href}" if href.startswith("/") else href
                    current[url] = title
        browser.close()

    # 5. 通知処理
    if is_first:
        save_data(current)
        send_line(f"【京都府入札】Efftis管工事の自動監視を開始しました。\n現在検出数: {len(current)}件")
        return

    new_items = [{"title": t, "url": u} for u, t in current.items() if u not in saved]
    if new_items:
        msg = f"【京都府入札】「管工事」の新着案件を検知 ({len(new_items)}件)\n\n"
        for item in new_items: msg += f"・{item['title']}\n{item['url']}\n\n"
        send_line(msg)
        saved.update(current)
        save_data(saved)

if __name__ == "__main__":
    run()
