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

    target_keywords = [
        "管工事", "給水", "排水", "給排水", "空調", 
        "冷暖房", "換気", "衛生", "受水槽", "配管", 
        "ダクト", "エアコン", "機械設備"
    ]
    ignore_keywords = ["道路標示", "清掃", "草刈"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            page.goto(START_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2000)

            # 条件指定せず検索実行（入札課・全振興局・土木事務所の公告が一括表示される）
            btn = page.locator("input[type='submit']").or_(page.locator("input[value*='検索']")).first
            if btn.count() > 0:
                btn.click()
                page.wait_for_load_state("networkidle", timeout=60000)
                page.wait_for_timeout(3000)

            # 検索結果の全ページ（1ページ目〜最終ページ）を連続スキャン
            while True:
                targets = [page] + page.frames
                for target in targets:
                    try:
                        rows = target.locator("tr")
                        for i in range(rows.count()):
                            row = rows.nth(i)
                            text = row.inner_text().replace("\n", " ")
                            
                            if any(ig in text for ig in ignore_keywords):
                                continue
                            
                            if any(kw in text for kw in target_keywords) and "No." not in text:
                                tds = row.locator("td")
                                if tds.count() >= 3:
                                    title = tds.nth(2).inner_text().replace("\n", " ").strip()
                                    if len(title) > 3:
                                        current[title] = START_URL
                    except:
                        continue

                # 次ページボタンがあればクリックして進む
                has_next = False
                for target in targets:
                    next_btn = target.locator("a:has-text('次へ'), input[value*='次'], a:has-text('次ページ')")
                    if next_btn.count() > 0 and next_btn.first.is_visible():
                        next_btn.first.click()
                        page.wait_for_load_state("networkidle", timeout=30000)
                        page.wait_for_timeout(2000)
                        has_next = True
                        break
                
                if not has_next:
                    break

        except Exception as e:
            print(f"エラー発生: {e}")
        finally:
            browser.close()

    if is_first:
        save_data(current)
        msg = f"【京都府入札】Efftis全庁の管工事・受水槽監視を開始しました。\n現在検出数: {len(current)}件\n\n"
        if current:
            for title in current.keys():
                msg += f"・{title}\n{START_URL}\n\n"
        else:
            msg += "※現在、該当する公告案件はありません。"
        send_line(msg)
    else:
        new_items = [t for t in current.keys() if t not in saved]
        if new_items:
            msg = f"【京都府入札】新着案件を検知 ({len(new_items)}件)\n\n"
            for title in new_items:
                msg += f"・{title}\n{START_URL}\n\n"
            send_line(msg)
            saved.update(current)
            save_data(saved)

if __name__ == "__main__":
    run()
