"""Public pharmacy price readers. No private API, stock checks, or browser needed.

Prices are public page observations, not checkout quotes. Unreadable pages and
unmapped products return explicit statuses. Never extract arbitrary numbers
from page text: only read each site's product-specific structured pricing data.
"""

from backend.config.settings import CONSTANTS, PROJECT_ROOT

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


CATALOGUE_PATH = PROJECT_ROOT / CONSTANTS["paths"]["pharmacy_catalogue"]
TIMEOUT = CONSTANTS["pricing"]["timeout_seconds"]
MAX_PAGE_BYTES = CONSTANTS["pricing"]["max_page_bytes"]
PHARMACIES = CONSTANTS["pharmacies"]


def plain_text(value):
    return " ".join(unescape(re.sub(CONSTANTS["patterns"]["html_tag"], CONSTANTS["patterns"]["single_space"], str(value or ""))).split())


def product_identity(name):
    """Compare brand, strength, and form while ignoring pack-count formatting."""
    name = plain_text(name).casefold()
    name = re.sub(CONSTANTS["patterns"]["remove_pack_prefix"], CONSTANTS["patterns"]["remove_text"], name)
    name = re.sub(CONSTANTS["patterns"]["remove_pack_suffix"], CONSTANTS["patterns"]["capture_first_group"], name)
    name = re.sub(CONSTANTS["patterns"]["split_lowercase_numbers"], CONSTANTS["patterns"]["single_space"], name)
    tokens = re.findall(CONSTANTS["patterns"]["word_or_number"], name)
    aliases = CONSTANTS["matching"]["unit_aliases"]
    return sorted(aliases.get(token, token) for token in tokens if token not in set(CONSTANTS["matching"]["ignored_product_tokens"]))


def money(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).replace(CONSTANTS["pricing"]["currency_symbol"], "").replace(",", "").strip())
        if not number.is_finite() or number <= 0:
            return None
        return float(number.quantize(Decimal(CONSTANTS["pricing"]["money_quantum"])))
    except InvalidOperation:
        return None


def pack_details(text):
    text = plain_text(text).casefold()
    # Product names often contain strengths like "625 Tablet". Only explicit
    # pack patterns count; a strength must never become a pack quantity.
    match = re.search(CONSTANTS["patterns"]["pack_quantity_after_form"], text)
    if match:
        return int(match[2]), match[1].rstrip("s")
    match = re.search(CONSTANTS["patterns"]["pack_quantity_before_form"], text)
    if not match:
        return None, None
    return int(match[1]), match[2].rstrip("s")


def checked_url(url, pharmacy):
    parsed = urlparse(url)
    if (parsed.scheme != CONSTANTS["pricing"]["scheme"] or parsed.hostname != PHARMACIES[pharmacy]["host"]
            or parsed.username or parsed.password or parsed.port not in CONSTANTS["pricing"]["allowed_ports"]):
        raise ValueError(CONSTANTS["messages"]["invalid_pharmacy_url"])
    return url


class PharmacyRedirectHandler(HTTPRedirectHandler):
    def __init__(self, pharmacy):
        self.pharmacy = pharmacy

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        checked_url(newurl, self.pharmacy)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def fetch_page(url, pharmacy):
    checked_url(url, pharmacy)
    request = Request(url, headers={"User-Agent": CONSTANTS["pricing"]["user_agent"],
                                    "Accept": CONSTANTS["pricing"]["accept"]})
    opener = build_opener(PharmacyRedirectHandler(pharmacy))
    with opener.open(request, timeout=TIMEOUT) as response:
        raw = response.read(MAX_PAGE_BYTES + 1)
        if len(raw) > MAX_PAGE_BYTES:
            raise ValueError(CONSTANTS["messages"]["pharmacy_page_too_large"])
        return raw.decode("utf-8", errors="replace")


class PageData(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.scripts, self.links = [], []
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.current = [attrs, ""]
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])

    def handle_data(self, data):
        if self.current is not None:
            self.current[1] += data

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.scripts.append(self.current)
            self.current = None

    def state(self, next_data=False):
        for attrs, body in self.scripts:
            if next_data and attrs.get("id") == "__NEXT_DATA__":
                return json.loads(body).get("props", {}).get("pageProps", {})
            if not next_data:
                match = re.search(CONSTANTS["patterns"]["initial_state_assignment"], body)
                if match:
                    return json.JSONDecoder().raw_decode(body[match.end():])[0]
        return {}


def quote_data(name, url, price, mrp=None, pack=None, conditions=None):
    price = money(price)
    quantity, unit = pack_details(pack or name)
    return {
        "product_name": plain_text(name), "product_url": url,
        "price": price, "mrp": money(mrp), "currency": CONSTANTS["pricing"]["currency"],
        "pack_size": plain_text(pack or name), "pack_quantity": quantity, "unit": unit,
        "unit_price": round(price / quantity, CONSTANTS["pricing"]["unit_precision"]) if price and quantity else None,
        "conditions": conditions or [], "conditional": bool(conditions),
        "price_basis": "public_page", "status": "ok" if price else "price_not_found",
    }


def read_pharmeasy(page, url):
    state = page.state(next_data=True)
    products = ([state["productDetails"]] if state.get("productDetails") else
                state.get("genericsProductList", []) + state.get("productList", []))
    quotes = []
    for row in products:
        best_offer = row.get("isBestOfferApplied", False)
        # Best-offer sale prices can require a minimum basket. Prefer the
        # separately published assured price when available.
        price = row.get("assuredDiscountPrice") if best_offer else None
        conditions = []
        if not price:
            price = row.get("salePrice", row.get("salePriceDecimal"))
            if best_offer:
                conditions = [CONSTANTS["messages"]["conditional_best_offer"]]
        quotes.append(quote_data(
            row.get("seoH1Tag") or row.get("name", ""),
            urljoin(url, PHARMACIES["pharmeasy"]["product_path"] + row["slug"]) if row.get("slug") else url,
            price, row.get("costPrice", row.get("mrpDecimal")),
            row.get("measurementUnit"), conditions,
        ))
    return quotes


def read_netmeds(page, url):
    state = page.state()
    rows = state.get("productListingPage", {}).get("productlists", {}).get("items", [])
    product = state.get("productDetailsPage", {}).get("product", {})
    if product.get("name"):
        rows = [product]
    quotes = []
    for row in rows:
        effective = row.get("price", {}).get("effective", {})
        marked = row.get("price", {}).get("marked", {})
        if effective.get("currency_code") != CONSTANTS["pricing"]["currency"]:
            continue
        conditions = []
        if effective.get("min") != effective.get("max"):
            conditions = [CONSTANTS["messages"]["seller_price_variation"]]
        quotes.append(quote_data(
            row.get("name", ""), urljoin(url, row.get("url") or PHARMACIES["netmeds"]["product_path"] + row.get("slug", "")),
            effective.get("min"), marked.get("min"),
            row.get("attributes", {}).get("mstar-packlabel"), conditions,
        ))
    return quotes


def read_tata1mg(page, url):
    drug = page.state().get("drugPageReducer", {})
    sku = drug.get("staticData", {}).get("sku", {})
    dynamic = drug.get("dynamicData", {})
    box = dynamic.get("priceBox", {})
    prices = box.get("priceList", [])
    if not sku.get("name") or not prices:
        return []
    selected = next((row for row in prices if row.get("type") == box.get("selected")), prices[0])
    discount = selected.get("discount") or {}
    conditions = []
    if discount.get("tnc"):
        conditions.append(plain_text(discount["tnc"]))
    if discount.get("isCp"):
        conditions.append(CONSTANTS["messages"]["membership_price"])
    return [quote_data(sku["name"], url, discount.get("price"),
                       (selected.get("mrp") or {}).get("price"),
                       box.get("packSizes"), conditions)]


def read_structured_offers(page, url):
    """Read only top-level Product/Drug data, never unrelated recommendations."""
    quotes = []
    for attrs, body in page.scripts:
        if attrs.get("type") != "application/ld+json":
            continue
        data = json.loads(body)
        nodes = data if isinstance(data, list) else data.get("@graph", [data])
        for node in nodes:
            if node.get("@type") == "MedicalWebPage":
                node = node.get("mainEntity", {})
            if node.get("@type") not in {"Product", "Drug"}:
                continue
            offers = node.get("offers", [])
            offers = offers if isinstance(offers, list) else [offers]
            for offer in offers:
                if offer.get("priceCurrency") == CONSTANTS["pricing"]["currency"]:
                    name = node.get("proprietaryName") or node.get("name", "")
                    quotes.append(quote_data(name, url, offer.get("price")))
    return quotes


READERS = {"apollo": read_structured_offers, "pharmeasy": read_pharmeasy,
           "tata1mg": read_tata1mg, "netmeds": read_netmeds, "medplus": read_structured_offers}


def pharmacy_quotes(name, pharmacy, catalogue):
    source = PHARMACIES[pharmacy]
    search_url = source["search"].format(query=quote(name))
    base = {"pharmacy": pharmacy, "pharmacy_name": source["name"], "search_url": search_url,
            "checked_at": datetime.now(timezone.utc).isoformat()}
    urls = catalogue.get(name, {}).get(pharmacy, [])
    if isinstance(urls, str):
        urls = [urls]
    if not urls and pharmacy == "medplus":
        return [{**base, "status": "integration_required", "price": None,
                 "message": CONSTANTS["messages"]["medplus_integration_required"]}]
    try:
        quotes = []
        for url in urls or [search_url]:
            page = PageData(fetch_page(url, pharmacy))
            extracted = READERS[pharmacy](page, url)
            # Search pages may provide links but no prices. Fetch one matching
            # product link if its slug clearly matches the full product identity.
            if not extracted and not urls and pharmacy in {"apollo", "tata1mg"}:
                for link in page.links:
                    path = urlparse(link).path
                    prefix = source["product_path"]
                    if path.startswith(prefix):
                        slug = re.sub(CONSTANTS["patterns"]["trailing_product_id"], CONSTANTS["patterns"]["remove_text"], path.rsplit("/", 1)[-1])
                        if product_identity(slug) == product_identity(name):
                            product_url = checked_url(urljoin(url, link), pharmacy)
                            extracted = READERS[pharmacy](PageData(fetch_page(product_url, pharmacy)), product_url)
                            break
            quotes.extend(row for row in extracted
                          if product_identity(row["product_name"]) == product_identity(name))
        if not quotes:
            return [{**base, "status": "product_not_found" if pharmacy in {"pharmeasy", "netmeds"}
                     else "integration_required", "price": None,
                     "message": CONSTANTS["messages"]["public_price_not_found"]}]
        unique = {row["product_url"]: row for row in quotes}
        return [{**base, **row} for row in unique.values()]
    except HTTPError as error:
        return [{**base, "status": "access_denied" if error.code in CONSTANTS["pricing"]["access_denied_codes"] else "http_error",
                 "price": None, "http_status": error.code}]
    except (URLError, TimeoutError, OSError):
        return [{**base, "status": "network_error", "price": None}]
    except (ValueError, KeyError, TypeError, AttributeError):
        return [{**base, "status": "parse_error", "price": None}]


def get_prices(medicine_names, *, intent="price_comparison"):
    """Return one JSON-ready row per medicine, with quotes from all five stores."""
    if intent not in set(CONSTANTS["routing"]["price_intents"]):
        raise ValueError(CONSTANTS["messages"]["unsupported_price_intent"])
    if not isinstance(medicine_names, (list, tuple)) or any(not isinstance(name, str) or not name.strip() for name in medicine_names):
        raise ValueError(CONSTANTS["messages"]["invalid_medicine_names"])
    names = list(dict.fromkeys(name.strip() for name in medicine_names))
    with CATALOGUE_PATH.open(encoding="utf-8") as file:
        catalogue = json.load(file)
    tasks = [(name, pharmacy) for name in names for pharmacy in PHARMACIES]
    with ThreadPoolExecutor(max_workers=CONSTANTS["pricing"]["max_workers"]) as pool:
        batches = list(pool.map(lambda task: pharmacy_quotes(*task, catalogue), tasks))
    output = []
    source_count = len(PHARMACIES)
    for index, name in enumerate(names):
        quotes = [row for batch in batches[index * source_count:(index + 1) * source_count] for row in batch]
        available = [row for row in quotes if row["status"] == "ok"]
        output.append({"medicine": name, "status": "ok" if available else "no_prices",
                       "quotes": quotes, "successful_pharmacies": len({row["pharmacy"] for row in available}),
                       "note": CONSTANTS["messages"]["public_price_note"]})
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=CONSTANTS["messages"]["price_cli_description"])
    parser.add_argument("medicines", nargs="+")
    args = parser.parse_args()
    print(json.dumps(get_prices(args.medicines), indent=CONSTANTS["display"]["json_indent"], ensure_ascii=True))
