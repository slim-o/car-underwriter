import json
import re

from playwright.sync_api import sync_playwright


AUTOTRADER_URL = "https://www.autotrader.co.uk/"
MODELS_FILE = "autotrader_models.json"
CHROME_URL = "http://localhost:9222"


def clean_name(name):
    """
    Remove AutoTrader's listing count from the end
    of a make or model name.

    Examples:

        Abarth (681)       -> Abarth
        Ford (12,345)      -> Ford
        500 (45)           -> 500
        4 Series (123)     -> 4 Series
    """

    return re.sub(
        r"\s*\(\d[\d,]*\)$",
        "",
        name.strip()
    )


def get_autotrader_models():

    # --------------------------------------------------
    # Connect to existing Chromium
    # --------------------------------------------------

    print(
        f"Connecting to Chromium at {CHROME_URL}"
    )

    with sync_playwright() as p:

        browser = p.chromium.connect_over_cdp(
            CHROME_URL
        )

        context = browser.contexts[0]

        # --------------------------------------------------
        # Find existing AutoTrader homepage
        # --------------------------------------------------

        page = None

        print()
        print("Existing browser pages:")

        for existing_page in context.pages:

            print(
                f"  {existing_page.url}"
            )

            if (
                existing_page.url.rstrip("/")
                == "https://www.autotrader.co.uk"
            ):

                page = existing_page
                break

        # --------------------------------------------------
        # Open homepage if necessary
        # --------------------------------------------------

        if page is None:

            print()
            print(
                "AutoTrader homepage not found."
            )

            print(
                "Opening AutoTrader homepage..."
            )

            page = context.new_page()

            page.goto(
                AUTOTRADER_URL,
                wait_until="domcontentloaded"
            )

        else:

            print()
            print(
                "Found existing AutoTrader homepage."
            )

        print()
        print(
            "AutoTrader URL:",
            page.url
        )

        # --------------------------------------------------
        # Wait for make dropdown
        # --------------------------------------------------

        print()
        print(
            "Waiting for make dropdown..."
        )

        page.wait_for_selector(
            '[data-testid="make"]',
            state="attached",
            timeout=15000
        )

        print(
            "Make dropdown found."
        )

        # --------------------------------------------------
        # Get make dropdown
        # --------------------------------------------------

        make_select = page.locator(
            '[data-testid="make"]'
        )

        makes = make_select.locator(
            "option"
        )

        make_count = makes.count()

        print()
        print(
            f"Found {make_count} make options."
        )

        # --------------------------------------------------
        # Store results
        # --------------------------------------------------

        models = {}

        # --------------------------------------------------
        # Process every make
        # --------------------------------------------------

        for i in range(make_count):

            option = makes.nth(i)

            make_value = option.get_attribute(
                "value"
            )

            raw_make_name = option.inner_text()

            make_name = clean_name(
                raw_make_name
            )

            # Skip empty / placeholder options
            if not make_value or not make_name:
                continue

            print()
            print(
                f"[{i + 1}/{make_count}] {make_name}"
            )

            # --------------------------------------------------
            # Select make
            # --------------------------------------------------

            make_select.select_option(
                value=make_value
            )

            # Give AutoTrader time to update the
            # model dropdown.
            page.wait_for_timeout(500)

            # --------------------------------------------------
            # Get model dropdown
            # --------------------------------------------------

            model_select = page.locator(
                '[data-testid="model"]'
            )

            model_options = model_select.locator(
                "option"
            )

            model_count = model_options.count()

            make_models = []

            # --------------------------------------------------
            # Extract models
            # --------------------------------------------------

            for j in range(model_count):

                model_option = model_options.nth(j)

                model_value = (
                    model_option.get_attribute(
                        "value"
                    )
                )

                raw_model_name = (
                    model_option.inner_text()
                )

                model_name = clean_name(
                    raw_model_name
                )

                # Skip empty / placeholder options
                if (
                    not model_value
                    or not model_name
                ):
                    continue

                make_models.append({
                    "name": model_name,
                    "value": model_value
                })

            models[make_name] = make_models

            print(
                f"    Found {len(make_models)} models"
            )

        # --------------------------------------------------
        # Check for leftover counts
        # --------------------------------------------------

        print()
        print(
            "Checking generated names..."
        )

        bad_names = []

        for make, make_models in models.items():

            if re.search(
                r"\(\d[\d,]*\)$",
                make
            ):

                bad_names.append(
                    f"MAKE: {make}"
                )

            for model in make_models:

                if re.search(
                    r"\(\d[\d,]*\)$",
                    model["name"]
                ):

                    bad_names.append(
                        f"MODEL: {make} -> "
                        f"{model['name']}"
                    )

        if bad_names:

            print()
            print(
                "WARNING: Found names with "
                "trailing numbers:"
            )

            for name in bad_names:

                print(
                    f"    {name}"
                )

        else:

            print(
                "No trailing listing counts found."
            )

        # --------------------------------------------------
        # Save JSON
        # --------------------------------------------------

        with open(
            MODELS_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                models,
                file,
                indent=4,
                ensure_ascii=False
            )

        # --------------------------------------------------
        # Summary
        # --------------------------------------------------

        total_models = sum(
            len(make_models)
            for make_models in models.values()
        )

        print()
        print("=" * 60)
        print(
            "MODEL DATABASE COMPLETE"
        )
        print("=" * 60)

        print(
            f"Makes: {len(models)}"
        )

        print(
            f"Models: {total_models}"
        )

        print(
            f"Saved to: {MODELS_FILE}"
        )

        print("=" * 60)

        browser.close()


if __name__ == "__main__":

    get_autotrader_models()