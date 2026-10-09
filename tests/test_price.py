import json
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from backend.services.price import (
    PageData, checked_url, get_prices, money, pack_details, pharmacy_quotes,
    product_identity, read_netmeds, read_pharmeasy, read_structured_offers, read_tata1mg,
)
from backend.services.response import build_price_comparison


def state_page(state, next_data=False):
    if next_data:
        return PageData('<script id="__NEXT_DATA__" type="application/json">' +
                        json.dumps({"props": {"pageProps": state}}) + '</script>')
    return PageData('<script>window.__INITIAL_STATE__ = ' + json.dumps(state) + ';</script>')


class PriceTests(unittest.TestCase):
    def test_product_matching_does_not_confuse_strength_or_release(self):
        self.assertEqual(product_identity("Augmentin 625 Duo Tablet"),
                         product_identity("Augmentin Duo 625Mg Strip Of 10 Tablets"))
        self.assertEqual(product_identity("Augmentin 625 Duo Tablet"),
                         product_identity("Augmentin 625 DUO Tablet 10'S"))
        self.assertNotEqual(product_identity("Example 650 Tablet"), product_identity("Example 65 Tablet"))
        self.assertNotEqual(product_identity("Example 650 Tablet"), product_identity("Example 650 Tablet SR"))
        self.assertNotEqual(product_identity("Example 650 Tablet"), product_identity("Example 650 Capsule"))

    def test_invalid_prices_and_pack_sizes(self):
        for value in (None, True, "not a price", "NaN", "Infinity", "-2", "0"):
            self.assertIsNone(money(value))
        self.assertEqual(money("₹1,234.50"), 1234.5)
        self.assertEqual(pack_details("10 Tablet(s) in Strip"), (10, "tablet"))
        self.assertEqual(pack_details("Example 625mg Tablet 6's"), (6, "tablet"))
        self.assertEqual(pack_details("500mg Tablet"), (None, None))
        self.assertEqual(pack_details("Moxikind-CV 625 Tablet 10's"), (10, "tablet"))
        self.assertEqual(pack_details("Moxikind-CV 625 Tablet"), (None, None))

    def test_pharmeasy_uses_assured_price_instead_of_conditional_offer(self):
        page = state_page({"productDetails": {
            "name": "Example 650mg Strip Of 10 Tablets", "slug": "example-1",
            "measurementUnit": "10 Tablet(s) in Strip", "costPrice": "100",
            "salePrice": "60", "assuredDiscountPrice": "90", "isBestOfferApplied": True,
        }}, next_data=True)
        quote = read_pharmeasy(page, "https://pharmeasy.in/online-medicine-order/example-1")[0]
        self.assertEqual(quote["price"], 90)
        self.assertEqual(quote["unit_price"], 9)
        self.assertFalse(quote["conditional"])

    def test_tata1mg_keeps_offer_conditions_and_ignores_other_skus(self):
        page = state_page({"drugPageReducer": {
            "staticData": {"sku": {"name": "Example 650 Tablet"}},
            "dynamicData": {"priceBox": {
                "packSizes": "10 tablets", "selected": "main",
                "priceList": [{"type": "main", "mrp": {"price": "₹100"},
                               "discount": {"price": "₹80", "tnc": "on orders above ₹1200"},
                               "bestPrice": {"price": "₹1"}}],
            }},
        }})
        quote = read_tata1mg(page, "https://www.1mg.com/drugs/example-1")[0]
        self.assertEqual(quote["price"], 80)
        self.assertTrue(quote["conditional"])
        self.assertIn("1200", quote["conditions"][0])

    def test_netmeds_reads_only_product_price_and_currency(self):
        page = state_page({"productListingPage": {"productlists": {"items": [{
            "name": "Example 650 Tablet 10'S", "url": "/product/example-1",
            "price": {"effective": {"min": 80, "max": 80, "currency_code": "INR"},
                      "marked": {"min": 100}},
            "attributes": {"mstar-packlabel": "10 Tablet(s) in a Strip", "quantity": 1000},
        }]}}})
        quote = read_netmeds(page, "https://www.netmeds.com/products/")[0]
        self.assertEqual(quote["price"], 80)
        self.assertEqual(quote["unit_price"], 8)

    def test_apollo_structured_offer_does_not_invent_mrp(self):
        page = PageData('<script type="application/ld+json">' + json.dumps({
            "@type": "MedicalWebPage", "mainEntity": {"@type": "Drug",
                "proprietaryName": "Example 650 Tablet 10's",
                "offers": {"priceCurrency": "INR", "price": 95}},
        }) + '</script>')
        quote = read_structured_offers(page, "https://www.apollopharmacy.in/medicine/example")[0]
        self.assertEqual(quote["price"], 95)
        self.assertIsNone(quote["mrp"])

    def test_failures_are_explicit_and_wrong_products_are_excluded(self):
        for error, expected in [(URLError("failed"), "network_error"),
                                (HTTPError("url", 403, "Forbidden", {}, None), "access_denied")]:
            with patch("backend.services.price.fetch_page", side_effect=error):
                quote = pharmacy_quotes("Example 650 Tablet", "pharmeasy", {})[0]
            self.assertEqual(quote["status"], expected)
            self.assertIsNone(quote["price"])
        html = '<script id="__NEXT_DATA__">' + json.dumps({"props": {"pageProps": {
            "productList": [{"name": "Example 65 Tablet", "salePriceDecimal": 80}],
        }}}) + '</script>'
        with patch("backend.services.price.fetch_page", return_value=html):
            quote = pharmacy_quotes("Example 650 Tablet", "pharmeasy", {})[0]
        self.assertEqual(quote["status"], "product_not_found")

    def test_five_sources_and_deduplicated_names(self):
        with patch("backend.services.price.pharmacy_quotes", return_value=[{"status": "network_error", "price": None}]) as reader:
            result = get_prices(["Example Tablet", "Example Tablet"])
        self.assertEqual(reader.call_count, 5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "no_prices")
        self.assertEqual(len(result[0]["quotes"]), 5)

    def test_price_module_does_not_accept_blocked_availability_intent(self):
        with patch("backend.services.price.fetch_page") as fetch:
            with self.assertRaises(ValueError):
                get_prices(["Example"], intent="availability")
        fetch.assert_not_called()

    def test_invalid_input_has_a_consistent_validation_error(self):
        for names in (None, "Example", [None], [" "], (name for name in ["Example"])):
            with self.assertRaises(ValueError):
                get_prices(names)

    def test_urls_cannot_fetch_arbitrary_hosts(self):
        for url in ("http://pharmeasy.in/product", "https://localhost/product",
                    "https://pharmeasy.in.evil.example/product", "https://user@pharmeasy.in/product"):
            with self.assertRaises(ValueError):
                checked_url(url, "pharmeasy")

    def test_savings_use_units_and_require_composition_form_and_unconditional_price(self):
        original = {"name": "Original Tablet", "regulatory": "OTC",
                    "composition": [{"drug": "Example", "strength": "500mg"}]}
        substitute = {**original, "name": "Substitute Tablet"}
        def price(name, pack_price, quantity):
            return {"medicine": name, "status": "ok", "quotes": [{"pharmacy": "pharmeasy",
                "status": "ok", "price": pack_price, "pack_quantity": quantity,
                "unit": "tablet", "unit_price": pack_price / quantity, "conditional": False}]}
        prices = {original["name"]: price(original["name"], 100, 10),
                  substitute["name"]: price(substitute["name"], 48, 6)}
        result = build_price_comparison(original, [substitute], prices)
        self.assertEqual(result["alternatives"][0]["savings"][0]["percent"], 20)
        self.assertNotIn("max_potential_savings_percent", result)
        prices[substitute["name"]]["quotes"][0]["conditional"] = True
        self.assertEqual(build_price_comparison(original, [substitute], prices)["alternatives"][0]["savings"], [])
        prices[substitute["name"]]["quotes"][0]["conditional"] = False
        substitute["composition"] = [{"drug": "Example", "strength": "250mg"}]
        self.assertFalse(build_price_comparison(original, [substitute], prices)["alternatives"][0]["composition_match"])
        substitute["composition"] = original["composition"]
        substitute["name"] = "Substitute Tablet SR"
        self.assertEqual(build_price_comparison(original, [substitute], prices)["alternatives"][0]["savings"], [])


if __name__ == "__main__":
    unittest.main()
