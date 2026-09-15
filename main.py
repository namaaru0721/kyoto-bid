import json, os, requests, re
from playwright.sync_api import sync_playwright

WEBHOOK_URL = "https://webhook.worksmobile.com/message/98a5731f-7764-4495-9bc6-521fa876bcb5"
START_URL = "https://kyoto.efftis.jp/26000/CALS/PPI_P/pages/PPI_P/PiCtBaFi02/PiCtBaFi02start.vm"
CACHE_FILE = "known_links.json"

FORCE_OVERWRITE = True
MAX_PAGES = 30

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

def scan_rows(frame):
    texts = []
    rows = frame.locator("tr").all()
    for row in rows:
        try:
            raw_text = row.inner_text()
            text = re.sub(r'\s+', ' ', raw_text).strip()
            if len(text) > 10:
                texts.append(text)
        except:
            continue
    return texts

def go_to_next_page(frame, current_page_num):
    """<a>タグに限定してページ送りリンクを探す（表内の数字セルとの誤認を防ぐ）"""
    next_num = str(current_page_num + 1)
    target_texts = [f"{next_num}ページ目", next_num]
    links = frame.locator("a")
    count = links.count()
    for i in range(count):
        link = links.nth(i)
        try:
            text = link.inner_text().strip()
        except:
            continue
        if text in target_texts:
            try:
                link.click(force=True)
                print(f"<a>タグ '{text}'（{i}番目のリンク）をクリックしました。")
                return True
            except Exception as e:
                print(f"クリック失敗: {e}")
                continue
    return False

def run():
    saved = load_data()
    is_first = len(saved) == 0 or FORCE_OVERWRITE
    current = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            print("Efftis初期画面へアクセス中...")
            page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            for frame in page.frames:
                btn = frame.locator("input[value*='検'], input[alt*='検'], input[type='submit']").first
                if btn.count() > 0:
                    btn.click(force=True)
                    print("検索ボタンをクリックしました。")
                    break

            page.wait_for_timeout(8000)

            target_frame = None
            for frame in page.frames:
                try:
                    body_text = frame.inner_text("body")
                    if "工事場所" in body_text or "資料配布" in body_text or "案件名称" in body_text:
                        target_frame = frame
                        print(f"結果テーブルを含むフレームを特定しました: {frame.url}")
                        break
                except:
                    continue

            if target_frame is None:
                target_frame = page.main_frame

            total_scanned = 0
            page_num = 1
            prev_first_row = None

            while page_num <= MAX_PAGES:
                print(f"--- {page_num}ページ目をスキャン中 ---")
                texts = scan_rows(target_frame)

                # ページが本当に切り替わったかチェック（表の1件目の内容で比較）
                data_rows = [t for t in texts if re.match(r'^\d+\s', t)]
                current_first_row = data_rows[0] if data_rows else None
                if page_num > 1 and current_first_row == prev_first_row:
                    print(f"警告: {page_num}ページ目の内容が前ページと同一です。ページ送りが実際には機能していない可能性があります。処理を中断します。")
                    break
                prev_first_row = current_first_row

                for text in texts:
                    total_scanned += 1
                    print(f"取得サンプル[{total_scanned}]: {text[:150]}")
                    if is_target_project(text):
                        current[text] = text

                moved = go_to_next_page(target_frame, page_num)
                if not moved:
                    print(f"{page_num}ページ目で次のページが見つからないため終了します。")
                    break
                page.wait_for_timeout(3000)
                page_num += 1

            print(f"総スキャン行数: {total_scanned}行 ／ 総スキャンページ数: {page_num}ページ")

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
