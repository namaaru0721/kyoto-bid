import json, os, requests, re
from playwright.sync_api import sync_playwright

WEBHOOK_URL = "https://webhook.worksmobile.com/message/98a5731f-7764-4495-9bc6-521fa876bcb5"
START_URL = "https://kyoto.efftis.jp/26000/CALS/PPI_P/pages/PPI_P/PiCtBaFi02/PiCtBaFi02start.vm"
CACHE_FILE = "known_links.json"

# 対象キーワード（管工事・機械設備関連）
INCLUDE_KEYWORDS = ["管", "機械", "設備", "空調", "衛生", "給排水", "水洗", "ダクト", "ボイラー", "ポンプ", "修繕", "改修", "浄化センター"]

# 除外キーワード（無関係な工事を排除）
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
            # ページ読み込み（タイムアウト防止）
            page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)

            # 全フレームから検索ボタンを探して押す
            btn_clicked = False
            for frame in page.frames:
                btn = frame.locator("input[type='submit']").or_(frame.locator("input[value*='検索']")).first
                if btn.count() > 0:
                    btn.click()
                    btn_clicked = True
                    break
            
            if not btn_clicked:
                btn = page.locator("input[type='submit']").or_(page.locator("input[value*='検索']")).first
                if btn.count() > 0:
                    btn.click()

            page.wait_for_timeout(5000)

            # メインページおよび全フレーム内のリンク・テキストを取得
            frames_to_check = page.frames if page.frames else [page]
            for frame in frames_to_check:
                for a in frame.locator("a").all():
                    try:
                        title = re.sub(r'\s+', ' ', a.inner_text()).strip()
                        
                        # 3文字以上かつ対象キーワードにマッチするか確認
                        if title and len(title) > 3:
                            if is_target_project(title):
                                current[title] = title
                    except:
                        continue

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
