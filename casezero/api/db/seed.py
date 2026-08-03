"""Seed the mock bank.

Run:  .venv/bin/python -m api.db.seed

Everything here is fabricated. MYBank Berhad does not exist, and no row derives
from a real person or account (T&C originality clause).

The data is shaped for three demo beats rather than being random filler:

* **Ahmad bin Ismail** holds the RM2,450.00 TECHWORLD KL debit at 03:02 that drives
  the 90-Second Challenge, surrounded by ordinary spending so the verifier has to
  find the right row.
* **Seven further customers** each carry a TECHWORLD KL debit on the same device
  fingerprint. Nobody notices this by reading cases one at a time — which is
  exactly the point of Fraud-Ring Radar.
* **Siti binti Rahman** is flagged vulnerable, so her RM90 dispute outranks a
  RM4,000 one. Priority by need, not by amount.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from api.db.client import service_client
from api.kernel.sla import MYT
from api.security.crypto import encrypt, last4

RULE_PACKS_DIR = Path(__file__).resolve().parent.parent.parent / "rule_packs"

GREEN, DIM, OFF, YELLOW = "\033[32m", "\033[2m", "\033[0m", "\033[33m"

FRAUD_MERCHANT = "TECHWORLD KL"
FRAUD_DEVICE = "dev_a91f77c204"

# (name, nric, email, phone, segment, risk_flags, account_no, product, balance)
CUSTOMERS: list[tuple[str, str, str, str, str, list[str], str, str, float]] = [
    ("Ahmad bin Ismail", "880412-14-5521", "ahmad.ismail@example.my",
     "+60123445566", "retail", [], "7142556890", "savings", 8_420.15),
    ("Siti binti Rahman", "540308-08-2210", "siti.rahman@example.my",
     "+60127788990", "vulnerable", ["senior_citizen", "assisted_banking"],
     "7142001233", "savings", 1_240.00),
    ("Lim Wei Jian", "920716-10-3345", "lim.weijian@example.my",
     "+60165554433", "retail", [], "7142778812", "credit_card", -2_310.55),
    ("Nur Aisyah binti Kamal", "990101-14-7788", "nur.aisyah@example.my",
     "+60193332211", "retail", [], "7142334455", "savings", 15_680.90),
    ("Rajesh Kumar", "861122-06-1199", "rajesh.kumar@example.my",
     "+60174445566", "retail", [], "7142889900", "current", 33_120.40),
    ("Tan Mei Ling", "950530-07-4412", "tan.meiling@example.my",
     "+60182223344", "retail", [], "7142667788", "savings", 4_905.25),
    ("Mohd Faizal bin Yusof", "910208-05-6677", "faizal.yusof@example.my",
     "+60136667788", "retail", [], "7142445566", "savings", 2_150.75),
    ("Chong Ka Wai", "870914-12-2233", "chong.kawai@example.my",
     "+60111234567", "sme", [], "7142112233", "current", 78_400.00),
]

# Ordinary spending for Ahmad, mirroring the generated statement PDF exactly so
# that OCR output and core-banking records agree.
AHMAD_TXNS: list[tuple[int, str, float, str, str]] = [
    (3, "DUITNOW TRF - TNB BILL PAYMENT", 187.40, "duitnow", "dev_ahmad_phone"),
    (9, "POS - LOTUS'S KOTA DAMANSARA", 243.85, "pos", "dev_ahmad_phone"),
    (12, "FPX - SHOPEE MALAYSIA", 89.90, "online", "dev_ahmad_phone"),
    (15, "ATM WDL - CIMB SS2 PJ", 500.00, "atm", "atm_cimb_ss2"),
    (19, "POS - 99 SPEEDMART TTDI", 62.30, "pos", "dev_ahmad_phone"),
    (24, "DUITNOW TRF - MAYBANK CARD PMT", 1_100.00, "duitnow", "dev_ahmad_phone"),
    (28, "POS - SHELL SEKSYEN 14", 120.00, "pos", "dev_ahmad_phone"),
]

# The ring. Same merchant, same device, small hours, spread across seven accounts
# so no single case looks like a pattern.
RING_VICTIMS: list[tuple[str, float, int, int]] = [
    ("7142001233", 890.00, 16, 2),
    ("7142778812", 3_180.00, 17, 3),
    ("7142334455", 1_450.00, 18, 2),
    ("7142889900", 2_990.00, 19, 4),
    ("7142667788", 760.00, 20, 3),
    ("7142445566", 1_875.00, 21, 2),
    ("7142112233", 4_620.00, 22, 3),
]


def july(day: int, hour: int = 12, minute: int = 0) -> str:
    return datetime(2026, 7, day, hour, minute, tzinfo=MYT).astimezone(timezone.utc).isoformat()


def seed_customers(sb) -> dict[str, str]:
    """Insert customers and accounts. Returns account_no -> customer_id."""
    print(f"\n{DIM}customers + accounts{OFF}")
    mapping: dict[str, str] = {}

    for (name, nric, email, phone, segment, flags,
         account_no, product, balance) in CUSTOMERS:
        existing = sb.table("customers").select("id").eq("email", email).limit(1).execute().data
        if existing:
            customer_id = existing[0]["id"]
        else:
            customer_id = (
                sb.table("customers")
                .insert(
                    {
                        # The NRIC is stored only as ciphertext. A database dump
                        # yields nothing without FERNET_KEY.
                        "name": name,
                        "nric_enc": encrypt(nric),
                        "nric_last4": last4(nric),
                        "email": email,
                        "phone": phone,
                        "segment": segment,
                        "risk_flags": flags,
                    }
                )
                .execute()
                .data[0]["id"]
            )

        sb.table("accounts").upsert(
            {
                "account_no": account_no,
                "customer_id": customer_id,
                "product_type": product,
                "balance_rm": balance,
                "status": "ACTIVE",
            },
            on_conflict="account_no",
        ).execute()

        mapping[account_no] = customer_id
        tag = f"  {YELLOW}[vulnerable]{OFF}" if segment == "vulnerable" else ""
        print(f"  {name:<26} {account_no}  RM {balance:>10,.2f}{tag}")

    return mapping


def seed_transactions(sb) -> None:
    print(f"\n{DIM}transactions{OFF}")
    rows: list[dict] = []

    # Ahmad's salary credit.
    rows.append(
        {
            "txn_ref": "TXN20260705AHMAD01",
            "account_no": "7142556890",
            "merchant": "SIME DARBY BHD",
            "amount_rm": 6_200.00,
            "direction": "CREDIT",
            "channel": "duitnow",
            "device_id": None,
            "posted_at": july(5, 9, 15),
        }
    )

    for day, description, amount, channel, device in AHMAD_TXNS:
        rows.append(
            {
                "txn_ref": f"TXN202607{day:02d}AHMAD",
                "account_no": "7142556890",
                "merchant": description,
                "amount_rm": amount,
                "direction": "DEBIT",
                "channel": channel,
                "device_id": device,
                "posted_at": july(day, 14, 30),
            }
        )

    # The disputed transaction. This exact reference is quoted on stage.
    rows.append(
        {
            "txn_ref": "TXN20260718TECHWORLD",
            "account_no": "7142556890",
            "merchant": FRAUD_MERCHANT,
            "amount_rm": 2_450.00,
            "direction": "DEBIT",
            "channel": "pos",
            "country": "MY",
            "device_id": FRAUD_DEVICE,
            "posted_at": july(18, 3, 2),
        }
    )

    # The ring.
    for account_no, amount, day, hour in RING_VICTIMS:
        rows.append(
            {
                "txn_ref": f"TXN202607{day:02d}TW{account_no[-4:]}",
                "account_no": account_no,
                "merchant": FRAUD_MERCHANT,
                "amount_rm": amount,
                "direction": "DEBIT",
                "channel": "pos",
                "country": "MY",
                "device_id": FRAUD_DEVICE,
                "posted_at": july(day, hour, 14),
            }
        )

    # Background noise, so the ring is not the only thing in the table.
    noise = [
        ("7142001233", "POS - PHARMACY GUARDIAN SS15", 48.60, 11, "pos"),
        ("7142334455", "FPX - GRAB MALAYSIA", 32.00, 13, "online"),
        ("7142889900", "POS - AEON BIG WANGSA MAJU", 310.75, 14, "pos"),
        ("7142667788", "ATM WDL - MAYBANK KLCC", 200.00, 15, "atm"),
        ("7142112233", "DUITNOW TRF - SUPPLIER PAYMENT", 12_400.00, 16, "duitnow"),
        ("7142445566", "POS - MCDONALDS DAMANSARA", 27.90, 17, "pos"),
        ("7142778812", "FPX - LAZADA MALAYSIA", 156.40, 18, "online"),
    ]
    for account_no, merchant, amount, day, channel in noise:
        rows.append(
            {
                "txn_ref": f"TXN202607{day:02d}N{account_no[-4:]}",
                "account_no": account_no,
                "merchant": merchant,
                "amount_rm": amount,
                "direction": "DEBIT",
                "channel": channel,
                "device_id": f"dev_{account_no[-4:]}",
                "posted_at": july(day, 16, 45),
            }
        )

    sb.table("transactions").upsert(rows, on_conflict="txn_ref").execute()

    ring_count = 1 + len(RING_VICTIMS)
    print(f"  {len(rows)} transactions")
    print(f"  {YELLOW}{ring_count}{OFF} share merchant {FRAUD_MERCHANT!r} on device "
          f"{FRAUD_DEVICE!r}  {DIM}<- Fraud-Ring Radar finds this{OFF}")
    print(f"  disputed row: TXN20260718TECHWORLD  RM 2,450.00  03:02")


def seed_rule_packs(sb) -> None:
    print(f"\n{DIM}rule packs{OFF}")
    files = sorted(RULE_PACKS_DIR.glob("*.yaml"))
    if not files:
        print(f"  {YELLOW}none found in {RULE_PACKS_DIR}{OFF}")
        return

    for path in files:
        text = path.read_text()
        parsed = yaml.safe_load(text)
        category, version = parsed["category"], int(parsed["version"])

        sb.table("rule_packs").upsert(
            {
                "category": category,
                "version": version,
                "yaml": text,
                "is_active": False,
                "change_summary": "Initial pack, seeded from disk.",
                "created_by": "system",
            },
            on_conflict="category,version",
        ).execute()

        # Deactivate before activating: the database permits only one active pack
        # per category, so the other order is rejected.
        sb.table("rule_packs").update({"is_active": False}).eq("category", category).eq(
            "is_active", True
        ).execute()
        sb.table("rule_packs").update({"is_active": True}).eq("category", category).eq(
            "version", version
        ).execute()

        share = parsed.get("volume_share")
        share_label = f"{share:.0%} of volume" if share else ""
        print(f"  {category:<26} v{version}  active  {DIM}{share_label}{OFF}")


def seed_proactive_alert(sb) -> None:
    """Stable synthetic token for the presenter-mode closer."""
    print(f"\n{DIM}proactive dispute{OFF}")
    token = "demo-proactive-techworld-2026"
    sb.table("proactive_alerts").upsert(
        {
            "token": token,
            "account_no": "7142001233",
            "txn_ref": "TXN20260718TECHWORLD",
            "amount_rm": 2450.00,
            "merchant": "TECHWORLD KL",
            "occurred_at": "2026-07-18T03:02:00+08:00",
            "status": "PENDING",
            "expires_at": "2026-12-31T23:59:59+08:00",
        },
        on_conflict="token",
    ).execute()
    print(f"  /proactive/{token}  {DIM}<- presenter-mode magic link{OFF}")


def main() -> int:
    sb = service_client()
    print("=" * 68)
    print("  CaseZero - seeding MYBank Berhad (100% synthetic)")
    print("=" * 68)

    account_map = seed_customers(sb)
    seed_transactions(sb)
    seed_rule_packs(sb)
    seed_proactive_alert(sb)

    print("\n" + "=" * 68)
    print(f"  {GREEN}seeded{OFF}  {len(account_map)} accounts")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
