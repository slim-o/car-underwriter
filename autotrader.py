import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, quote, urlparse, urlsplit, urlunsplit, parse_qsl

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup


SEARCH_URL = (
    "https://www.autotrader.co.uk/car-search?"
    "channel=cars"
    "&make=BMW"
    "&model=4%20Series%20Gran%20Coupe"
    "&only-writeoff-categories=on"
    "&postcode=SW1X%207PL"
    "&sort=relevance"
    "&year-from=2022"
    "&year-to=2026"
)

RAW_HTML_DIR = "raw"
LISTINGS_FILE = "listings.json"

CHROME_URL = "http://localhost:9222"


def build_search_url(
    *,
    make: str,
    model: str,
    postcode: str,
    year: int,
    keywords: str | None = None,
    year_span: int = 1,
    only_writeoff_categories: bool = True,
    channel: str = "cars",
    sort: str = "relevance",
) -> str:
    """
    Build an Auto Trader search URL.

    Uses quote_via=quote so spaces become %20 (not '+') and brackets are encoded,
    matching the URL style you typically get from the site.
    """

    year_from = max(1900, int(year) - int(year_span))
    year_to = max(year_from, int(year) + int(year_span))

    params: dict[str, str] = {
        "channel": channel,
        "make": make,
        "model": model,
        "postcode": postcode,
        "sort": sort,
        "year-from": str(year_from),
        "year-to": str(year_to),
    }

    if keywords and str(keywords).strip():
        params["keywords"] = str(keywords).strip()

    if only_writeoff_categories:
        params["only-writeoff-categories"] = "on"

    return "https://www.autotrader.co.uk/car-search?" + urlencode(
        params,
        quote_via=quote,
        safe="",
    )


def get_search_page(context, search_url: str):
    """
    Find an existing AutoTrader search page.

    If one doesn't exist, create a new page and open SEARCH_URL.
    """

    # Prefer an existing tab that's already on this exact search (or a startswith
    # match to tolerate anchors/query ordering differences).
    for page in context.pages:
        try:
            if page.url == search_url or page.url.startswith(search_url):
                print("Found matching AutoTrader search page:")
                print(page.url)
                return page
        except Exception:
            continue

    for page in context.pages:

        if "autotrader.co.uk/car-search" in page.url:

            print("Found existing AutoTrader search page:")
            print(page.url)

            # Reuse the existing search tab, but navigate it to the requested query
            # so we don't accidentally scrape a previous search.
            try:
                if page.url != search_url and not page.url.startswith(search_url):
                    print("Navigating existing search tab to requested URL...")
                    page.goto(search_url, wait_until="domcontentloaded")
            except Exception:
                pass

            return page

    print("No AutoTrader search page found.")
    print("Opening search page...")

    page = context.new_page()

    page.goto(
        search_url,
        wait_until="domcontentloaded"
    )

    return page


def get_listings(page, *, debug_html_path: str | None = None):
    """
    Find advert cards on the AutoTrader search page.
    """

    print("Waiting for listings to load...")

    page.wait_for_timeout(5000)

    html = page.content()

    if debug_html_path:
        Path(debug_html_path).write_text(html, encoding="utf-8")

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    listings = soup.find_all(
        "div",
        attrs={
            "data-testid": lambda value:
                value and value.startswith("advertCard-")
        }
    )

    print(
        f"Found {len(listings)} advert cards "
        "using advertCard selector."
    )

    return listings


def get_listing_urls(listings):
    """
    Extract unique listing URLs from advert cards.
    """

    urls = []

    for listing in listings:

        links = listing.find_all(
            "a",
            href=True
        )

        for link in links:

            url = link["href"]

            if "/car-details/" not in url:
                continue

            if url.startswith("/"):
                url = (
                    "https://www.autotrader.co.uk"
                    + url
                )

            # Remove duplicate URLs.
            if url not in urls:
                urls.append(url)

    return urls

def find_json_data(soup):
    """
    Look for JSON data embedded in the page.
    """

    scripts = soup.find_all(
        "script"
    )

    for script in scripts:

        script_type = script.get(
            "type"
        )

        if script_type == "application/ld+json":

            print()
            print(
                "Found JSON-LD:"
            )

            print(
                script.get_text(
                    strip=True
                )[:5000]
            )

'''
def scrape_listing(page, url, index):
    """
    Open an individual advert and save its raw HTML.
    """

    print()
    print(
        f"[{index}] Opening listing:"
    )
    print(url)

    page.goto(
        url,
        wait_until="domcontentloaded"
    )

    page.wait_for_timeout(3000)

    html = page.content()

    filename = os.path.join(
        RAW_HTML_DIR,
        f"listing_{index:03}.html"
    )

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as file:
        file.write(html)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    title = None

    if soup.title:
        title = soup.title.get_text(
            strip=True
        )

    return {
        "url": page.url,
        "title": title,
        "raw_html": filename
    }
'''
def scrape_listing(page, url, index):
    """
    Open an individual AutoTrader advert, save its raw HTML,
    and extract the main vehicle information.
    """

    print()
    print(f"[{index}] Opening listing:")
    print(url)

    # --------------------------------------------------
    # Open listing
    # --------------------------------------------------

    page.goto(
        url,
        wait_until="domcontentloaded"
    )

    page.wait_for_timeout(3000)

    # Wait for the main listing container
    try:
        page.wait_for_selector(
            "#top",
            timeout=10000
        )
    except Exception:
        print("WARNING: #top did not appear")

    print("Current URL:", page.url)
    print("Page title:", page.title())
    print("#top count:", page.locator("#top").count())

    # --------------------------------------------------
    # Get HTML
    # --------------------------------------------------

    html = page.content()

    filename = os.path.join(
        RAW_HTML_DIR,
        f"listing_{index:03}.html"
    )

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as file:
        file.write(html)

    # --------------------------------------------------
    # Parse HTML
    # --------------------------------------------------

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    top = soup.find(
        "div",
        id="top"
    )

    if top is None:

        print("WARNING: Could not find #top")

        return {
            "url": page.url,
            "raw_html": filename
        }

    # --------------------------------------------------
    # Title
    # --------------------------------------------------

    title = None

    if soup.title:

        title = soup.title.get_text(
            strip=True
        )

    # --------------------------------------------------
    # Images
    # --------------------------------------------------

    images = []

    for image in top.find_all("img"):

        src = image.get("src")
        alt = image.get("alt")

        if not src:
            continue

        images.append({
            "url": src,
            "description": alt
        })

    # --------------------------------------------------
    # Information section
    # --------------------------------------------------

    info_section = top.select_one(
        "section.sc-2g3p0n-1"
    )

    if info_section is None:

        print(
            "WARNING: Could not find information section"
        )

        return {
            "url": page.url,
            "title": title,
            "images": images,
            "raw_html": filename
        }

    # --------------------------------------------------
    # Vehicle specifications
    # --------------------------------------------------

    specifications = {}

    for container in info_section.find_all(
        "div",
        class_=lambda value:
            value and "sc-1yzvd0s-4" in value
    ):

        paragraphs = container.find_all("p")

        if len(paragraphs) < 2:
            continue

        label = paragraphs[0].get_text(
            " ",
            strip=True
        )

        value = paragraphs[1].get_text(
            " ",
            strip=True
        )

        specifications[label] = value

    # --------------------------------------------------
    # Print specifications
    # --------------------------------------------------

    print()
    print("SPECIFICATIONS")
    print("=" * 40)

    for key, value in specifications.items():

        print(
            f"{key}: {value}"
        )

    # --------------------------------------------------
    # Basic listing information
    # --------------------------------------------------

    location = None
    distance = None
    writeoff_category = None
    vehicle_name = None
    variant = None
    price = None
    seller_type = None

    # --------------------------------------------------
    # Key information
    # --------------------------------------------------

    key_information = info_section.select_one(
        '[data-testid="key-information"]'
    )

    if key_information:

        spans = key_information.find_all(
            "span"
        )

        if len(spans) >= 2:

            location = spans[0].get_text(
                " ",
                strip=True
            )

            distance = spans[1].get_text(
                " ",
                strip=True
            )

    # --------------------------------------------------
    # Pricing / vehicle information
    # --------------------------------------------------

    pricing = info_section.select_one(
        '[data-testid="pricing"]'
    )

    if pricing:

        # Write-off category
        writeoff_element = pricing.find(
            "p",
            string=lambda text:
                text and text.strip() in [
                    "Cat S",
                    "Cat N",
                    "Cat A",
                    "Cat B"
                ]
        )

        if writeoff_element:

            writeoff_category = (
                writeoff_element.get_text(
                    " ",
                    strip=True
                )
            )

        # Vehicle name
        vehicle_element = pricing.find(
            "h1"
        )

        if vehicle_element:

            vehicle_name = (
                vehicle_element.get_text(
                    " ",
                    strip=True
                )
            )

        # Variant
        variant_element = pricing.select_one(
            "h1 + div span"
        )

        if variant_element:

            variant = (
                variant_element.get_text(
                    " ",
                    strip=True
                )
            )

        # Price
        price_element = pricing.select_one(
            '[data-testid="advert-price"]'
        )

        if price_element:

            price = (
                price_element.get_text(
                    " ",
                    strip=True
                )
            )

    # --------------------------------------------------
    # Seller information
    # --------------------------------------------------

    next_steps = info_section.select_one(
        '[data-testid="next-steps"]'
    )

    if next_steps:

        seller_element = next_steps.find(
            "span",
            string=lambda text:
                text and text.strip() in [
                    "Private seller",
                    "Trade seller"
                ]
        )

        if seller_element:

            seller_type = (
                seller_element.get_text(
                    " ",
                    strip=True
                )
            )

    # --------------------------------------------------
    # Print basic information
    # --------------------------------------------------

    print()
    print("BASIC INFORMATION")
    print("=" * 40)

    print(f"Location: {location}")
    print(f"Distance: {distance}")
    print(f"Write-off category: {writeoff_category}")
    print(f"Vehicle: {vehicle_name}")
    print(f"Variant: {variant}")
    print(f"Price: {price}")
    print(f"Seller: {seller_type}")

    # --------------------------------------------------
    # Description
    # --------------------------------------------------

    description = None

    description_button = page.locator(
        '[data-testid="description-signpost"]'
    )

    if description_button.count() > 0:

        try:

            print()
            print("Opening full description...")

            description_button.click()

            description_body = page.locator(
                "div.QlZ4CW__body"
            )

            description_body.wait_for(
                state="visible",
                timeout=5000
            )

            description = (
                description_body.inner_text().strip()
            )

            print("Description found.")

        except Exception as error:

            print(
                f"WARNING: Could not extract full description: {error}"
            )

    else:

        print(
            "WARNING: Description button not found."
        )
    # --------------------------------------------------
    # Result
    # --------------------------------------------------

    listing = {
        "url": page.url,
        "title": title,

        "location": location,
        "distance": distance,
        "writeoff_category": writeoff_category,

        "vehicle": vehicle_name,
        "variant": variant,
        "price": price,
        "seller_type": seller_type,

        "specifications": specifications,

        "description": description,

        "images": images,

        "raw_html": filename
    }

    return listing
def save_results(
    results,
    *,
    search_url: str,
    requested_search_url: str | None = None,
    listings_file: str,
):
    """
    Save search metadata and scraped listings.
    """

    data = {
        "search": {
            "url": search_url,
            "requested_url": requested_search_url or search_url,
        },

        "scraped_at": datetime.now().isoformat(),

        "result_count": len(results),

        "results": results
    }

    with open(
        listings_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False
        )

    print()
    print(
        f"Saved {len(results)} listings "
        f"to {listings_file}"
    )


def strip_keywords_param(search_url: str) -> tuple[str, bool]:
    """
    Remove the `keywords` query parameter from an Auto Trader search URL.

    Returns (url_without_keywords, removed_bool).
    """

    parts = urlsplit(search_url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    filtered = [(k, v) for (k, v) in query if k.lower() != "keywords"]
    removed = len(filtered) != len(query)
    if not removed:
        return search_url, False

    new_query = urlencode(filtered, quote_via=quote, safe="")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)), True


def run_search(
    *,
    cdp_url: str,
    search_url: str,
    output_dir: str | Path = ".",
    limit: int | None = None,
):
    """
    Scrape Auto Trader search results + individual adverts, saving:
    - <output_dir>/listings.json
    - <output_dir>/search.html (debug snapshot)
    - <output_dir>/raw/listing_XXX.html

    Note: this does not attempt to bypass access controls or CAPTCHAs.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    listings_file = str(output_dir / "listings.json")
    debug_html_path = str(output_dir / "search.html")
    debug_html_with_keywords_path = str(output_dir / "search_with_keywords.html")

    # Create raw directory if it doesn't exist.
    os.makedirs(
        str(raw_dir),
        exist_ok=True
    )

    global RAW_HTML_DIR
    RAW_HTML_DIR = str(raw_dir)

    with sync_playwright() as p:

        print(
            f"Connecting to Chromium at "
            f"{cdp_url}"
        )

        browser = p.chromium.connect_over_cdp(
            cdp_url
        )

        context = (
            browser.contexts[0]
            if browser.contexts
            else browser.new_context()
        )

        # ---------------------------------------------
        # GET SEARCH PAGE
        # ---------------------------------------------

        search_page = get_search_page(
            context,
            search_url
        )

        print()
        print("Search page:")
        print(search_page.url)

        print(
            "Title:",
            search_page.title()
        )

        # ---------------------------------------------
        # FIND LISTINGS
        # ---------------------------------------------

        requested_search_url = search_url
        used_search_url = search_url

        def collect_urls(*, html_debug_path: str) -> list[str]:
            nonlocal used_search_url
            listings = get_listings(
                search_page,
                debug_html_path=html_debug_path,
            )
            urls = get_listing_urls(listings)
            return urls

        urls = collect_urls(
            html_debug_path=(
                debug_html_with_keywords_path
                if "keywords=" in used_search_url
                else debug_html_path
            )
        )

        # If keyword-narrowed searches return too few results, retry without keywords.
        if len(urls) < 3:
            fallback_url, removed = strip_keywords_param(used_search_url)
            if removed and fallback_url != used_search_url:
                print()
                print(
                    f"Only {len(urls)} results with keywords. Retrying without keywords..."
                )
                used_search_url = fallback_url
                try:
                    search_page.goto(used_search_url, wait_until="domcontentloaded")
                except Exception:
                    pass
                urls = collect_urls(html_debug_path=debug_html_path)

        if limit is not None:
            urls = urls[: max(0, int(limit))]

        print()
        print(
            f"Found {len(urls)} listing URLs."
        )

        # ---------------------------------------------
        # IF NO URLS WERE FOUND
        # ---------------------------------------------

        if not urls:

            print()
            print(
                "No listing URLs were found."
            )

            print(
                "The search page has been saved as:"
            )

            print(
                debug_html_path
            )

            print()
            print(
                "Inspect search.html to determine "
                "the current AutoTrader structure."
            )

            save_results(
                [],
                search_url=used_search_url,
                requested_search_url=requested_search_url,
                listings_file=listings_file,
            )

            return json.loads(Path(listings_file).read_text(encoding="utf-8"))

        # ---------------------------------------------
        # CREATE LISTING PAGE
        # ---------------------------------------------

        listing_page = context.new_page()

        results = []

        # ---------------------------------------------
        # SCRAPE EACH LISTING
        # ---------------------------------------------

        for index, url in enumerate(
            urls,
            start=1
        ):

            try:

                result = scrape_listing(
                    listing_page,
                    url,
                    index
                )

                results.append(
                    result
                )

            except Exception as error:

                print(
                    f"Error scraping listing "
                    f"{index}: {error}"
                )

                results.append(
                    {
                        "url": url,
                        "error": str(error)
                    }
                )

        # ---------------------------------------------
        # CLOSE LISTING PAGE
        # ---------------------------------------------

        listing_page.close()

        # ---------------------------------------------
        # SAVE JSON
        # ---------------------------------------------

        save_results(
            results,
            search_url=used_search_url,
            requested_search_url=requested_search_url,
            listings_file=listings_file,
        )

    return json.loads(Path(listings_file).read_text(encoding="utf-8"))


def main():

    run_search(
        cdp_url=CHROME_URL,
        search_url=SEARCH_URL,
        output_dir=".",
        limit=None,
    )


if __name__ == "__main__":
    main()
