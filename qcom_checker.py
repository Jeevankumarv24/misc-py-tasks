import json
import os
import requests
from playwright.sync_api import sync_playwright

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
STATE_FILE = "seen_qcom.json"

# Add your 5-6 target coordinates here
LOCATIONS = [
    {"name": "Pragathi Nagar", "lat": 17.5169, "lon": 78.3932},
    {"name": "Kukatpally",     "lat": 17.4948, "lon": 78.3996},
    {"name": "Madhapur",       "lat": 17.4483, "lon": 78.3915},
    {"name": "Kondapur",       "lat": 17.4622, "lon": 78.3568},
    {"name": "Banjara Hills",  "lat": 17.4156, "lon": 78.4347},
    {"name": "Kompally",       "lat": 17.5366, "lon": 78.4845},
]

BRAND_KEYWORDS = [
    "porsche", "ferrari", "lamborghini", "bugatti", "mclaren", "pagani",
    "koenigsegg", "nissan", "skyline", "gt-r", "gtr", "datsun", "mazda",
    "supra", "toyota", "honda", "civic", "bmw", "mercedes", "audi",
    "f1", "formula 1", "williams", "red bull", "mustang", "corvette",
    "car culture", "team transport", "boulevard", "premium", "silver series"
]

SITES = [
    {
        "name": "BigBasket",
        "url": "https://www.bigbasket.com/ps/?q=hot+wheels",
        "card_selector": "li[class*='PaginateItems'], div[class*='SKUDeck']",
    },
    {
        "name": "Zepto",
        "url": "https://www.zeptonow.com/search?query=hot+wheels",
        "card_selector": "a[data-testid='product-card'], a[href*='/pn/']",
    },
    {
        "name": "Blinkit",
        "url": "https://blinkit.com/s/?q=hot+wheels",
        "card_selector": "div[role='button'][id], div[class*='Product__UpdatedPlpProductContainer']",
    },
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
        data={"chat_id": CHAT_ID, "text": message, "disable_web_page_preview": True},
        timeout=15,
    )


def scan_qcom():
    currently_in_stock = {}  # {unique_key: (loc_name, site_name, title, url)}
    total_cards_loaded = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )

        for loc in LOCATIONS:
            loc_name = loc["name"]
            # Fresh context per coordinate so dark-store cookies reset cleanly
            context = browser.new_context(
                geolocation={"latitude": loc["lat"], "longitude": loc["lon"]},
                permissions=["geolocation"],
                locale="en-IN",
                timezone_id="Asia/Kolkata",
                viewport={"width": 1366, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = context.new_page()

            for site in SITES:
                site_name = site["name"]
                url = site["url"]
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=35000)
                    page.wait_for_timeout(4000)

                    for _ in range(2):
                        page.mouse.wheel(0, 2000)
                        page.wait_for_timeout(1200)

                    cards = page.locator(site["card_selector"])
                    count = cards.count()
                    total_cards_loaded += count
                    print(f"[{loc_name} | {site_name}] Found {count} cards")

                    for i in range(count):
                        text = cards.nth(i).inner_text().strip()
                        lower_text = text.lower()

                        if any(oos in lower_text for oos in ["out of stock", "sold out", "notify me", "currently unavailable"]):
                            continue

                        if "hot wheels" in lower_text and any(k in lower_text for k in BRAND_KEYWORDS):
                            clean_title = " | ".join([line.strip() for line in text.splitlines() if line.strip()][:3])
                            unique_key = f"{loc_name}::{site_name}::{clean_title.lower()}"
                            currently_in_stock[unique_key] = (loc_name, site_name, clean_title, url)

                except Exception as e:
                    print(f"[{loc_name} | {site_name}] Error: {e}")

            context.close()

        browser.close()

    previously_seen = load_seen()
    new_hits = [
        data for key, data in currently_in_stock.items() if key not in previously_seen
    ]

    for loc_name, site_name, title, url in new_hits:
        send_telegram(f"⚡ Hot Wheels on {site_name} ({loc_name})!\n\n🏎️ {title}\n🔗 {url}")

    # Only update seen state if pages actually loaded (avoids wiping state on a temporary IP block)
    if total_cards_loaded > 0:
        save_seen(set(currently_in_stock.keys()))

    print(f"Done. Total cards: {total_cards_loaded} | Matches: {len(currently_in_stock)} | New alerts: {len(new_hits)}")


if __name__ == "__main__":
    scan_qcom()
