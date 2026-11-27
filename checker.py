import json
import os
import requests
from playwright.sync_api import sync_playwright

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
STATE_FILE = "seen.json"

# FirstCry Hot Wheels catalog sorted by New Arrivals
CATALOG_URLS = [
    "https://www.firstcry.com/hot-wheels/0/0/113?sort=NewArrivals",
    "https://www.firstcry.com/hot-wheels/0/0/113",  # Popular / default sort
]

# Edit this list anytime to add or remove car brands / series you want alerts for
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


def scan_firstcry():
    currently_in_stock = {}  # {url: title}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for catalog_url in CATALOG_URLS:
            try:
                page.goto(catalog_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(4000)

                # Scroll down several times to trigger lazy-loaded products
                for _ in range(6):
                    page.mouse.wheel(0, 2500)
                    page.wait_for_timeout(1500)

                # Extract product cards from the page
                cards = page.locator(".list_block")
                count = cards.count()
                print(f"Found {count} product cards on {catalog_url}")

                for i in range(count):
                    card = cards.nth(i)
                    card_text = card.inner_text().lower()

                    # Skip out-of-stock listings
                    if "out of stock" in card_text or "notify me" in card_text or "sold out" in card_text:
                        continue

                    link_el = card.locator('a[href*="/product-detail"]').first
                    if link_el.count() == 0:
                        continue

                    href = link_el.get_attribute("href") or ""
                    title = (link_el.get_attribute("title") or link_el.inner_text() or "").strip()
                    if not href:
                        continue

                    full_url = href if href.startswith("http") else f"https://www.firstcry.com{href}"
                    searchable = f"{title} {full_url}".lower()

                    if any(keyword in searchable for keyword in BRAND_KEYWORDS):
                        currently_in_stock[full_url] = title or "Hot Wheels Match"

            except Exception as e:
                print(f"Error scanning {catalog_url}: {e}")

        browser.close()

    previously_seen = load_seen()

    # Alert only for newly listed or restocked matches
    new_hits = [
        (url, title)
        for url, title in currently_in_stock.items()
        if url not in previously_seen
    ]

    for url, title in new_hits:
        send_telegram(f"🚨 Hot Wheels In Stock on FirstCry!\n\n🏎️ {title}\n🔗 {url}")

    # Save current in-stock matches (items that go OOS are dropped so restocks trigger again)
    save_seen(set(currently_in_stock.keys()))
    print(f"Scan complete. Matches in stock: {len(currently_in_stock)} | New alerts sent: {len(new_hits)}")


if __name__ == "__main__":
    scan_firstcry()
