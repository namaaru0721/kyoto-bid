import json, os, requests
from playwright.sync_api import sync_playwright

WEBHOOK_URL = "https://webhook.worksmobile.com/message/98a5731f-7764-4495-9bc6-521fa876bcb5"
START_URL = "https://kyoto.efftis.jp/26000/CALS/PPI_P/pages/PPI_P/PiCtBaFi02/PiCtBaFi02start.vm"
CACHE_FILE = "known_links.json"

# 除外ワード（無関係な工事を排除）
EXCLUDE_KEYWORDS = ["信号", "標示", "電柱", "通学路", "治山", "舗装", "標識", "白線", "道路", "緑化", "剪定"]

# 対象ワード（管工事・機械設備に関連するもの）
INCLUDE_KEYWORDS = ["管", "機械", "設備", "空調", "衛生", "給排水", "ダクト", "ボイラー", "ポンプ", "修繕", "改修"]

def is_target_project(title):
    for ex in EXCLUDE_KEYWORDS:
        if ex in title:
            return False
            
    for inc in INCLUDE_KEYWORDS:
        if inc in title:
            return True
            
    return False

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

            # スキップ判定を外して検索ボタンを直接クリック
            btn = page.locator("input[type='submit']").or_(page.locator("input[value*='検索']")).first
            btn.click()
            page.wait_for_load_state("networkidle", timeout=60000)
            page.wait_for_timeout(3000)

            # 案件リンクの抽出と選別
            for a in page.locator("a").all():
                try:
                    title = a.inner_text().strip()
                    href = a.get_attribute("href")
                    if href and title and len(title) > 2 and "javascript" not in href:
                        if is_target_project(title):
                            url = f"https://kyoto.efftis.jp{href}" if href.startswith("/") else href
                            current[url] = title
                except:
                    continue

        except Exception as e:
            print(f"エラー発生: {e}")
        finally:
            browser.close()

    if is_first:
        save_data(current)
        msg = f"【京都府入札】Efftis「管工事・機械設備」自動監視を開始しました。\n現在検出数: {len(current)}件\n\n"
        for url, title in current.items():
            msg += f"・{title}\n{url}\n\n"
        send_line(msg)
    else:
        new_items = [{"title": t, "url": u} for u, t in current.items() if u not in saved]
        if new_items:
            msg = f"【京都府入札】「管工事・機械設備」の新着案件を検知 ({len(new_items)}件)\n\n"
            for item in new_items:
                msg += f"・{item['title']}\n{item['url']}\n\n"
            send_line(msg)
            saved.update(current)
            save_data(saved)

if __name__ == "__main__":
    run()
