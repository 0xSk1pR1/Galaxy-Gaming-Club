import re
import csv
import json
import time
import requests
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

TELEGRAM_BOT_TOKEN = "8715306378:AAFEnBmQtN7cKjiXzx7V78C8GPXigwfmDFw"
TELEGRAM_CHAT_ID = "-5167263836"

USERNAME = "0xSk1pR"
PASSWORD = "Excellence440"
LOGIN_URL = "https://cp.icafecloud.com/?license_name=002028511341"

BASE_DIR = Path(r"C:\iCafeLogs")
DOWNLOAD_DIR = BASE_DIR / "raw"
REPORT_DIR = BASE_DIR / "reports"
DEBUG_DIR = BASE_DIR / "debug"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

today_file = datetime.now().strftime("%Y-%m-%d")
downloaded_csv = DOWNLOAD_DIR / f"icafe_logs_{today_file}.csv"
report_txt = REPORT_DIR / f"review_output_{today_file}.txt"
debug_network_file = DEBUG_DIR / "network_debug.json"

REFUND_WORDS = [
    "refund", "reverse", "reversal", "void", "return",
    "cancel sale", "rollback", "money back"
]

BONUS_ADD_WORDS = [
    "bonus added", "add bonus", "manual bonus", "grant bonus",
    "given bonus", "gift bonus", "bonus increase",
    "bonus credited", "reward bonus", "bonus changed",
    "bonus adjust"
]

BONUS_USE_WORDS = [
    "used bonus", "bonus used", "start balance session", "left mins"
]

ACCOUNT_DELETE_WORDS = [
    "member_delete",
    "delete member",
    "delete account",
    "account deleted",
    "remove member",
    "member removed",
    "member delete",
    "account remove",
    "remove account",
    "deleted member"
]


def telegram_send_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def telegram_send_long_message(text: str, chunk_size: int = 3500):
    text = (text or "").strip()

    if not text:
        telegram_send_message("Report is empty.")
        return

    chunks = []
    current = ""

    for line in text.splitlines(True):
        if len(current) + len(line) <= chunk_size:
            current += line
        else:
            if current:
                chunks.append(current.strip())
            if len(line) <= chunk_size:
                current = line
            else:
                start = 0
                while start < len(line):
                    part = line[start:start + chunk_size]
                    chunks.append(part.strip())
                    start += chunk_size
                current = ""

    if current.strip():
        chunks.append(current.strip())

    for i, chunk in enumerate(chunks, 1):
        if len(chunks) == 1:
            telegram_send_message(chunk)
        else:
            telegram_send_message(f"Report part {i}/{len(chunks)}\n\n{chunk}")


def save_debug(page, name):
    try:
        page.screenshot(path=str(DEBUG_DIR / f"{name}.png"), full_page=True)
    except Exception:
        pass


def click_first(page, candidates, name, timeout=10000):
    deadline = time.time() + (timeout / 1000)
    last_error = None

    while time.time() < deadline:
        for locator in candidates:
            try:
                count = locator.count()
                for i in range(count):
                    item = locator.nth(i)
                    if item.is_visible():
                        item.click(force=True)
                        print(f"Clicked {name}")
                        return item
            except Exception as e:
                last_error = e
        page.wait_for_timeout(300)

    raise RuntimeError(f"Could not click {name}. Last error: {last_error}")


def fill_first(page, candidates, value, name, timeout=10000):
    deadline = time.time() + (timeout / 1000)
    last_error = None

    while time.time() < deadline:
        for locator in candidates:
            try:
                count = locator.count()
                for i in range(count):
                    item = locator.nth(i)
                    if item.is_visible():
                        item.fill(value)
                        print(f"Filled {name}")
                        return item
            except Exception as e:
                last_error = e
        page.wait_for_timeout(300)

    raise RuntimeError(f"Could not fill {name}. Last error: {last_error}")


def open_logs(page):
    click_first(
        page,
        [
            page.get_by_text("Logs", exact=True),
            page.locator("a").filter(has_text=re.compile(r"^\s*Logs\s*$", re.I)),
            page.locator("div").filter(has_text=re.compile(r"^\s*Logs\s*$", re.I)),
            page.locator("text=Logs"),
        ],
        "Logs menu"
    )
    page.wait_for_timeout(2500)

    try:
        click_first(
            page,
            [
                page.get_by_text("Billing logs", exact=True),
                page.locator("text=Billing logs"),
            ],
            "Billing logs tab",
            timeout=5000
        )
        page.wait_for_timeout(1500)
    except Exception:
        pass


def open_date_picker(page):
    js = """
    () => {
        const all = Array.from(document.querySelectorAll('div, span, input, button'));

        const isVisible = (el) => {
            const s = window.getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s.display !== 'none' &&
                   s.visibility !== 'hidden' &&
                   r.width > 120 &&
                   r.height > 20;
        };

        const looksLikeDateRange = (txt) => {
            txt = (txt || '').trim();
            return /\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}\\s*-\\s*\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}/.test(txt);
        };

        const candidates = all
            .filter(el => isVisible(el))
            .map(el => ({
                el,
                text: (el.innerText || el.value || '').trim(),
                rect: el.getBoundingClientRect()
            }))
            .filter(x => looksLikeDateRange(x.text))
            .sort((a, b) => {
                if (a.rect.top !== b.rect.top) return a.rect.top - b.rect.top;
                return b.rect.width - a.rect.width;
            });

        if (!candidates.length) return null;

        const target = candidates[0].el;
        target.scrollIntoView({ block: 'center' });
        const rect = target.getBoundingClientRect();

        return {
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2,
            text: (target.innerText || target.value || '').trim()
        };
    }
    """

    target = page.evaluate(js)
    if not target:
        raise RuntimeError("Could not find top date range control")

    print("Top date range found:", target["text"])
    page.mouse.click(target["x"], target["y"])
    page.wait_for_timeout(1500)


def select_today_range(page):
    try:
        items = page.locator('li[data-range-key="Today"]')
        count = items.count()

        visible_items = []
        for i in range(count):
            item = items.nth(i)
            try:
                if item.is_visible():
                    box = item.bounding_box()
                    if box:
                        visible_items.append((item, box))
            except Exception:
                pass

        if visible_items:
            visible_items.sort(key=lambda x: x[1]["y"])
            item = visible_items[0][0]
            item.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            item.click(force=True)
            print("Clicked visible Today")
            page.wait_for_timeout(1200)

            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            except Exception:
                pass

            return True
    except Exception:
        pass

    try:
        clicked = page.evaluate("""
        () => {
            const nodes = Array.from(document.querySelectorAll('li[data-range-key="Today"]'));
            const isVisible = (el) => {
                const s = window.getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return s.display !== 'none' &&
                       s.visibility !== 'hidden' &&
                       r.width > 0 &&
                       r.height > 0;
            };

            const visible = nodes.filter(isVisible).sort((a, b) => {
                return a.getBoundingClientRect().top - b.getBoundingClientRect().top;
            });

            const target = visible[0];
            if (!target) return false;

            target.scrollIntoView({ block: 'center' });
            target.click();
            return true;
        }
        """)
        if clicked:
            print("Clicked Today via JS")
            page.wait_for_timeout(1200)
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            except Exception:
                pass
            return True
    except Exception:
        pass

    return False


def click_search_button(page):
    click_first(
        page,
        [
            page.get_by_role("button", name=re.compile(r"^\s*search\s*$", re.I)),
            page.locator("button").filter(has_text=re.compile(r"^\s*Search\s*$", re.I)),
            page.locator("text=Search"),
        ],
        "Search button",
        timeout=12000
    )
    page.wait_for_timeout(3500)


def pick_download_target(page):
    js = """
    () => {
        const vw = window.innerWidth;
        const vh = window.innerHeight;

        const raw = Array.from(document.querySelectorAll('*'));

        const isVisible = (el) => {
            const s = window.getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s.display !== 'none' &&
                   s.visibility !== 'hidden' &&
                   s.opacity !== '0' &&
                   r.width >= 18 &&
                   r.height >= 18 &&
                   r.bottom > 0 &&
                   r.right > 0 &&
                   r.left < vw &&
                   r.top < vh;
        };

        const isClickable = (el) => {
            const s = window.getComputedStyle(el);
            return (
                el.tagName === 'BUTTON' ||
                el.tagName === 'A' ||
                el.getAttribute('role') === 'button' ||
                typeof el.onclick === 'function' ||
                s.cursor === 'pointer' ||
                !!el.closest('button,a,[role="button"]')
            );
        };

        const getClickableRoot = (el) => {
            return el.closest('button,a,[role="button"]') || el;
        };

        const text = (el) => (
            (el.innerText || '') + ' ' +
            (el.getAttribute('title') || '') + ' ' +
            (el.getAttribute('aria-label') || '') + ' ' +
            (el.className || '')
        ).toLowerCase();

        let candidates = raw
            .filter(isVisible)
            .filter(isClickable)
            .map(getClickableRoot)
            .filter((el, idx, arr) => arr.indexOf(el) === idx)
            .map(el => {
                const rect = el.getBoundingClientRect();
                return {
                    el,
                    rect,
                    text: text(el),
                    html: el.outerHTML
                };
            })
            .filter(x => !x.text.includes('switch theme'))
            .filter(x => !x.text.includes('theme-toggle'))
            .filter(x => !x.text.includes('search'))
            .filter(x => !x.text.includes('menu'))
            .filter(x => x.rect.top >= 0 && x.rect.top < 220)
            .filter(x => x.rect.left > vw * 0.45)
            .filter(x => x.rect.width >= 20 && x.rect.width <= 120)
            .filter(x => x.rect.height >= 20 && x.rect.height <= 120)
            .sort((a, b) => {
                if (b.rect.left != a.rect.left) return b.rect.left - a.rect.left;
                return a.rect.top - b.rect.top;
            })
            .map(x => ({
                x: x.rect.left + x.rect.width / 2,
                y: x.rect.top + x.rect.height / 2,
                left: x.rect.left,
                top: x.rect.top,
                width: x.rect.width,
                height: x.rect.height,
                text: x.text,
                html: x.html
            }));

        return {
            viewportWidth: vw,
            candidates
        };
    }
    """

    result = page.evaluate(js)
    candidates = result["candidates"]
    vw = result["viewportWidth"]

    if candidates:
        print("Chosen clickable candidate:")
        print(candidates[0]["html"])
        return {"mode": "candidate", **candidates[0]}

    fallback = {
        "mode": "fallback",
        "x": vw - 55,
        "y": 32
    }
    print("Using coordinate fallback:", fallback)
    return fallback


def save_real_file_response(resp, path):
    headers = {k.lower(): v for k, v in resp.headers.items()}
    content_type = headers.get("content-type", "").lower()
    content_disposition = headers.get("content-disposition", "").lower()

    if (
        "text/csv" in content_type or
        "application/csv" in content_type or
        "application/vnd.ms-excel" in content_type or
        "application/octet-stream" in content_type or
        "attachment" in content_disposition
    ):
        body = resp.body()
        with open(path, "wb") as f:
            f.write(body)
        return True

    return False


def click_download_target(page, target):
    page.mouse.click(target["x"], target["y"])


def to_float(value):
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def normalize_row(row):
    return {str(k).strip().upper(): str(v).strip() for k, v in row.items()}


def getv(row, key):
    return row.get(key, "").strip()


def contains_any(text, words):
    text = text.lower()
    return any(word.lower() in text for word in words)


def is_refund(row):
    text = f"{getv(row, 'EVENT')} {getv(row, 'DETAILS')}".lower()
    return contains_any(text, REFUND_WORDS)


def is_account_deleted(row):
    text = f"{getv(row, 'EVENT')} {getv(row, 'DETAILS')}".lower()
    return contains_any(text, ACCOUNT_DELETE_WORDS)


def extract_bonus_amount(row):
    bonus_col = to_float(getv(row, "BONUS"))
    if bonus_col > 0:
        return bonus_col

    details = getv(row, "DETAILS")
    patterns = [
        r'bonus\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)',
        r'add bonus\s*([0-9]+(?:\.[0-9]+)?)',
        r'bonus added\s*([0-9]+(?:\.[0-9]+)?)',
        r'bonus\s+([0-9]+(?:\.[0-9]+)?)'
    ]

    for p in patterns:
        m = re.search(p, details, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                pass

    return 0.0


def is_bonus_activity(row):
    text = f"{getv(row, 'EVENT')} {getv(row, 'DETAILS')}".lower()

    if contains_any(text, BONUS_USE_WORDS):
        return False

    bonus_amount = extract_bonus_amount(row)
    if bonus_amount > 0:
        return True

    return contains_any(text, BONUS_ADD_WORDS)


def analyze_downloaded_logs(csv_path: Path, output_txt: Path):
    account_deleted = []
    refund_logs = []
    bonus_activity = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for raw_row in reader:
            row = normalize_row(raw_row)

            if is_account_deleted(row):
                account_deleted.append(row)
                continue

            if is_refund(row):
                refund_logs.append(row)
                continue

            if is_bonus_activity(row):
                bonus_amount = extract_bonus_amount(row)
                bonus_activity.append((row, bonus_amount))
                continue

    with open(output_txt, "w", encoding="utf-8") as out:
        out.write("ICAFE LOG REVIEW\n")
        out.write("=" * 100 + "\n\n")

        out.write("SUMMARY\n")
        out.write("-" * 100 + "\n")
        out.write(f"ACCOUNT_DELETED: {len(account_deleted)}\n")
        out.write(f"REFUND_LOGS: {len(refund_logs)}\n")
        out.write(f"BONUS_ACTIVITY: {len(bonus_activity)}\n\n")

        out.write("=" * 100 + "\n")
        out.write("ACCOUNT_DELETED\n")
        out.write("=" * 100 + "\n\n")
        if account_deleted:
            for i, row in enumerate(account_deleted, 1):
                balance_value = to_float(getv(row, "BALANCE"))
                bonus_value = to_float(getv(row, "BONUS"))
                total_visible_funds = balance_value + bonus_value

                out.write(f"[{i}]\n")
                out.write(f"DATE: {getv(row, 'DATE')}\n")
                out.write(f"TIME: {getv(row, 'TIME')}\n")
                out.write(f"DELETED_BY: {getv(row, 'STAFF')}\n")
                out.write(f"DELETED_ACCOUNT: {getv(row, 'MEMBER')}\n")
                out.write(f"BALANCE_BEFORE_DELETE: {balance_value}\n")
                out.write(f"BONUS_BEFORE_DELETE: {bonus_value}\n")
                out.write(f"TOTAL_VISIBLE_FUNDS_BEFORE_DELETE: {total_visible_funds}\n")
                out.write("-" * 100 + "\n")
        else:
            out.write("NO ACCOUNT_DELETED LOGS FOUND\n\n")

        out.write("=" * 100 + "\n")
        out.write("REFUND_LOGS\n")
        out.write("=" * 100 + "\n\n")
        if refund_logs:
            for i, row in enumerate(refund_logs, 1):
                member = getv(row, "MEMBER")
                out.write(f"[{i}]\n")
                out.write(f"DATE: {getv(row, 'DATE')}\n")
                out.write(f"TIME: {getv(row, 'TIME')}\n")
                out.write(f"MEMBER: {member}\n")
                out.write(f"STAFF: {getv(row, 'STAFF')}\n")
                out.write(f"COMPUTER: {getv(row, 'COMPUTER')}\n")
                out.write(f"EVENT: {getv(row, 'EVENT')}\n")
                out.write(f"CASH: {getv(row, 'CASH')}\n")
                out.write(f"CARD/QR: {getv(row, 'CARD/QR')}\n")
                out.write(f"COIN: {getv(row, 'COIN')}\n")
                out.write(f"BALANCE: {getv(row, 'BALANCE')}\n")
                out.write(f"BONUS: {getv(row, 'BONUS')}\n")

                if member.strip().lower() != "bar1":
                    out.write(f"DETAILS: {getv(row, 'DETAILS')}\n")
                else:
                    out.write("DETAILS: HIDDEN_FOR_BAR1\n")

                out.write("-" * 100 + "\n")
        else:
            out.write("NO REFUND LOGS FOUND\n\n")

        out.write("=" * 100 + "\n")
        out.write("BONUS_ACTIVITY\n")
        out.write("=" * 100 + "\n\n")
        if bonus_activity:
            for i, (row, bonus_amount) in enumerate(bonus_activity, 1):
                out.write(f"[{i}]\n")
                out.write(f"DATE: {getv(row, 'DATE')}\n")
                out.write(f"TIME: {getv(row, 'TIME')}\n")
                out.write(f"BONUS_ACCOUNT: {getv(row, 'MEMBER')}\n")
                out.write(f"BONUS_DONE_BY: {getv(row, 'STAFF')}\n")
                out.write(f"BONUS_AMOUNT: {bonus_amount}\n")
                out.write("-" * 100 + "\n")
        else:
            out.write("NO BONUS ACTIVITY FOUND\n\n")

    print("Analysis done.")
    print("Report file:", output_txt)


def run_download_and_analysis():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=250)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(15000)

        captured_responses = []

        def on_response(resp):
            try:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                captured_responses.append({
                    "url": resp.url,
                    "status": resp.status,
                    "content_type": headers.get("content-type", ""),
                    "content_disposition": headers.get("content-disposition", "")
                })
            except Exception:
                pass

        page.on("response", on_response)

        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            save_debug(page, "01_login_page")

            fill_first(
                page,
                [
                    page.locator('input[name="username"]'),
                    page.locator('input[placeholder*="user" i]'),
                    page.locator('input[placeholder*="email" i]'),
                    page.locator('input[type="text"]'),
                ],
                USERNAME,
                "username"
            )

            fill_first(
                page,
                [
                    page.locator('input[name="password"]'),
                    page.locator('input[placeholder*="pass" i]'),
                    page.locator('input[type="password"]'),
                ],
                PASSWORD,
                "password"
            )

            click_first(
                page,
                [
                    page.locator('button[type="submit"]'),
                    page.get_by_role("button", name=re.compile("login|sign in", re.I)),
                    page.locator("button"),
                ],
                "login button"
            )

            page.wait_for_timeout(5000)
            save_debug(page, "02_after_login")

            open_logs(page)
            save_debug(page, "03_logs_page")

            open_date_picker(page)
            save_debug(page, "04_date_dropdown_open")

            if not select_today_range(page):
                raise RuntimeError("Could not select Today filter")

            save_debug(page, "05_after_today")

            click_search_button(page)
            save_debug(page, "06_after_search")

            download_target = pick_download_target(page)
            save_debug(page, "07_before_download")

            downloaded = False

            try:
                with page.expect_download(timeout=45000) as download_info:
                    click_download_target(page, download_target)

                download = download_info.value
                download.save_as(str(downloaded_csv))
                print("Downloaded successfully:", downloaded_csv)
                downloaded = True

            except PlaywrightTimeoutError:
                print("No browser download event. Trying strict file response...")

            if not downloaded:
                try:
                    before_count = len(captured_responses)
                    click_download_target(page, download_target)
                    page.wait_for_timeout(5000)

                    recent = captured_responses[before_count:]
                    print("Recent responses after click:")
                    for r in recent:
                        print(r)

                    with page.expect_response(
                        lambda r: (
                            r.status == 200 and (
                                "text/csv" in str(r.headers).lower() or
                                "application/csv" in str(r.headers).lower() or
                                "application/octet-stream" in str(r.headers).lower() or
                                "application/vnd.ms-excel" in str(r.headers).lower() or
                                "attachment" in str(r.headers).lower()
                            )
                        ),
                        timeout=20000
                    ) as resp_info:
                        click_download_target(page, download_target)

                    resp = resp_info.value

                    if save_real_file_response(resp, downloaded_csv):
                        print("Saved real file response to:", downloaded_csv)
                        downloaded = True

                except Exception as e:
                    print("Strict file response not found:", e)

            if not downloaded:
                with open(debug_network_file, "w", encoding="utf-8") as f:
                    json.dump(captured_responses[-100:], f, ensure_ascii=False, indent=2)

                raise RuntimeError(
                    "Did not get a real logs file. "
                    f"Saved network debug to: {debug_network_file}"
                )

            save_debug(page, "08_done")

        finally:
            browser.close()

    if downloaded_csv.exists():
        analyze_downloaded_logs(downloaded_csv, report_txt)
    else:
        raise RuntimeError(f"Downloaded file not found: {downloaded_csv}")


def main():
    try:
        run_download_and_analysis()

        if report_txt.exists():
            report_content = report_txt.read_text(encoding="utf-8").strip()
            telegram_send_long_message(report_content)
        else:
            telegram_send_message("Report file was not created.")

        print("Done.")

    except Exception as e:
        print("ERROR:", e)
        try:
            telegram_send_message(f"Script failed: {e}")
        except Exception as tg_err:
            print("Telegram send failed:", tg_err)
        raise


if __name__ == "__main__":
    main()
