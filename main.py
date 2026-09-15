import json, os, requests, re
from playwright.sync_api import sync_playwright

WEBHOOK_URL = "https://webhook.worksmobile.com/message/98a5731f-7764-4495-9bc6-521fa876bcb5"
START_URL = "https://kyoto.efftis.jp/26000/CALS/PPI_P/pages/PPI_P/PiCtBaFi02/PiCtBaFi02start.vm"
CACHE_FILE = "known_links.json"

# テスト送信（全件強制通知）フラグ
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
            page.goto(START_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)

            # 1. 検索実行（JS実行 & ボタンクリックの両方に対応）
            search_done = False
            for frame in page.frames:
                try:
                    # JavaScriptで直接フォーム送信を起動
                    frame.evaluate("if(typeof doSearch === 'function'){ doSearch(); } else if(document.forms[0]){ document.forms[0].submit(); }")
                    search_done = True
                    print("JavaScript経由で検索を実行しました。")
                    break
                except:
                    pass

            if not search_done:
                for frame in page.frames:
                    btn = frame.locator("input[value*='検'], input[type='submit']").first
                    if btn.count() > 0:
                        btn.click(force=True)
                        print("ボタン直接クリックで検索を実行しました。")
                        break

            # 2. 結果テーブルの表示（「案件名称」テキストの出現）を最大15秒待機
            page.wait_for_timeout(7000)
            
            # 3. 全フレームから「案件名称」が含まれるテーブルの行を優先解析
            found_rows = 0
            for idx, frame in enumerate(page.frames):
                rows = frame.locator("tr").all()
                for row in rows:
                    try:
                        text = re.sub(r'\s+', ' ', row.inner_text()).strip()
                        # 表の見出し行やフォーム行を除外し、案件情報を取得
                        if "案件名称" not in text and len(text) > 15:
                            found_rows += 1
                            if is_target_project(text):
                                current[text] = text
                    except:
                        continue

            print(f"スキャン対象案件行数: {found_rows} 行")

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
                    msg += f"・{raw_text[:120]}\n\n"
                send_line(msg)
            print("LINEへの通知送信を完了しました。")
        else:
            print("該当案件は0件でした。")
    else:
        new_items = [t for t in current.keys() if t not in saved]
        if new_items:
            msg = f"【京都府(Efftis)】新着案件を検知 ({len(new_items)}件)\n\n"
            for raw_text in new_items:
                msg += f"・{raw_text[:120]}\n\n"
            send_line(msg)
        save_data(current)

if __name__ == "__main__":
    run()
