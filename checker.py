import json
import os
from urllib.parse import urljoin
import requests
from playwright.sync_api import sync_playwright

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
PINCODE = "500090"  # Change to your exact 6-digit Hyderabad PIN code
STATE_FILE = "seen.json"

CATALOG_URLS = [
    "https://www.firstcry.com/hot-wheels/0/0/113?sort=NewArrivals",
    "https://www.firstcry.com/hot-wheels/0/0/113",
]

BRAND_KEYWORDS = [
    "porsche", "ferrari", "lamborghini", "bugatti", "mclaren", "pagani",
    "koenigsegg", "nissan", "skyline", "gt-r", "gtr", "datsun", "mazda",
    "supra", "toyota", "honda", "civic", "bmw", "mercedes", "audi",
    "f1", "formula 1", "williams", "red bull", "mustang", "corvette",
    "car culture", "team transport", "boulevard", "premium", "silver series"
]


def load_seen():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(seen_set):
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(list(seen_set)), f, indent=2)


def send_telegram(message):
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(
        api_url,
        data={"chat_id": CHAT_ID, "text": message, "disable_web_page_preview": False},
        timeout=15,
    )


def set_pincode(page, pincode):
    try:
        # Target the visible "Enter Pin Code" / "Enter Pincode" input directly
        pin_input = page.locator('input[placeholder*="Pin" i]').first
        if pin_input.count() > 0 and pin_input.is_visible():
            pin_input.fill(pincode)
            check_btn = page.get_by_text("CHECK", exact=True).first
            if check_btn.count() > 0:
                check_btn.click(timeout=5000)
                page.wait_for_timeout(2000)
                print(f"PIN code set to {pincode}")
                return
        print("PIN code input not visible on page (continuing anyway)")
    except Exception as e:
        print(f"Could not set PIN code via UI (continuing anyway): {e}")


def load_all_products(page):
    """Scrolls down until no new product cards load (handles infinite scroll + View More)."""
    prev_count = 0
    stagnant_rounds = 0

    for _ in range(30):  # Max 30 scroll rounds (~600 items capacity)
        # Scroll to the bottom of the page
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)

        # Click "View More Products" / "Load More" if FirstCry shows a button
        load_more = page.locator('text=/View More|Load More/i').first
        if load_more.count() > 0 and load_more.is_visible():
            try:
                load_more.click(timeout=3000)
                page.wait_for_timeout(1500)
            except Exception:
                pass

        current_count = page.locator(".list_block").count()
        if current_count == prev_count:
            stagnant_rounds += 1
            if stagnant_rounds >= 3:  # Stop after 3 consecutive scrolls with no new items
                break
        else:
            stagnant_rounds = 0
            prev_count = current_count


def scan_firstcry():
    currently_in_stock = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        page.goto(CATALOG_URLS[0], wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)
        set_pincode(page, PINCODE)

        for idx, catalog_url in enumerate(CATALOG_URLS):
            try:
                if idx > 0:
                    page.goto(catalog_url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(3000)

                load_all_products(page)

                cards = page.locator(".list_block")
                count = cards.count()
                print(f"Found {count} product cards on {catalog_url}")

                for i in range(count):
                    card = cards.nth(i)
                    card_text = card.inner_text().lower()

                    if "out of stock" in card_text or "notify me" in card_text or "sold out" in card_text:
                        continue

                    link_el = card.locator('a[href*="/product-detail"]').first
                    if link_el.count() == 0:
                        continue

                    href = (link_el.get_attribute("href") or "").strip()
                    title = (link_el.get_attribute("title") or link_el.inner_text() or "").strip()
                    if not href:
                        continue

                    full_url = urljoin("https://www.firstcry.com/", href)
                    searchable = f"{title} {full_url}".lower()

                    if any(keyword in searchable for keyword in BRAND_KEYWORDS):
                        currently_in_stock[full_url] = title or "Hot Wheels Match"

            except Exception as e:
                print(f"Error scanning {catalog_url}: {e}")

        browser.close()

    previously_seen = load_seen()
    new_hits = [
        (url, title)
        for url, title in currently_in_stock.items()
        if url not in previously_seen
    ]

    for url, title in new_hits:
        send_telegram(f"🚨 Hot Wheels In Stock (PIN {PINCODE})!\n\n🏎️ {title}\n🔗 {url}")

    save_seen(set(currently_in_stock.keys()))
    print(f"Scan complete. Matches in stock: {len(currently_in_stock)} | New alerts sent: {len(new_hits)}")


if __name__ == "__main__":
    scan_firstcry()
