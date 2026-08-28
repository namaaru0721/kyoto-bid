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
            page.goto(START_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)

            # 業種「管」を選択
            select_loc = page.locator("select[name='syokusuCD']").or_(page.locator("select")).first
            select_loc.wait_for(state="attached", timeout=30000)

            options = select_loc.locator("option").all_inner_texts()
            for txt in options:
                if "管" in txt:
                    select_loc.select_option(label=txt)
                    break

            # 検索実行
            btn = page.locator("input[type='submit']").or_(page.locator("input[value*='検索']")).first
            btn.click()
            page.wait_for_load_state("networkidle", timeout=60000)
            page.wait_for_timeout(3000)

            # 表の各行から「案件名称(3列目)」と「種別(5列目)」を直接読み取る
            rows = page.locator("table tr").all()
            for row in rows:
                try:
                    tds = row.locator("td").all()
                    if len(tds) >= 5:
                        title = tds[2].inner_text().replace("\n", " ").strip()
                        category = tds[4].inner_text().strip()
                        
                        # 種別が「管工事」またはタイトルに管工事関連が含まれる場合を検出
                        if ("管" in category or "管" in title) and len(title) > 3:
                            current[title] = START_URL
                except:
                    continue

        except Exception as e:
            print(f"エラー発生: {e}")
        finally:
            browser.close()

    # LINE通知処理
    if is_first:
        save_data(current)
        msg = f"【京都府入札】Efftis管工事の自動監視を開始しました。\n現在検出数: {len(current)}件\n\n"
        if current:
            for title in current.keys():
                msg += f"・{title}\n{START_URL}\n\n"
        else:
            msg += "※現在、該当する公告案件はありません。"
        send_line(msg)
    else:
        new_items = [t for t in current.keys() if t not in saved]
        if new_items:
            msg = f"【京都府入札】「管工事」の新着案件を検知 ({len(new_items)}件)\n\n"
            for title in new_items:
                msg += f"・{title}\n{START_URL}\n\n"
            send_line(msg)
            saved.update(current)
            save_data(saved)

if __name__ == "__main__":
    run()
