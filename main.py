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

def debug_dump_links(frame):
    """全リンクのテキストとhref/onclickを出力して、ページ送りリンクの正体を突き止める"""
    try:
        links = frame.locator("a").all()
        print(f"--- リンク一覧（{len(links)}件） ---")
        for i, link in enumerate(links):
            try:
                text = link.inner_text().strip()
                href = link.get_attribute("href") or ""
                onclick = link.get_attribute("onclick") or ""
                if text or href or onclick:
                    print(f"link[{i}] text='{text}' href='{href[:60]}' onclick='{onclick[:80]}'")
            except:
                continue
    except Exception as e:
        print(f"リンク一覧取得失敗: {e}")

def go_to_next_page(frame, current_page_num):
    next_num = str(current_page_num + 1)
    candidates = [f"{next_num}ページ目", next_num]
    for label in candidates:
        try:
            loc = frame.get_by_text(label, exact=True)
            if loc.count() > 0:
                loc.first.click(force=True)
                print(f"'{label}' の完全一致リンクをクリックしました。")
                return True
        except:
            pass
    # 完全一致がなければ部分一致で探す
    for label in candidates:
        try:
            loc = frame.get_by_text(label, exact=False)
            if loc.count() > 0:
                loc.first.click(force=True)
                print(f"'{label}' の部分一致リンクをクリックしました。")
                return True
        except:
            pass
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
            while page_num <= MAX_PAGES:
                print(f"--- {page_num}ページ目をスキャン中 ---")
                texts = scan_rows(target_frame)
                for text in texts:
                    total_scanned += 1
                    print(f"取得サンプル[{total_scanned}]: {text[:150]}")
                    if is_target_project(text):
                        current[text] = text

                moved = go_to_next_page(target_frame, page_num)
                if not moved:
                    print(f"{page_num}ページ目で次のページが見つからないため終了します。")
                    if page_num == 1:
                        debug_dump_links(target_frame)
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
