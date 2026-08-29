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
            page.wait_for_timeout(2000)

            target_frame = page
            for frame in page.frames:
                if frame.locator("select").count() > 0:
                    target_frame = frame
                    break

            # 発注機関の限定を解除し、業種「管」を選択
            selects = target_frame.locator("select").all()
            for sel in selects:
                name = sel.get_attribute("name") or ""
                # 業種以外の選択肢（発注機関など）は先頭の「指定なし(全庁)」に戻す
                if "syoku" not in name.lower() and "gyo" not in name.lower():
                    try:
                        sel.select_option(index=0)
                    except:
                        pass
                else:
                    options = sel.locator("option").all()
                    for opt in options:
                        txt = opt.inner_text().strip()
                        if "管" in txt and "管理" not in txt:
                            val = opt.get_attribute("value")
                            if val:
                                sel.select_option(value=val)
                            else:
                                sel.select_option(label=txt)
                            break

            # 検索ボタンをクリック
            btn = target_frame.locator("input[type='submit']").or_(target_frame.locator("input[value*='検索']")).first
            if btn.count() > 0:
                btn.click()
                page.wait_for_load_state("networkidle", timeout=60000)
                page.wait_for_timeout(3000)

            # 結果の全ページ走査
            while True:
                frames = [page] + page.frames
                for frame in frames:
                    try:
                        rows = frame.locator("tr")
                        for i in range(rows.count()):
                            row = rows.nth(i)
                            tds = row.locator("td")
                            if tds.count() >= 3:
                                text = row.inner_text().replace("\n", " ")
                                if "No." not in text and "戻る" not in text:
                                    dept = tds.nth(1).inner_text().replace("\n", " ").strip() if tds.count() >= 2 else ""
                                    title = tds.nth(2).inner_text().replace("\n", " ").strip()
                                    if len(title) > 3:
                                        full_name = f"【{dept}】{title}" if dept else title
                                        current[full_name] = START_URL
                    except:
                        continue

                has_next = False
                for frame in frames:
                    next_btn = frame.locator("a:has-text('次へ'), input[value*='次'], a:has-text('次ページ')")
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
        msg = f"【京都府入札】全庁（入札課・教育庁・警察本部・全土木）の自動監視を開始しました。\n現在検出数: {len(current)}件\n\n"
        if current:
            for title in current.keys():
                msg += f"・{title}\n{START_URL}\n\n"
        else:
            msg += "※現在、該当する「管工事」案件はありません。"
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
