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
        
        try:
            # 1. アクセス後、リダイレクト通信が落ち着くまで待機
            page.goto(START_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)

            # 2. ドロップダウンが表示されるまで確実に待つ
            select_loc = page.locator("select[name='syokusuCD']").or_(page.locator("select")).first
            select_loc.wait_for(state="attached", timeout=30000)

            # 3. 「管」が含まれる項目を選択
            options = select_loc.locator("option").all_inner_texts()
            for txt in options:
                if "管" in txt:
                    select_loc.select_option(label=txt)
                    break

            # 4. 検索ボタンを押す
            btn = page.locator("input[type='submit']").or_(page.locator("input[value*='検索']")).first
            btn.click()
            page.wait_for_load_state("networkidle", timeout=60000)
            page.wait_for_timeout(3000)

            # 5. 案件リンクの抽出
            for a in page.locator("a").all():
                try:
                    title = a.inner_text().strip()
                    href = a.get_attribute("href")
                    if href and title and len(title) > 2 and "javascript" not in href:
                        url = f"https://kyoto.efftis.jp{href}" if href.startswith("/") else href
                        current[url] = title
                except:
                    continue

        except Exception as e:
            print(f"ログ確認用: {e}")
        finally:
            browser.close()

    if is_first:
        save_data(current)
        send_line(f"【京都府入札】Efftis管工事の自動監視を開始しました。\n現在検出数: {len(current)}件")
    else:
        new_items = [{"title": t, "url": u} for u, t in current.items() if u not in saved]
        if new_items:
            msg = f"【京都府入札】「管工事」の新着案件を検知 ({len(new_items)}件)\n\n"
            for item in new_items: msg += f"・{item['title']}\n{item['url']}\n\n"
            send_line(msg)
            saved.update(current)
            save_data(saved)

if __name__ == "__main__":
    run()
