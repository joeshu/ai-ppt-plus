#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    delivery = (ROOT / "scripts" / "delivery_check.py").read_text(encoding="utf-8")
    rerun = (ROOT / "scripts" / "strict_reference_rerun.py").read_text(encoding="utf-8")
    assert 'route_report.get("route") == "reference-reconstruction"' in delivery
    assert 'current-rerun.json' in delivery
    assert 'authoring_provenance_failed' in delivery
    assert 'validate_authoring_provenance' in delivery
    assert 'current_rerun_path.unlink()' in rerun
    assert '"status": "authored"' in rerun
    print("delivery authoring provenance contract: ok")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
