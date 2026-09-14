import contextlib
import contextlib
from pathlib import Path
from datetime import datetime

import streamlit as st
from playwright.sync_api import sync_playwright

import underwriter
import comparables
import autotrader_offline


CASES_DIR = Path("cases")


def case_path_from_lot(lot_number: str) -> Path:
    cleaned = "".join(ch for ch in (lot_number or "").strip() if ch.isdigit())
    if not cleaned:
        raise ValueError("Enter a numeric Copart lot number")
    return CASES_DIR / cleaned


def lot_url(lot_number: str) -> str:
    cleaned = "".join(ch for ch in (lot_number or "").strip() if ch.isdigit())
    return f"https://www.copart.co.uk/lot/{cleaned}"


def ensure_case(case_dir: Path, url: str):
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "photos").mkdir(exist_ok=True)

    capture_path = case_dir / "capture.json"
    if not capture_path.exists():
        underwriter.save_json(
            capture_path,
            {
                "requested_url": url,
                "captured_url": None,
                "captured_at": underwriter.utc_now(),
                "lot_number": case_dir.name,
                "capture_type": "ui_prepared",
                "automatic_gallery_collection": False,
            },
        )

    settings_path = case_dir / "settings.json"
    if not settings_path.exists():
        underwriter.save_json(settings_path, underwriter.DEFAULT_SETTINGS)

    listing_path = case_dir / "listing.txt"
    if not listing_path.exists():
        listing_path.write_text("", encoding="utf-8")


@contextlib.contextmanager
def connect_cdp_page(
    cdp_url: str,
    target_url: str | None = None,
    *,
    navigate: bool = False,
):
    if not cdp_url:
        raise ValueError("Set CDP URL (e.g. http://127.0.0.1:9222)")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()

        page = None
        # Prefer an existing tab to avoid reloading/navigating unexpectedly.
        if target_url and context.pages:
            for candidate in context.pages:
                if candidate.url == target_url:
                    page = candidate
                    break
            if page is None:
                # Fall back to a "starts with" match (query params, anchors, etc).
                for candidate in context.pages:
                    if candidate.url.startswith(target_url):
                        page = candidate
                        break

        if page is None and context.pages:
            page = context.pages[0]

        if page is None:
            page = context.new_page()

        if navigate and target_url:
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

        yield page


def capture_listing_and_photos(case_dir: Path, cdp_url: str, url: str):
    ensure_case(case_dir, url)

    with connect_cdp_page(cdp_url, url, navigate=False) as page:
        if not page.url.startswith(url):
            raise RuntimeError(
                "UI will not navigate/reload your tab during capture. "
                f"Open the lot page in Chrome first.\n\nExpected: {url}\n"
                f"Current: {page.url}"
            )
        underwriter.try_reveal_vrn(page)
        body_text = page.locator("body").inner_text(timeout=20000)
        if any(
            marker.lower() in body_text.lower()
            for marker in underwriter.IMPERVA_MARKERS
        ):
            raise RuntimeError(
                "Imperva/security-check page detected. In Chrome, complete the "
                "checkbox/challenge, then refresh the lot page and try again."
            )

        captured_at = underwriter.utc_now()
        (case_dir / "listing.txt").write_text(body_text, encoding="utf-8")
        page.screenshot(path=str(case_dir / "listing.png"), full_page=True)

        capture_data = underwriter.load_json(case_dir / "capture.json")
        capture_data.update(
            {
                "requested_url": url,
                "captured_url": page.url,
                "captured_at": captured_at,
                "capture_type": "ui_cdp",
                "listing_parsed": underwriter.parse_copart_listing_text(body_text),
            }
        )
        underwriter.save_json(case_dir / "capture.json", capture_data)

        gallery = underwriter.download_gallery_images(page, case_dir)
        capture_data["automatic_gallery_collection"] = gallery["downloaded"] > 0
        underwriter.save_json(case_dir / "capture.json", capture_data)

        settings = underwriter.load_json(case_dir / "settings.json")
        listing_parsed = capture_data.get("listing_parsed") or {}
        if listing_parsed.get("vat_to_add_to_final_price") is False:
            settings["hammer_vat_rate"] = 0
        if listing_parsed.get("odometer") is not None:
            settings["wbac"]["mileage"] = listing_parsed["odometer"]
        if listing_parsed.get("vrn"):
            settings["wbac"]["registration"] = listing_parsed["vrn"]
        if gallery["downloaded"] > 0:
            settings["expected_gallery_images"] = gallery["downloaded"]
            settings["photos_complete_confirmed"] = False
        underwriter.save_json(case_dir / "settings.json", settings)

    return gallery


def open_lot_in_browser(cdp_url: str, url: str):
    with connect_cdp_page(cdp_url, url, navigate=True) as page:
        try:
            page.bring_to_front()
        except Exception:
            pass
        return page.url


def capture_wbac(case_dir: Path, cdp_url: str, url: str | None = None):
    ensure_case(case_dir, lot_url(case_dir.name))
    with connect_cdp_page(cdp_url, url, navigate=False) as page:
        if url and not page.url.startswith(url):
            raise RuntimeError(
                "Open the WBAC valuation page in Chrome first (the UI won't "
                "navigate/reload during capture).\n\n"
                f"Expected: {url}\nCurrent: {page.url}"
            )
        body_text = page.locator("body").inner_text(timeout=20000)
        candidates = underwriter.extract_gbp_amounts(body_text)
        chosen = underwriter.choose_reasonable_value(candidates)

        screenshot_name = f"wbac_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        page.screenshot(path=str(case_dir / screenshot_name), full_page=True)

        underwriter.save_json(
            case_dir / "wbac_capture.json",
            {
                "captured_at": underwriter.utc_now(),
                "captured_url": page.url,
                "candidates_gbp": candidates,
                "chosen_value_gbp": chosen,
                "evidence_file": screenshot_name,
            },
        )

        settings = underwriter.load_json(case_dir / "settings.json")
        settings.setdefault("wbac", {})
        settings["wbac"]["value"] = chosen
        settings["wbac"]["evidence_file"] = screenshot_name
        settings["wbac"]["captured_at"] = underwriter.utc_now()
        settings["wbac"]["captured_url"] = page.url
        settings["wbac"]["candidate_values_gbp"] = candidates
        underwriter.save_json(case_dir / "settings.json", settings)

    return {"candidates": candidates, "chosen": chosen, "screenshot": screenshot_name}


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


st.set_page_config(page_title="Car Underwriter", layout="wide")
st.title("Car Underwriter")

with st.sidebar:
    st.header("Lot")
    lot = st.text_input("Copart lot number", value="", placeholder="e.g. 67067136")
    cdp = st.text_input(
        "CDP URL (existing Chrome session)",
        value="http://127.0.0.1:9222",
        help="Start Chrome with --remote-debugging-port=9222 and log in to Copart.",
    )

    if lot:
        url = lot_url(lot)
        st.caption(url)
    else:
        url = None

col_a, col_b = st.columns([1, 1])

if not lot:
    st.info("Enter a lot number in the sidebar.")
    st.stop()

case_dir = case_path_from_lot(lot)
ensure_case(case_dir, url)

with col_a:
    st.subheader("Actions")
    if st.button("Open lot in browser (CDP)"):
        with st.spinner("Opening lot page in your existing Chrome session..."):
            opened = open_lot_in_browser(cdp, url)
        st.session_state["lot_opened"] = True
        st.success(f"Opened: {opened}")

    st.caption(
        "Before capturing: in the browser, click the masked VRN/VIN element to "
        "reveal the registration (if available) and make sure the Photos gallery "
        "is visible."
    )
    ready = st.checkbox(
        "I revealed VRN (if possible) and the Photos gallery is visible",
        value=False,
    )
    if st.button("Capture listing + download photos (CDP)", disabled=not ready):
        with st.spinner("Capturing listing and downloading gallery images..."):
            result = capture_listing_and_photos(case_dir, cdp, url)
        st.success(f"Downloaded {result['downloaded']} images.")
        if result["errors"]:
            st.warning("Some downloads failed. See `gallery.json` for details.")

    st.divider()
    wbac_url = st.text_input(
        "WBAC URL (optional)",
        value="",
        placeholder="Leave blank if your active tab is the WBAC valuation page.",
    )
    if st.button("Capture WBAC value (screenshot + extract £)"):
        with st.spinner("Capturing WBAC evidence from your browser session..."):
            result = capture_wbac(case_dir, cdp, wbac_url or None)
        st.success(
            f"WBAC value: {result['chosen']} (saved {result['screenshot']})"
        )

    st.divider()
    if st.button("Run underwriting (analyse)"):
        with st.spinner("Running analysis (sends listing/photos to AI if configured)..."):
            underwriter.analyse(case_dir, consent=True)
        st.success("Analysis complete. Open report.md below.")

with col_b:
    st.subheader("Edit settings")
    settings_path = case_dir / "settings.json"
    settings = underwriter.load_json(settings_path)

    with st.form("settings_form"):
        capital_limit = st.number_input(
            "Capital limit (£)", min_value=0.0, value=float(settings["capital_limit"])
        )
        target_roi = st.number_input(
            "Target ROI (e.g. 0.2 = 20%)",
            min_value=0.0,
            value=float(settings["target_roi"]),
            step=0.01,
        )
        transport = st.number_input(
            "Delivery / transport incl VAT (£)",
            min_value=0.0,
            value=float(settings.get("transport_including_vat") or 0),
        )
        ulez = st.selectbox(
            "ULEZ",
            options=["UNKNOWN", "YES", "NO"],
            index=["UNKNOWN", "YES", "NO"].index(settings.get("ulez", "UNKNOWN")),
        )
        ulez_evidence = st.text_input(
            "ULEZ evidence (source + timestamp)",
            value=settings.get("ulez_evidence", ""),
        )
        hammer_vat_rate = st.selectbox(
            "Hammer VAT rate",
            options=[0.0, 0.2],
            index=0 if float(settings.get("hammer_vat_rate") or 0) == 0 else 1,
            help="0.0 if listing says VAT not added to final price; otherwise 0.2.",
        )

        st.markdown("### WBAC")
        wbac_value = st.number_input(
            "WBAC value (£)",
            min_value=0.0,
            value=float(settings.get("wbac", {}).get("value") or 0),
        )
        wbac_reg = st.text_input(
            "WBAC registration",
            value=settings.get("wbac", {}).get("registration", ""),
        )
        wbac_mileage = st.number_input(
            "WBAC mileage",
            min_value=0,
            value=int(settings.get("wbac", {}).get("mileage") or 0),
            step=1,
        )
        cat_n_declared = st.checkbox(
            "Cat N declared (WBAC)",
            value=bool(settings.get("wbac", {}).get("cat_n_declared", False)),
        )
        basis_confirmed = st.checkbox(
            "Repaired-condition basis confirmed (WBAC)",
            value=bool(
                settings.get("wbac", {}).get(
                    "repaired_condition_basis_confirmed", False
                )
            ),
        )

        st.markdown("### Exit prices (preferred over WBAC)")
        exit_settings = settings.get("exit") or {}
        exit_source = st.selectbox(
            "Exit source label",
            options=["COMPARABLES", "UNDERWRITTEN", "WBAC", "EXIT"],
            index=0
            if (exit_settings.get("source") in {None, "", "COMPARABLES"})
            else ["COMPARABLES", "UNDERWRITTEN", "WBAC", "EXIT"].index(
                exit_settings.get("source")
            ),
            help="Used only for reporting; the tool uses the first non-empty exit price.",
        )
        advert_price = st.number_input(
            "Advert price (£)",
            min_value=0.0,
            value=float(exit_settings.get("advert_price") or 0),
        )
        underwritten_sale_price = st.number_input(
            "Underwritten sale price (£)",
            min_value=0.0,
            value=float(exit_settings.get("underwritten_sale_price") or 0),
        )
        quick_sale_price = st.number_input(
            "Quick-sale price (£)",
            min_value=0.0,
            value=float(exit_settings.get("quick_sale_price") or 0),
        )
        trade_fallback_price = st.number_input(
            "Trade fallback (£) (optional)",
            min_value=0.0,
            value=float(exit_settings.get("trade_fallback_price") or 0),
        )

        submitted = st.form_submit_button("Save settings.json")
        if submitted:
            settings["capital_limit"] = capital_limit
            settings["target_roi"] = target_roi
            settings["transport_including_vat"] = transport
            settings["ulez"] = ulez
            settings["ulez_evidence"] = ulez_evidence
            settings["hammer_vat_rate"] = hammer_vat_rate
            settings.setdefault("wbac", {})
            settings["wbac"]["value"] = wbac_value if wbac_value > 0 else None
            settings["wbac"]["registration"] = wbac_reg
            settings["wbac"]["mileage"] = wbac_mileage if wbac_mileage > 0 else None
            settings["wbac"]["cat_n_declared"] = cat_n_declared
            settings["wbac"]["repaired_condition_basis_confirmed"] = basis_confirmed
            settings["exit"] = {
                "source": exit_source,
                "advert_price": advert_price if advert_price > 0 else None,
                "underwritten_sale_price": (
                    underwritten_sale_price
                    if underwritten_sale_price > 0
                    else None
                ),
                "quick_sale_price": quick_sale_price if quick_sale_price > 0 else None,
                "trade_fallback_price": (
                    trade_fallback_price if trade_fallback_price > 0 else None
                ),
            }
            underwriter.save_json(settings_path, settings)
            st.success("Saved.")

st.divider()
st.subheader("Outputs")
tabs = st.tabs(
    ["report.md", "capture.json", "gallery.json", "comparables", "listing.txt"]
)

with tabs[0]:
    report_path = case_dir / "report.md"
    st.code(load_text(report_path) or "(no report.md yet)", language="markdown")

with tabs[1]:
    st.code(load_text(case_dir / "capture.json"), language="json")

with tabs[2]:
    st.code(load_text(case_dir / "gallery.json") or "(no gallery.json yet)", language="json")

with tabs[3]:
    st.subheader("Comparables (manual)")
    comps = comparables.load_comparables(case_dir)
    if comps:
        st.caption(f"{len(comps)} saved")
        st.code(
            (case_dir / "comparables.json").read_text(encoding="utf-8"),
            language="json",
        )
    else:
        st.caption("No comparables saved yet.")

    with st.form("add_comp"):
        platform = st.selectbox(
            "Platform",
            options=["FACEBOOK_MARKETPLACE", "AUTOTRADER", "OTHER"],
            index=0,
        )
        status = st.selectbox(
            "Status",
            options=[
                "ACTIVE",
                "PRICE_REDUCED",
                "MARKED_SOLD_PRICE_UNKNOWN",
                "REMOVED_OUTCOME_UNKNOWN",
                "SALE_PRICE_CONFIRMED",
            ],
            index=0,
        )
        comp_url = st.text_input("URL", value="")
        comp_title = st.text_input("Title", value="")
        comp_price = st.number_input("Asking price (£)", min_value=0.0, value=0.0)
        comp_sale = st.number_input(
            "Confirmed sale price (£) (optional)", min_value=0.0, value=0.0
        )
        comp_notes = st.text_area("Notes", value="", height=80)
        add = st.form_submit_button("Add comparable")
        if add:
            item = comparables.Comparable(
                platform=platform,
                url=comp_url,
                title=comp_title or None,
                status=status,
                asking_price_gbp=comp_price if comp_price > 0 else None,
                transaction_price_gbp=comp_sale if comp_sale > 0 else None,
                first_seen=comparables.utc_now(),
                last_checked=comparables.utc_now(),
                notes=comp_notes or None,
            )
            comps.append(item)
            comparables.save_comparables(case_dir, comps)
            st.success("Saved comparable.")

    if st.button("Compute exit tiers from comparables"):
        tiers = comparables.compute_exit_tiers(comps)
        settings = underwriter.load_json(settings_path)
        settings.setdefault("exit", {})
        settings["exit"]["source"] = "COMPARABLES"
        settings["exit"]["advert_price"] = tiers.get("advert_price")
        settings["exit"]["underwritten_sale_price"] = tiers.get(
            "underwritten_sale_price"
        )
        settings["exit"]["quick_sale_price"] = tiers.get("quick_sale_price")
        if settings.get("wbac", {}).get("value"):
            settings["exit"]["trade_fallback_price"] = settings["wbac"]["value"]
        underwriter.save_json(settings_path, settings)
        st.success(
            f"Updated settings.exit from {tiers.get('sample_size')} comparables "
            f"(confidence: {tiers.get('confidence')})."
        )

    st.divider()
    st.subheader("Import Auto Trader (offline)")
    st.caption(
        "Save an Auto Trader search results page as HTML in your browser, then "
        "upload it here to extract listing URLs/prices. This tool does not "
        "crawl Auto Trader."
    )
    uploaded = st.file_uploader(
        "Upload saved Auto Trader HTML",
        type=["html", "htm"],
        accept_multiple_files=False,
    )
    if uploaded is not None:
        html = uploaded.getvalue().decode("utf-8", errors="replace")
        listings = autotrader_offline.extract_listings_from_saved_html(html)
        st.write(f"Found {len(listings)} listings in the saved page.")
        if listings:
            st.dataframe(
                [
                    {
                        "title": l.title,
                        "price_gbp": l.price_gbp,
                        "url": l.url,
                    }
                    for l in listings[:50]
                ],
                use_container_width=True,
            )
            default_status = st.selectbox(
                "Imported status",
                options=["ACTIVE", "PRICE_REDUCED", "MARKED_SOLD_PRICE_UNKNOWN"],
                index=0,
            )
            if st.button("Add all imported as comparables"):
                for listing in listings:
                    comps.append(
                        comparables.Comparable(
                            platform="AUTOTRADER",
                            url=listing.url,
                            title=listing.title,
                            status=default_status,  # type: ignore[arg-type]
                            asking_price_gbp=listing.price_gbp,
                            first_seen=comparables.utc_now(),
                            last_checked=comparables.utc_now(),
                            notes="Imported from saved Auto Trader HTML.",
                        )
                    )
                comparables.save_comparables(case_dir, comps)
                st.success(f"Added {len(listings)} comparables.")

with tabs[4]:
    listing_path = case_dir / "listing.txt"
    edited = st.text_area(
        "listing.txt",
        value=load_text(listing_path),
        height=300,
    )
    if st.button("Save listing.txt"):
        listing_path.write_text(edited or "", encoding="utf-8")
        st.success("Saved listing.txt")
