"""
Backfill sync data from raw stored JSONB columns.

Fixes two categories of historic records without re-fetching from Garmin:

1. GarminSleep — re-extracts durations from raw_sleep_data.dailySleepDTO
   (previously stored as 0 due to wrong top-level key lookup)

2. GarminActivity — re-extracts averageHR/maxHR/elevation/training effects
   from raw_activity_data
   (previously stored as 0 due to wrong field names)

Run once:
    ./.venv/bin/python scripts/backfill_sync_data.py
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv
load_dotenv()

from core.config import init_config
from core.database import init_database, GarminSleep, GarminActivity
from core.garmin_client import GarminClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def backfill_sleep(db) -> int:
    updated = 0
    with db.get_session() as session:
        rows = session.query(GarminSleep).filter(GarminSleep.total_sleep_minutes == 0).all()
        logger.info("Sleep rows with total_sleep_minutes=0: %d", len(rows))

        for row in rows:
            raw = row.raw_sleep_data
            if not raw or not isinstance(raw, dict):
                continue

            m = GarminClient._parse_sleep_dto(raw)
            if m["sleep_time_s"] == 0:
                continue

            row.total_sleep_minutes  = m["sleep_time_s"]  // 60
            row.deep_sleep_minutes   = m["deep_sleep_s"]  // 60
            row.light_sleep_minutes  = m["light_sleep_s"] // 60
            row.rem_sleep_minutes    = m["rem_sleep_s"]   // 60
            row.awake_minutes        = m["awake_s"]       // 60
            row.sleep_quality_score  = m["quality"]
            if m["start_dt"]:
                row.sleep_start_time = m["start_dt"]
            if m["end_dt"]:
                row.sleep_end_time   = m["end_dt"]

            updated += 1

        session.commit()
    return updated


def backfill_activities(db) -> int:
    updated = 0
    with db.get_session() as session:
        rows = session.query(GarminActivity).filter(
            (GarminActivity.avg_heart_rate == 0) | (GarminActivity.avg_heart_rate.is_(None))
        ).all()
        logger.info("Activity rows with avg_heart_rate=0/None: %d", len(rows))

        for row in rows:
            raw = row.raw_activity_data
            if not raw or not isinstance(raw, dict):
                continue

            avg_hr = raw.get("averageHR") or raw.get("averageHeartRate") or 0
            max_hr = raw.get("maxHR")     or raw.get("maxHeartRate")     or 0

            if avg_hr:
                row.avg_heart_rate = avg_hr
            if max_hr:
                row.max_heart_rate = max_hr

            if raw.get("elevationGain") is not None:
                row.elevation_gain_m = raw["elevationGain"]
            if raw.get("aerobicTrainingEffect") is not None:
                row.training_effect_aerobic = raw["aerobicTrainingEffect"]
            if raw.get("anaerobicTrainingEffect") is not None:
                row.training_effect_anaerobic = raw["anaerobicTrainingEffect"]

            hr_zones = {
                str(z): raw.get(f"hrTimeInZone_{z}")
                for z in range(1, 6)
                if raw.get(f"hrTimeInZone_{z}") is not None
            }
            if hr_zones:
                row.heart_rate_zones = hr_zones

            updated += 1

        session.commit()
    return updated


if __name__ == "__main__":
    config = init_config()
    db = init_database(config)

    sleep_fixed = backfill_sleep(db)
    logger.info("Sleep rows backfilled: %d", sleep_fixed)

    act_fixed = backfill_activities(db)
    logger.info("Activity rows backfilled: %d", act_fixed)

    logger.info("Backfill complete.")
