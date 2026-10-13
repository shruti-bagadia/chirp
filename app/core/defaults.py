"""Default dashboard settings, seeded into the settings table on first run."""

DEFAULT_SETTINGS: dict = {
    "fit_threshold": 70,
    "max_jobs_per_run": 30,
    "daily_apply_cap": 8,
    "ctc_tiers": {
        "premium": {"min": 18, "max": 22, "single": 20, "floor": 16},
        "standard": {"min": 16, "max": 17, "single": 16, "floor": 16},
        "services": {"min": 16, "max": 18, "single": 17, "floor": 16},
    },
    "match_thresholds": {"strong": 0.85, "possible": 0.70},
    "dormant_after_days": 60,
    "schedule": {
        "paused": False,
        "find": {"times": ["08:30", "13:00"], "days": ["mon", "tue", "wed", "thu", "fri"]},
        "apply": {"times": ["10:30", "15:30"], "days": ["mon", "tue", "wed", "thu", "fri"]},
        "nightly": {
            "times": ["02:00"],
            "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        },
    },
}
