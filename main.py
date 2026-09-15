import json, os, requests, re
from playwright.sync_api import sync_playwright

WEBHOOK_URL = "https://webhook.worksmobile.com/message/98a5731f-7764-4495-9bc6-521fa876bcb5"
START_URL = "https://kyoto.efftis.jp/26000/CALS/PPI_P/pages/PPI_P/PiCtBaFi02/PiCtBaFi02start.vm"
CACHE_FILE = "known_links.json"

# テスト送信用に True に設定中（確認完了後に False に戻してください）
FORCE_OVERWRITE = True

INCLUDE_KEYWORDS = ["管工事", "機械", "設備", "空調", "衛生", "給排水", "水洗", "ダクト", "ボイラー", "ポンプ", "修繕", "改修", "更新", "浄化センター"]
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
        res = requests.post(WEBHOOK_URL, json={"title": "京都府入札(Efftis)", "body": {"text": text}})
        print(f"LINE送信結果: {res.status_code}")
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
            page.wait_for_timeout(4000)

            # 1. 全フレームを巡回して検索ボタンをクリック
            clicked = False
            for frame in page.frames:
                for selector in ["input[value*='検']", "input[type='submit']", "img[alt*='検']", "button"]:
                    btn = frame.locator(selector).first
                    if btn.count() > 0:
                        btn.click(force=True)
                        clicked = True
                        print(f"フレーム内で検索ボタンを検出・クリックしました: Selector={selector}")
                        break
                if clicked:
                    break

            # 2. 結果画面（新規フレーム）のレンダリング待ち
            page.wait_for_timeout(8000)

            # 3. 再最新化した全フレームからテーブル行を取得
            all_frames = page.frames
            print(f"検出対象フレーム数: {len(all_frames)}")

            for idx, frame in enumerate(all_frames):
                rows = frame.locator("tr").all()
                print(f"フレーム[{idx}] 内の行数: {len(rows)}")
                
                for row in rows:
                    try:
                        text = re.sub(r'\s+', ' ', row.inner_text()).strip()
                        if len(text) > 8 and is_target_project(text):
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
            items = list(current.keys())
            batch_size = 5
            for i in range(0, len(items), batch_size):
                chunk = items[i:i + batch_size]
                msg = f"【京都府(Efftis)】「管工事・設備」自動監視を更新しました ({i+1}~{i+len(chunk)}件 / 全{len(items)}件)\n\n"
                for raw_text in chunk:
                    msg += f"・{raw_text[:100]}\n\n"
                send_line(msg)
            print("LINEへの分割送信を完了しました。")
        else:
            print("該当案件は0件でした。")
    else:
        new_items = [t for t in current.keys() if t not in saved]
        if new_items:
            msg = f"【京都府(Efftis)】新着案件を検知 ({len(new_items)}件)\n\n"
            for raw_text in new_items:
                msg += f"・{raw_text[:100]}\n\n"
            send_line(msg)
        save_data(current)

if __name__ == "__main__":
    run()
