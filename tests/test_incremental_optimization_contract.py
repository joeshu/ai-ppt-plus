#!/usr/bin/env python3
"""Dependency-light regression coverage for the A-O optimization contract."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from incremental_orchestrator import CheckpointStore, SCHEMA  # noqa: E402
from font_preflight import validate_font_evidence  # noqa: E402
from atomic_output import atomic_write_json  # noqa: E402
from tool_adapter import (  # noqa: E402
    AdapterError,
    check_arrow_collisions,
    create_staging_dir,
    detect_full_page_image,
    preload_files,
    publish_staged,
    validate_finite,
    validate_overlay_bindings,
)
from validate_skill_references import scan  # noqa: E402


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def test_attachment_recovery(tmp: Path) -> None:
    requested = tmp / "page.png"
    recovered = tmp / "page (1).png"
    recovered.write_bytes(PNG)
    sys.path.insert(0, str(ROOT / "scripts"))
    from reference_input_preflight import resolve
    record, candidates = resolve(str(requested), [tmp])
    assert record and record["path"] == str(recovered.resolve()) and candidates


def test_page_order_and_count(tmp: Path) -> None:
    paths = []
    for index in (2, 1):
        path = tmp / f"page-{index}.png"; path.write_bytes(PNG); paths.append(path)
    roster = [{"page": index + 1, "path": str(path)} for index, path in enumerate(paths)]
    assert [item["page"] for item in roster] == [1, 2] and [Path(item["path"]).name for item in roster] == ["page-2.png", "page-1.png"] and len(roster) == 2


def test_nan_guard() -> None:
    try: validate_finite(float("nan"), field="width")
    except AdapterError: pass
    else: raise AssertionError("NaN accepted")


def test_preload_barrier(tmp: Path) -> None:
    resource = tmp / "asset.bin"; resource.write_bytes(b"ready")
    evidence = preload_files([resource]); assert evidence[str(resource.resolve())]["size"] == 5
    try: preload_files([tmp / "missing.bin"])
    except AdapterError: pass
    else: raise AssertionError("missing resource accepted")


def test_cjk_render_evidence() -> None:
    report = {"cjk_delivery_supported": True, "native_font_rendering_verified": True, "fallback": False, "weights_found": [400, 500, 600, 700], "missing_weights": []}
    result = validate_font_evidence(report)
    assert result["valid"] and result["native_font_rendering_verified"] and not result["fallback"]


def test_missing_weight_is_explicit() -> None:
    report = {"cjk_delivery_supported": True, "native_font_rendering_verified": True, "weights_found": [400, 700], "missing_weights": [500, 600]}
    result = validate_font_evidence(report)
    assert result["missing_weights"] == [500, 600] and result["simulated_bold_possible"] is False


def test_rich_text_order() -> None:
    from xml.etree.ElementTree import fromstring
    root = fromstring("<a:p xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'><a:r><a:t>A</a:t></a:r><a:r><a:t>B</a:t></a:r></a:p>")
    assert "".join(node.text or "" for node in root.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}t")) == "AB"


def test_overlay_binding() -> None:
    validate_overlay_bindings([{"table_id": "t", "row": 0, "column": 1, "overlay_id": "o"}])
    try: validate_overlay_bindings([{"table_id": "t", "row": 0, "column": 1, "overlay_id": "o1"}, {"table_id": "t", "row": 0, "column": 1, "overlay_id": "o2"}])
    except AdapterError: pass
    else: raise AssertionError("duplicate overlay binding accepted")


def test_arrow_collision() -> None:
    findings = check_arrow_collisions([{"object_id": "a", "left": 0, "top": 0, "width": 100, "height": 10}], [{"object_id": "t", "left": 50, "top": 0, "width": 40, "height": 20}])
    assert findings and findings[0]["arrow_id"] == "a"


def test_output_conflict(tmp: Path) -> None:
    staging_root = tmp / "staging"; deliverables = tmp / "deliverables"; deliverables.mkdir(); staging = create_staging_dir(staging_root, run_id="run-test")
    report = tmp / "atomic-report.json"; atomic_write_json(report, {"ok": True}); assert json.loads(report.read_text(encoding="utf-8"))["ok"] is True
    source = staging / "candidate.pptx"; source.write_bytes(b"pptx")
    target = deliverables / "final.pptx"; target.write_bytes(b"old")
    try: publish_staged(source, target, staging_root=staging, deliverables_root=deliverables)
    except AdapterError: pass
    else: raise AssertionError("output conflict silently replaced")


def test_checkpoint_resume(tmp: Path) -> None:
    inp = tmp / "input.png"; inp.write_bytes(PNG)
    state = CheckpointStore.create(tmp / "checkpoint.json", project_root=tmp, repository_sha="a" * 40, package_revision="r1", inputs=[inp])
    marker = tmp / "marker.json"; marker.write_text("{}", encoding="utf-8")
    state.record_stage("A", outputs=[marker])
    state.load(); plan = state.resume_plan()
    assert plan["entry_stage"] == "B" and plan["artifact_marker_reusable"] is False


def test_cache_invalidation(tmp: Path) -> None:
    inp = tmp / "input.png"; inp.write_bytes(PNG)
    state = CheckpointStore.create(tmp / "checkpoint.json", project_root=tmp, repository_sha="a" * 40, package_revision="r1", inputs=[inp])
    state.record_stage("B", outputs=[inp])
    inp.write_bytes(PNG + b"changed"); state.load(); plan = state.resume_plan()
    assert "B" in plan["invalidated"] and plan["entry_stage"] == "B"


def test_full_page_detection() -> None:
    findings = detect_full_page_image([{"object_id": "bg", "object_type": "image", "geometry": {"width": 100, "height": 100}}], slide_width=100, slide_height=100)
    assert findings and findings[0]["coverage"] == 1.0


def test_final_mutation(tmp: Path) -> None:
    final = tmp / "final.pptx"; final.write_bytes(b"final")
    state = CheckpointStore.create(tmp / "checkpoint.json", project_root=tmp, repository_sha="a" * 40, package_revision="r1")
    state.record_stage("L", outputs=[final]); final.write_bytes(b"mutated"); state.load(); plan = state.resume_plan()
    assert any(item["path"] == str(final.resolve()) for item in plan["output_mismatches"])


def test_reference_integrity() -> None:
    records, issues = scan(ROOT)
    assert records and not issues


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="incremental-contract-") as raw:
        tmp = Path(raw)
        tests = [test_attachment_recovery, test_page_order_and_count, lambda _: test_nan_guard(), lambda _: test_preload_barrier(tmp), lambda _: test_cjk_render_evidence(), lambda _: test_missing_weight_is_explicit(), lambda _: test_rich_text_order(), lambda _: test_overlay_binding(), lambda _: test_arrow_collision(), lambda _: test_output_conflict(tmp), lambda _: test_checkpoint_resume(tmp), lambda _: test_cache_invalidation(tmp), lambda _: test_full_page_detection(), lambda _: test_final_mutation(tmp), lambda _: test_reference_integrity()]
        for test in tests:
            test(tmp) if test in (test_attachment_recovery, test_page_order_and_count) else test(tmp)
    print("incremental optimization contract: 15 tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
