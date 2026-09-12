#!/usr/bin/env python3
"""Regenerate products.csv from products.json.

products.json is the source of truth. The CSV exists so the list is readable at a
glance and so it mirrors the name/address/country column format of the exercise's
own supplied sheets (list_1..list_3).

    python data/make_csv.py
"""

import csv
import json
import pathlib

HERE = pathlib.Path(__file__).parent


def main() -> None:
    products = json.loads((HERE / "products.json").read_text())["products"]
    with (HERE / "products.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["name", "address", "country", "brand", "product", "category"])
        for p in products:
            writer.writerow([
                p["legal_name"], p["hq_address"], p["country"],
                p["brand"], p["product"], p["category"],
            ])
    print(f"wrote products.csv ({len(products)} rows)")


if __name__ == "__main__":
    main()
