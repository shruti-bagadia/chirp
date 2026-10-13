"""One-off: raise the CTC floor to 16 LPA for every tier in the live `settings` row.

The settings row is seeded once from `app/core/defaults.py` on first boot — changing
that file doesn't touch a row that already exists. Run this once against whichever
database DATABASE_URL points at (dry run by default; pass --apply to actually write).

    python scripts/update_ctc_floor.py            # preview only
    python scripts/update_ctc_floor.py --apply     # write the change
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy.orm import Session

from app.core.defaults import DEFAULT_SETTINGS
from app.db.models import AppSettings
from app.db.session import get_engine


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write the change (default: preview)")
    args = ap.parse_args()

    engine = get_engine()
    with Session(engine) as db:
        row = db.get(AppSettings, 1)
        if row is None:
            print("No settings row yet — nothing to patch; next boot will seed the new floor.")
            return

        before = row.data.get("ctc_tiers", {})
        after = {**row.data, "ctc_tiers": DEFAULT_SETTINGS["ctc_tiers"]}

        print("Current ctc_tiers:")
        print(json.dumps(before, indent=2))
        print("\nNew ctc_tiers:")
        print(json.dumps(after["ctc_tiers"], indent=2))

        if not args.apply:
            print("\nDry run only — rerun with --apply to write this.")
            return

        row.data = after  # reassign, not mutate, so SQLAlchemy sees the JSONB change
        db.add(row)
        db.commit()
        print("\nUpdated.")


if __name__ == "__main__":
    main()
