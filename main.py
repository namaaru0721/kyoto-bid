import json, os, requests, re
from playwright.sync_api import sync_playwright

WEBHOOK_URL = "https://webhook.worksmobile.com/message/98a5731f-7764-4495-9bc6-521fa876bcb5"
START_URL = "https://kyoto.efftis.jp/26000/CALS/PPI_P/pages/PPI_P/PiCtBaFi02/PiCtBaFi02start.vm"
CACHE_FILE = "known_links.json"

FORCE_OVERWRITE = False  # デバッグ完了後はFalseに戻します（新着のみ通知）
MAX_PAGES = 30  # 1ページ10件なので30ページ=300件まで確認。全704件見たいなら71に増やす

# ① この種別は無条件で対象（御社の本業そのもの）
ALWAYS_TARGET_TYPES = ["管工事"]

# ② この種別は、タイトルに以下のキーワードが含まれる場合のみ対象
#    （ポンプ・エレベーター等、水回りと無関係な「機械もの」を除外するため）
CONDITIONAL_TARGET_TYPES = {
    "機械器具設置工事": [
        "給排水", "衛生", "浄水", "浄化", "配管", "揚水", "ポンプ",
        "受水槽", "消火", "空調", "ろ過", "排水処理", "水道", "汚水",
        "雑排水", "浄化槽", "受水", "加圧給水", "給水", "排水", "ダクト", "ボイラー",
    ],
    "建築一式工事": [
        "トイレ", "便所", "衛生設備", "給排水", "浄化槽",
    ],
}

# ②の種別で、以下のキーワードが含まれる場合は上のキーワードに一致していても除外
#    （昇降機・電光掲示板など、機械器具設置工事の中の無関係カテゴリを弾く）
MECH_EXCLUDE_KEYWORDS = ["昇降機", "エレベーター", "電光", "表示板", "スコアボード", "監視装置", "制御装置"]


def extract_project_type(text):
    """テキストから「種別」欄を抽出する。種別は 入札方式（一般競争入札/指名競争入札）の直前のトークン。"""
    matches = list(re.finditer(r'(\S+工事(?:\([^)]*\))?)\s+(一般競争入札|指名競争入札)', text))
    if matches:
        return matches[-1].group(1)
    return None


def is_target_project(text):
    project_type = extract_project_type(text)
    if project_type is None:
        return False, None

    if project_type in ALWAYS_TARGET_TYPES:
        return True, f"種別「{project_type}」は無条件対象"

    if project_type in CONDITIONAL_TARGET_TYPES:
        for ex in MECH_EXCLUDE_KEYWORDS:
            if ex in text:
                return False, None
        for kw in CONDITIONAL_TARGET_TYPES[project_type]:
            if kw in text:
                return True, f"種別「{project_type}」＋キーワード「{kw}」に一致"

    return False, None


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

def go_to_page_by_index(frame, page_index_value):
    try:
        select = frame.locator("select").first
        if select.count() == 0:
            return False
        select.select_option(value=str(page_index_value))
        return True
    except Exception as e:
        print(f"ページ送り失敗(value={page_index_value}): {e}")
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

                data_rows = [t for t in texts if re.match(r'^\d+\s', t)]
                current_first_row = data_rows[0] if data_rows else None
                if page_num > 1 and current_first_row == prev_first_row:
                    print(f"警告: {page_num}ページ目の内容が前ページと同一です。処理を中断します。")
                    break
                prev_first_row = current_first_row

                for text in texts:
                    total_scanned += 1
                    matched, reason = is_target_project(text)
                    if matched:
                        print(f"[該当] {reason} : {text[:120]}")
                        current[text] = text

                next_value = page_num * 10
                moved = go_to_page_by_index(target_frame, next_value)
                if not moved:
                    print(f"{page_num}ページ目で次のページへ移動できなかったため終了します。")
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
