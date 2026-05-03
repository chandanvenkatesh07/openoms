"""Hearthline synthetic dataset generator.

Hearthline is a fictional home-improvement retailer used as the reference
domain for OpenOMS. The dataset is deterministic (seeded RNG) and realistic
in shape: long-tail SKU availability, regional inventory variation, and a mix
of DC and store nodes that forces interesting multi-node sourcing decisions.

v0.1 scale
----------
- 50 Distribution Centers  (major US logistics hubs)
- 150 Stores               (5 per metro across 30 cities)
- 500 SKUs                 (9 product categories)
- ~30,000 inventory records
"""

from __future__ import annotations

import random

from openoms.models.domain import InventoryRecord, Node, NodeType
from openoms.store.memory import MemoryStore

# ---------------------------------------------------------------------------
# 50 DC locations — real US logistics hub cities
# ---------------------------------------------------------------------------
_DCS: list[tuple[str, str, float, float]] = [
    # (node_id,   zip,     lat,      lon)
    ("dc-mem",  "38105",  35.1495, -90.0490),   # Memphis TN
    ("dc-col",  "43215",  39.9612, -82.9988),   # Columbus OH
    ("dc-lou",  "40202",  38.2527, -85.7585),   # Louisville KY
    ("dc-ind",  "46202",  39.7684, -86.1581),   # Indianapolis IN
    ("dc-cin",  "45202",  39.1031, -84.5120),   # Cincinnati OH
    ("dc-chi",  "60616",  41.8500, -87.6300),   # Chicago IL
    ("dc-kci",  "64106",  39.0997, -94.5786),   # Kansas City MO
    ("dc-dal",  "75207",  32.8000, -96.8100),   # Dallas TX
    ("dc-hou",  "77002",  29.7604, -95.3698),   # Houston TX
    ("dc-atl",  "30354",  33.6490, -84.4430),   # Atlanta GA
    ("dc-nas",  "37203",  36.1520, -86.7830),   # Nashville TN
    ("dc-clt",  "28206",  35.2100, -80.8100),   # Charlotte NC
    ("dc-rdu",  "27601",  35.7800, -78.6400),   # Raleigh NC
    ("dc-ric",  "23219",  37.5400, -77.4300),   # Richmond VA
    ("dc-bwi",  "21202",  39.2900, -76.6100),   # Baltimore MD
    ("dc-phi",  "19104",  39.9500, -75.1600),   # Philadelphia PA
    ("dc-ewr",  "07102",  40.7400, -74.1700),   # Newark NJ
    ("dc-jfk",  "11430",  40.6413, -73.7781),   # New York DC
    ("dc-bos",  "02118",  42.3400, -71.0700),   # Boston MA
    ("dc-pit",  "15222",  40.4400, -79.9900),   # Pittsburgh PA
    ("dc-cle",  "44114",  41.5000, -81.6900),   # Cleveland OH
    ("dc-det",  "48209",  42.3100, -83.1000),   # Detroit MI
    ("dc-grr",  "49503",  42.9600, -85.6700),   # Grand Rapids MI
    ("dc-mke",  "53202",  43.0400, -87.9100),   # Milwaukee WI
    ("dc-msp",  "55401",  44.9800, -93.2700),   # Minneapolis MN
    ("dc-stl",  "63101",  38.6312, -90.1922),   # St. Louis MO
    ("dc-oma",  "68102",  41.2600, -95.9400),   # Omaha NE
    ("dc-dsm",  "50309",  41.5900, -93.6200),   # Des Moines IA
    ("dc-den",  "80202",  39.7528, -104.9992),  # Denver CO
    ("dc-slc",  "84101",  40.7600, -111.8900),  # Salt Lake City UT
    ("dc-phx",  "85003",  33.4500, -112.0700),  # Phoenix AZ
    ("dc-tus",  "85701",  32.2200, -110.9700),  # Tucson AZ
    ("dc-abq",  "87102",  35.0800, -106.6500),  # Albuquerque NM
    ("dc-las",  "89101",  36.1700, -115.1400),  # Las Vegas NV
    ("dc-lax",  "90011",  34.0100, -118.2600),  # Los Angeles CA
    ("dc-riv",  "92501",  33.9800, -117.3700),  # Riverside CA
    ("dc-san",  "92101",  32.7200, -117.1600),  # San Diego CA
    ("dc-fre",  "93706",  36.7400, -119.7900),  # Fresno CA
    ("dc-sac",  "95814",  38.5800, -121.4900),  # Sacramento CA
    ("dc-sjc",  "95110",  37.3300, -121.8900),  # San Jose CA
    ("dc-oak",  "94607",  37.8000, -122.2700),  # Oakland CA
    ("dc-pdx",  "97217",  45.5900, -122.6800),  # Portland OR
    ("dc-sea",  "98108",  47.5500, -122.3000),  # Seattle WA
    ("dc-geg",  "99201",  47.6600, -117.4300),  # Spokane WA
    ("dc-boi",  "83702",  43.6100, -116.2100),  # Boise ID
    ("dc-jax",  "32206",  30.3500, -81.6500),   # Jacksonville FL
    ("dc-mia",  "33142",  25.8100, -80.2200),   # Miami FL
    ("dc-tpa",  "33602",  27.9500, -82.4600),   # Tampa FL
    ("dc-msy",  "70112",  29.9500, -90.0700),   # New Orleans LA
    ("dc-okc",  "73102",  35.4700, -97.5200),   # Oklahoma City OK
]

# ---------------------------------------------------------------------------
# 30 metro centers — 5 stores each = 150 stores
# ---------------------------------------------------------------------------
_METROS: list[tuple[str, float, float]] = [
    # (metro_code, center_lat, center_lon)
    ("NYC",  40.7128, -74.0060),
    ("LAX",  34.0522, -118.2437),
    ("CHI",  41.8781, -87.6298),
    ("HOU",  29.7604, -95.3698),
    ("PHX",  33.4484, -112.0740),
    ("PHL",  39.9526, -75.1652),
    ("SAT",  29.4241, -98.4936),
    ("DAL",  32.7767, -96.7970),
    ("SJC",  37.3382, -121.8863),
    ("AUS",  30.2672, -97.7431),
    ("JAX",  30.3322, -81.6557),
    ("CLT",  35.2271, -80.8431),
    ("DEN",  39.7392, -104.9903),
    ("LAS",  36.1699, -115.1398),
    ("SEA",  47.6062, -122.3321),
    ("DCA",  38.9072, -77.0369),
    ("BNA",  36.1627, -86.7816),
    ("OKC",  35.4676, -97.5164),
    ("PDX",  45.5051, -122.6750),
    ("RDU",  35.7796, -78.6382),
    ("SFO",  37.7749, -122.4194),
    ("BOS",  42.3601, -71.0589),
    ("MSP",  44.9778, -93.2650),
    ("SDF",  38.2527, -85.7585),
    ("IND",  39.7684, -86.1581),
    ("TPA",  27.9506, -82.4572),
    ("MIA",  25.7617, -80.1918),
    ("ATL",  33.7490, -84.3880),
    ("CMH",  39.9612, -82.9988),
    ("MSY",  29.9500, -90.0700),
]

# ---------------------------------------------------------------------------
# 500 SKUs across 9 home-improvement categories
# ---------------------------------------------------------------------------
_CATEGORIES: list[tuple[str, int]] = [
    ("LUMBER",   55),
    ("HARDWARE", 75),
    ("PAINT",    55),
    ("PLUMBING", 55),
    ("ELECTR",   55),
    ("TOOLS",    75),
    ("GARDEN",   55),
    ("APPL",     40),
    ("DECOR",    35),
]  # 55+75+55+55+55+75+55+40+35 = 500


def _build_skus() -> list[str]:
    skus: list[str] = []
    for cat, count in _CATEGORIES:
        for i in range(1, count + 1):
            skus.append(f"{cat}-{i:04d}")
    return skus


def build_hearthline_store(seed: int = 42) -> MemoryStore:
    """Build the full Hearthline inventory store deterministically."""
    rng = random.Random(seed)
    skus = _build_skus()
    popular = set(skus[:100])  # top 100 SKUs are high-velocity, widely stocked

    nodes: list[Node] = []

    # ── DCs ──────────────────────────────────────────────────────────────────
    for node_id, zip_code, lat, lon in _DCS:
        nodes.append(Node(
            node_id=node_id,
            node_type=NodeType.DC,
            zip_code=zip_code,
            lat=lat, lon=lon,
            capacity_units_per_day=rng.randint(800, 1500),
            cost_to_ship_factor=round(rng.uniform(0.9, 1.3), 2),
        ))

    # ── Stores (5 per metro, scattered within ~35 miles) ─────────────────────
    store_idx = 1
    for _metro, m_lat, m_lon in _METROS:
        for _ in range(5):
            lat = m_lat + rng.uniform(-0.45, 0.45)
            lon = m_lon + rng.uniform(-0.45, 0.45)
            nodes.append(Node(
                node_id=f"store-{store_idx:04d}",
                node_type=NodeType.STORE,
                zip_code=f"HL{store_idx:05d}",   # synthetic ZIP; distance uses lat/lon
                lat=lat, lon=lon,
                capacity_units_per_day=rng.randint(80, 300),
                cost_to_ship_factor=round(rng.uniform(0.7, 1.1), 2),
            ))
            store_idx += 1

    # ── Inventory ─────────────────────────────────────────────────────────────
    # DCs: broad deep stock; stores: narrow shallow stock.
    # ~30% of popular SKUs are intentionally absent from nearby stores,
    # forcing split-shipment decisions on multi-line orders.
    inventory: list[InventoryRecord] = []
    for node in nodes:
        if node.node_type == NodeType.DC:
            for sku in skus:
                hit_rate = 0.92 if sku in popular else 0.72
                if rng.random() < hit_rate:
                    on_hand = rng.randint(50, 500) if sku in popular else rng.randint(5, 80)
                    inventory.append(InventoryRecord(sku=sku, node_id=node.node_id, on_hand=on_hand))
        else:
            for sku in skus:
                hit_rate = 0.45 if sku in popular else 0.08
                if rng.random() < hit_rate:
                    on_hand = rng.randint(2, 25) if sku in popular else rng.randint(1, 8)
                    inventory.append(InventoryRecord(sku=sku, node_id=node.node_id, on_hand=on_hand))

    store = MemoryStore()
    store.seed(nodes=nodes, inventory=inventory)
    return store
