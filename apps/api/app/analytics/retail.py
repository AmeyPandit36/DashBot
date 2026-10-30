"""Deterministic synthetic retail dataset (demonstration environment).

The dataset is explicitly synthetic and is labelled as such everywhere it is
surfaced. It is generated with a fixed seed so that every analytical result is
reproducible across environments and test runs.

Business definitions baked into the data contract
-------------------------------------------------
* ``total_amount = quantity * unit_price * (1 - discount)``
  -> net transaction value, *excluding* tax and refunds.
* ``order_id`` is one sales order line per product; a single order_id may carry
  several lines, so "orders" are counted with COUNT(DISTINCT order_id).
"""
from __future__ import annotations

import csv
import io
import random
from datetime import date, timedelta

SEED = 20261030
MONTHS = 24

REGIONS = ["North", "South", "East", "West"]
REGION_WEIGHTS = {"North": 0.28, "South": 0.26, "East": 0.24, "West": 0.22}

CATEGORIES = {
    "Electronics": {
        "price": (180, 950),
        "products": [
            ("Aurora Wireless Headphones", 220),
            ("Nexus 4K Monitor", 480),
            ("Pulse Smart Speaker", 130),
            ("Vertex Mechanical Keyboard", 145),
            ("Orbit Tablet Stand", 65),
        ],
    },
    "Home & Kitchen": {
        "price": (25, 320),
        "products": [
            ("Copper Pour-Over Kettle", 78),
            ("Lumen Table Lamp", 96),
            ("Terra Cast Iron Pan", 62),
            ("Nimbus Air Purifier", 265),
        ],
    },
    "Fashion": {
        "price": (18, 240),
        "products": [
            ("Atlas Denim Jacket", 118),
            ("Meridian Linen Shirt", 74),
            ("Solstice Running Shoes", 132),
            ("Harbor Wool Scarf", 46),
        ],
    },
    "Sports & Outdoors": {
        "price": (22, 420),
        "products": [
            ("Summit Trail Backpack", 165),
            ("Cascade Water Bottle", 32),
            ("Ridge Climbing Rope", 145),
            ("Glacier Camp Stove", 118),
        ],
    },
    "Beauty": {
        "price": (12, 150),
        "products": [
            ("Verdant Facial Serum", 82),
            ("Ember Clay Mask", 38),
            ("Bloom Body Oil", 54),
        ],
    },
}

CUSTOMER_SEGMENTS = ["SMB", "Enterprise", "Consumer"]
SEGMENT_WEIGHTS = [0.45, 0.2, 0.35]


def _month_start(base: date, offset: int) -> date:
    year = base.year + (base.month - 1 + offset) // 12
    month = (base.month - 1 + offset) % 12 + 1
    return date(year, month, 1)


def generate_retail_rows(seed: int = SEED, months: int = MONTHS) -> list[dict]:
    rng = random.Random(seed)
    end_month = _month_start(date(2026, 10, 1), -1)  # last fully completed month
    months_list = [_month_start(end_month, -(months - 1) + i) for i in range(months)]

    products = []
    for category, spec in CATEGORIES.items():
        for name, price in spec["products"]:
            products.append({"product_id": f"P-{len(products) + 101:04d}", "product_name": name,
                             "category": category, "base_price": float(price)})

    customer_ids = [f"C-{i:05d}" for i in range(1, 1201)]
    customer_rows = []
    for idx, cid in enumerate(customer_ids):
        segment = rng.choices(CUSTOMER_SEGMENTS, weights=SEGMENT_WEIGHTS)[0]
        region = rng.choices(REGIONS, weights=[REGION_WEIGHTS[r] for r in REGIONS])[0]
        signup = months_list[0] - timedelta(days=rng.randint(20, 700))
        customer_rows.append({
            "customer_id": cid,
            "customer_name": f"Customer {idx + 1}",
            "segment": segment,
            "region": region,
            "signup_date": signup.isoformat(),
        })

    rows: list[dict] = []
    line = 0
    for m_idx, month in enumerate(months_list):
        # Growth for the first 18 months, then a soft contraction driven by the West region.
        base_orders = int(230 * (1 + 0.018 * m_idx))
        seasonal = 1.0 + (0.12 if month.month in (11, 12) else 0.0) - (0.05 if month.month == 2 else 0.0)
        if m_idx >= months - 3:
            base_orders = int(base_orders * 0.9)
        order_count = max(120, int(base_orders * seasonal))

        for _ in range(order_count):
            order_id = f"ORD-{month.year}{month.month:02d}-{rng.randint(10000, 99999)}"
            customer = rng.choice(customer_rows)
            lines = rng.choices([1, 2, 3], weights=[0.68, 0.24, 0.08])[0]
            order_date = month + timedelta(days=rng.randint(0, 27))
            chosen = rng.sample(products, k=min(lines, len(products)))
            for product in chosen:
                line += 1
                region = customer["region"]
                # West region discounting pressure in the final quarter (a real, explainable pattern).
                region_factor = 1.0
                if m_idx >= months - 3:
                    region_factor = 0.82 if region == "West" else 0.96 if region == "South" else 1.0
                quantity = rng.choices([1, 2, 3, 4, 5, 6], weights=[0.44, 0.27, 0.13, 0.08, 0.05, 0.03])[0]
                if customer["segment"] == "Enterprise":
                    quantity *= 2
                unit_price = round(product["base_price"] * rng.uniform(0.88, 1.12), 2)
                discount = rng.choices([0.0, 0.05, 0.1, 0.15, 0.2, 0.25], weights=[0.42, 0.2, 0.18, 0.1, 0.07, 0.03])[0]
                if m_idx >= months - 3 and region in ("West", "South"):
                    discount = min(0.35, discount + 0.08)
                gross = quantity * unit_price
                total = round(gross * (1 - discount) * region_factor, 2)
                rows.append({
                    "order_id": order_id,
                    "order_date": order_date.isoformat(),
                    "customer_id": customer["customer_id"],
                    "customer_segment": customer["segment"],
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "category": product["category"],
                    "region": region,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "discount": discount,
                    "total_amount": total,
                })
    return rows


def retail_csv_bytes(seed: int = SEED) -> bytes:
    rows = generate_retail_rows(seed=seed)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def retail_customers_csv_bytes(seed: int = SEED) -> bytes:
    """Secondary dimension table shipped for reference (single-file analytics MVP)."""
    rng = random.Random(seed + 7)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["customer_id", "segment", "region", "lifetime_value"])
    for i in range(1, 401):
        writer.writerow([
            f"C-{i:05d}",
            rng.choice(CUSTOMER_SEGMENTS),
            rng.choice(REGIONS),
            round(rng.uniform(120, 9800), 2),
        ])
    return buffer.getvalue().encode("utf-8")


DATASET_CONTRACT = {
    "name": "Retail Sales (synthetic)",
    "synthetic": True,
    "grain": "one row per sales order line",
    "definitions": {
        "total_amount": "quantity * unit_price * (1 - discount); net of discount, excludes tax and refunds",
        "order": "distinct order_id; one order may contain multiple product lines",
        "aov": "SUM(total_amount) / COUNT(DISTINCT order_id)",
    },
}
