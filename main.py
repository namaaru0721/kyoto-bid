import json, os, requests, re
from playwright.sync_api import sync_playwright

WEBHOOK_URL = "https://webhook.worksmobile.com/message/98a5731f-7764-4495-9bc6-521fa876bcb5"
START_URL = "https://kyoto.efftis.jp/26000/CALS/PPI_P/pages/PPI_P/PiCtBaFi02/PiCtBaFi02start.vm"
CACHE_FILE = "known_links.json"

# テスト時や強制再通知したい場合は True に変更
FORCE_OVERWRITE = False

INCLUDE_KEYWORDS = ["管工事", "機械", "設備", "空調", "衛生", "給排水", "水洗", "ダクト", "ボイラー", "ポンプ", "修繕", "改修", "浄化センター"]
EXCLUDE_KEYWORDS = ["管内一円", "インフラ保全", "信号", "標示", "電柱", "通学路", "治山", "舗装", "標識", "白線", "道路", "緑化", "剪定", "橋梁", "落石"]

def is_target_project(title):
    for ex in EXCLUDE_KEYWORDS:
        if ex in title:
            return False
    for inc in INCLUDE_KEYWORDS:
        if inc in title:
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
        requests.post(WEBHOOK_URL, json={"title": "京都府入札(Efftis)", "body": {"text": text}})
    except Exception as e:
        print(f"LINE送信エラー: {e}")

def run():
    saved = load_data()
    is_first = len(saved) == 0 or FORCE_OVERWRITE
    current = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            # 全フレームからEfftis特有の検索ボタンを探してクリック
            btn_clicked = False
            for frame in page.frames:
                btn = frame.locator("input[value*='検'], input[value*='検索'], input[type='submit'], img[alt*='検索']").first
                if btn.count() > 0:
                    btn.click()
                    btn_clicked = True
                    print("検索ボタンをクリックしました。")
                    break

            # 一覧テーブルの読み込み待ち
            page.wait_for_timeout(6000)

            # 一覧表の全行（tr）を取得して「管工事・設備案件」を抽出
            frames_to_check = page.frames if page.frames else [page]
            for frame in frames_to_check:
                rows = frame.locator("tr").all()
                for row in rows:
                    try:
                        text = re.sub(r'\s+', ' ', row.inner_text()).strip()
                        if len(text) > 10 and is_target_project(text):
                            current[text] = text
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
            msg = f"【京都府(Efftis)】「管工事・設備」自動監視を開始しました。\n現在検出数: {len(current)}件\n\n"
            for raw_text in current.keys():
                # 表示用に余分な空白を調整
                clean_text = raw_text[:120]
                msg += f"・{clean_text}\n\n"
            send_line(msg)
            print("初回/上書き通知を送信しました。")
        else:
            print("該当案件は0件でした。")
    else:
        new_items = [t for t in current.keys() if t not in saved]
        if new_items:
            msg = f"【京都府(Efftis)】新着案件を検知 ({len(new_items)}件)\n\n"
            for raw_text in new_items:
                clean_text = raw_text[:120]
                msg += f"・{clean_text}\n\n"
            send_line(msg)
            print(f"新着{len(new_items)}件の通知を送信しました。")
        else:
            print("新着案件はありませんでした。")
            
        save_data(current)

if __name__ == "__main__":
    run()
