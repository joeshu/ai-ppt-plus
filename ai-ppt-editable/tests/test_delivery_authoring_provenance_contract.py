#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    delivery = (ROOT / "scripts" / "delivery_check.py").read_text(encoding="utf-8")
    rerun = (ROOT / "scripts" / "strict_reference_rerun.py").read_text(encoding="utf-8")
    authoring = (ROOT / "scripts" / "validate_authoring_provenance.py").read_text(encoding="utf-8")
    assert 'route_report.get("route") == "reference-reconstruction"' in delivery
    assert 'current-rerun.json' in delivery
    assert 'authoring_provenance_failed' in delivery
    assert 'validate_authoring_provenance' in delivery
    assert 'current_rerun_path.unlink()' in rerun
    assert 'page-graph-provenance.json' in rerun
    assert 'validate_page_graph_provenance.py' in rerun
    assert 'validate_current_run_imagegen.py' in rerun
    assert 'validate_embedded_imagegen_assets.py' in rerun
    assert 'request_id has already been used' in rerun
    assert 'validate_page_graph_provenance' in authoring
    assert 'validate_current_run_imagegen' in authoring
    assert 'validate_embedded_imagegen_assets' in authoring
    assert 'strict-rerun-request/v2' in authoring
    print("delivery authoring/PageGraph/ImageGen provenance contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
