"""Canonical production execution profiles for editable reconstruction."""

PROFILES = {
    "fast": {
        "delivery_allowed": True,
        "candidate_limit": 2,
        "repair_round_limit": 1,
        "full_render_limit": 2,
        "imagegen_retry_limit_per_asset": 1,
        "local_crop_min": 3,
        "local_crop_max": 5,
        "text_fit_scope": "high_risk",
        "full_regression": False,
    },
    "strict": {
        "delivery_allowed": True,
        "candidate_limit": 3,
        "repair_round_limit": 2,
        "full_render_limit": 4,
        "imagegen_retry_limit_per_asset": 2,
        "local_crop_min": 5,
        "local_crop_max": 10,
        "text_fit_scope": "all_formal",
        "full_regression": False,
    },
    "ci": {
        "delivery_allowed": False,
        "candidate_limit": 0,
        "repair_round_limit": 0,
        "full_render_limit": 0,
        "imagegen_retry_limit_per_asset": 0,
        "local_crop_min": 0,
        "local_crop_max": 0,
        "text_fit_scope": "regression",
        "full_regression": True,
    },
}

