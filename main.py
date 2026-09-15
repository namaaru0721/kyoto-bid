import json, os, requests, re
from playwright.sync_api import sync_playwright

WEBHOOK_URL = "https://webhook.worksmobile.com/message/98a5731f-7764-4495-9bc6-521fa876bcb5"
START_URL = "https://kyoto.efftis.jp/26000/CALS/PPI_P/pages/PPI_P/PiCtBaFi02/PiCtBaFi02start.vm"
CACHE_FILE = "known_links.json"

INCLUDE_KEYWORDS = ["管", "機械", "設備", "空調", "衛生", "給排水", "水洗", "ダクト", "ボイラー", "ポンプ", "修繕", "改修", "浄化センター"]
EXCLUDE_KEYWORDS = ["信号", "標示", "電柱", "通学路", "治山", "舗装", "標識", "白線", "道路", "緑化", "剪定", "橋梁", "落石"]

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
    requests.post(WEBHOOK_URL, json={"title": "京都府・市入札(Efftis)", "body": {"text": text}})

def run():
    saved = load_data()
    is_first = len(saved) == 0
    current = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)

            # 1. 各種検索ボタン（画像・ボタン・入力フォーム）を強力に検索してクリック
            btn_clicked = False
            for frame in page.frames:
                search_btn = frame.locator("input[type='submit'], input[type='image'], input[value*='検索'], img[alt*='検索'], a:has-text('検索')").first
                if search_btn.count() > 0:
                    search_btn.click()
                    btn_clicked = True
                    print("フレーム内の検索ボタンをクリックしました。")
                    break
            
            if not btn_clicked:
                search_btn = page.locator("input[type='submit'], input[type='image'], input[value*='検索'], img[alt*='検索'], a:has-text('検索')").first
                if search_btn.count() > 0:
                    search_btn.click()
                    print("メインページの検索ボタンをクリックしました。")

            page.wait_for_timeout(6000)

            # 2. 全フレーム内の <a> および <td> 要素からテキストを抽出
            frames_to_check = page.frames if page.frames else [page]
            total_elements = 0

            for frame in frames_to_check:
                elements = frame.locator("a, td").all()
                total_elements += len(elements)
                
                for el in elements:
                    try:
                        text = re.sub(r'\s+', ' ', el.inner_text()).strip()
                        if text and len(text) > 3:
                            if is_target_project(text):
                                current[text] = text
                    except:
                        continue

            print(f"スキャン対象要素数: {total_elements} 件")

        except Exception as e:
            print(f"エラー発生: {e}")
        finally:
            browser.close()

    print(f"【判定結果】該当案件数: {len(current)}件")

    if is_first:
        save_data(current)
        if current:
            msg = f"【京都入札】Efftis「管工事・機械設備」自動監視を開始しました。\n現在検出数: {len(current)}件\n\n"
            for title in current.keys():
                msg += f"・{title}\n\n"
            send_line(msg)
            print("初回通知を送信しました。")
        else:
            print("初回実行: 該当案件は0件でした。")
    else:
        new_items = [t for t in current.keys() if t not in saved]
        if new_items:
            msg = f"【京都入札】「管工事・機械設備」の新着案件を検知 ({len(new_items)}件)\n\n"
            for title in new_items:
                msg += f"・{title}\n\n"
            send_line(msg)
            saved.update(current)
            save_data(saved)
            print(f"新着{len(new_items)}件の通知を送信しました。")
        else:
            print("新着案件はありませんでした。")

if __name__ == "__main__":
    run()
