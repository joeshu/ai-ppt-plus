#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "ai-ppt-editable" / "scripts"
CASE_ROOT = ROOT / "evals" / "text-fit-batch5" / "work" / "china-unicom-downgrade-control"
PARTS = ROOT / "evals" / "text-fit-batch5" / "sources" / "china-unicom-downgrade-control.b64.parts"
SOURCE_SHA = "036a0c6877bd9fd25541fcb38313a67d2bfef14c911f673f0e5c1a8d9be8ec99"


def run(*parts: str) -> None:
    print("+", " ".join(parts), flush=True)
    completed = subprocess.run(parts, cwd=ROOT, text=True, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rebuild_source() -> Path:
    files = sorted(PARTS.glob("part-*.b64"))
    if not files:
        raise SystemExit(f"source parts missing: {PARTS}")
    payload = "".join(path.read_text(encoding="ascii").strip() for path in files)
    source = CASE_ROOT / "source.jpeg"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(base64.b64decode(payload, validate=True))
    digest = sha256(source)
    if digest != SOURCE_SHA:
        raise SystemExit(f"source sha mismatch: {digest}")
    with Image.open(source) as image:
        if image.size != (1536, 864):
            raise SystemExit(f"source dimensions mismatch: {image.size}")
    return source


def add_text(items: list[dict], object_id: str, text: str, bbox: list[float], size: float,
             *, color: str = "#222222", bold: bool = False, align: str = "left",
             target_lines: int = 1, max_lines: int | None = None) -> None:
    spec = {
        "object_id": object_id,
        "text": text,
        "bbox": bbox,
        "font": "Noto Sans CJK SC",
        "font_size_pt": size,
        "color": color,
        "bold": bold,
        "align": align,
        "valign": "middle",
        "margin_left": 0.02,
        "margin_right": 0.02,
        "margin_top": 0.0,
        "margin_bottom": 0.0,
        "target_lines": target_lines,
        "max_lines": max_lines or target_lines,
        "measurement_scope": {"kind": "whole_phrase", "scope_id": object_id},
    }
    items.append(spec)


def build_layout() -> tuple[dict, dict, dict]:
    red = "#D71920"
    blue = "#0B67B5"
    orange = "#F05A28"
    pale_red = "#FDE9EA"
    pale_blue = "#E8F4FB"
    pale_orange = "#FFF0DC"
    dark = "#202020"
    shapes: list[dict] = [
        {"object_id": "bg", "type": "rect", "bbox": [0, 0, 1, 1], "fill": "#FFFFFF", "line": "#FFFFFF"},
        {"object_id": "thought-frame", "type": "rounded_rect", "bbox": [0.022, 0.142, 0.956, 0.062], "fill": "#FFFFFF", "line": red, "line_width": 0.8},
        {"object_id": "thought-label", "type": "rect", "bbox": [0.022, 0.142, 0.125, 0.062], "fill": red, "line": red},
        {"object_id": "left-body", "type": "rounded_rect", "bbox": [0.018, 0.221, 0.323, 0.684], "fill": "#FFFFFF", "line": "#F2C9CD", "line_width": 0.8},
        {"object_id": "left-head", "type": "rounded_rect", "bbox": [0.018, 0.221, 0.323, 0.063], "fill": red, "line": red},
        {"object_id": "center-body", "type": "rounded_rect", "bbox": [0.348, 0.221, 0.320, 0.684], "fill": "#FFFFFF", "line": "#D1E5F4", "line_width": 0.8},
        {"object_id": "center-head", "type": "rounded_rect", "bbox": [0.348, 0.221, 0.320, 0.063], "fill": blue, "line": blue},
        {"object_id": "right-body", "type": "rounded_rect", "bbox": [0.674, 0.221, 0.312, 0.684], "fill": "#FFFFFF", "line": "#F6D6C5", "line_width": 0.8},
        {"object_id": "right-head", "type": "rounded_rect", "bbox": [0.674, 0.221, 0.312, 0.063], "fill": orange, "line": orange},
        {"object_id": "left-strip-1", "type": "rounded_rect", "bbox": [0.097, 0.419, 0.232, 0.035], "fill": pale_red, "line": pale_red},
        {"object_id": "left-strip-2", "type": "rounded_rect", "bbox": [0.097, 0.642, 0.232, 0.035], "fill": pale_red, "line": pale_red},
        {"object_id": "left-strip-3", "type": "rounded_rect", "bbox": [0.097, 0.862, 0.232, 0.035], "fill": pale_red, "line": pale_red},
        {"object_id": "center-strip-1", "type": "rounded_rect", "bbox": [0.426, 0.446, 0.226, 0.036], "fill": pale_blue, "line": pale_blue},
        {"object_id": "center-strip-2", "type": "rounded_rect", "bbox": [0.426, 0.659, 0.226, 0.036], "fill": pale_blue, "line": pale_blue},
        {"object_id": "center-strip-3", "type": "rounded_rect", "bbox": [0.426, 0.859, 0.226, 0.036], "fill": pale_blue, "line": pale_blue},
        {"object_id": "right-transition", "type": "rounded_rect", "bbox": [0.688, 0.544, 0.278, 0.050], "fill": pale_orange, "line": "#F4C79D", "line_width": 0.5},
        {"object_id": "footer-red", "type": "rect", "bbox": [0, 0.925, 1, 0.075], "fill": "#D71920", "line": "#D71920"},
    ]
    texts: list[dict] = []
    add_text(texts, "title-main", "降套管控", [0.377, 0.004, 0.248, 0.086], 48, color=red, bold=True, align="center")
    add_text(texts, "subtitle", "——  多维发力   标本兼治   推动降套治理落地见效  ——", [0.235, 0.091, 0.530, 0.043], 17.5, color=red, bold=True, align="center")
    add_text(texts, "thought-label-text", "整体思路", [0.032, 0.151, 0.102, 0.040], 18, color="#FFFFFF", bold=True, align="center")
    add_text(texts, "thought-body", "从量化目标、压实责任、规则宣贯、激励约束、线上线下同管控、风险前置干预、流程优化多维度全方位推进降套治理工作落地见效。", [0.151, 0.149, 0.805, 0.045], 14, color=dark, target_lines=1)
    add_text(texts, "left-header", "分级分类管控    定目标·强管控·压责任", [0.057, 0.229, 0.268, 0.039], 17.5, color="#FFFFFF", bold=True)
    add_text(texts, "left-h1", "目标可量化，责任必到人", [0.067, 0.296, 0.245, 0.037], 16.5, color=red, bold=True)
    add_text(texts, "left-b1", "▪ 制定单位、网格月管控目标，按天监控进度。\n▪ 实施异常调度，压实各级责任。", [0.095, 0.345, 0.232, 0.070], 12.2, color=dark, target_lines=2)
    add_text(texts, "left-s1", "目标清晰 · 过程可控 · 责任到人", [0.108, 0.421, 0.206, 0.029], 11.7, color=red, bold=True, align="center")
    add_text(texts, "left-h2", "分类授权，依策办理", [0.067, 0.483, 0.245, 0.036], 16.5, color=red, bold=True)
    add_text(texts, "left-b2", "▪ 强化线上线下降套策略查询使用，按推荐逐级降档。\n▪ 线下依策受理不扣减积分。\n▪ 线上降套差异化管理，维挽成功分档给予激励，\n   拉大激励差距。", [0.095, 0.526, 0.235, 0.111], 11.6, color=dark, target_lines=4)
    add_text(texts, "left-s2", "线上线下有策可依 · 激励到位 · 能降必挽", [0.102, 0.644, 0.220, 0.028], 11.1, color=red, bold=True, align="center")
    add_text(texts, "left-h3", "严控触点，闭环管控", [0.067, 0.703, 0.245, 0.036], 16.5, color=red, bold=True)
    add_text(texts, "left-b3", "▪ 线下非自有厅及指定人员不允许受理。\n▪ 每例降套均执行主管副总审批制度。\n▪ 严控区县投诉节点管控。\n▪ 集约中台设定压降目标，结果纳入月度降套KPI管控。", [0.095, 0.747, 0.236, 0.109], 11.5, color=dark, target_lines=4)
    add_text(texts, "left-s3", "触点可控 · 审批闭环 · 考核落地", [0.105, 0.864, 0.214, 0.028], 11.4, color=red, bold=True, align="center")
    add_text(texts, "center-header", "强化穿透，前置维系    早识别·早干预·早维系", [0.397, 0.229, 0.255, 0.039], 17.0, color="#FFFFFF", bold=True)
    add_text(texts, "center-h1", "规则明晰，全员知晓", [0.398, 0.296, 0.230, 0.037], 16.5, color=blue, bold=True)
    add_text(texts, "center-b1", "▪ 制作降套明白卡，明确各类场景及扣罚规则。\n▪ 全渠道签字确认回收存档。\n▪ 规范后续处罚时以“不知晓规则”为由推诿。", [0.433, 0.344, 0.220, 0.094], 11.6, color=dark, target_lines=3)
    add_text(texts, "center-s1", "规则上墙 · 全员覆盖 · 有据可依", [0.438, 0.448, 0.202, 0.028], 11.4, color=blue, bold=True, align="center")
    add_text(texts, "center-h2", "识别在前，干预在先", [0.398, 0.513, 0.230, 0.037], 16.5, color=blue, bold=True)
    add_text(texts, "center-b2", "▪ 针对合约、优惠到期等风险客群，提前开展续约维系，\n   减少被动降套。\n▪ 规范营销用语，避免升档不成变降套。", [0.433, 0.557, 0.220, 0.094], 11.6, color=dark, target_lines=3)
    add_text(texts, "center-s2", "提前识别 · 主动维系 · 防患于未然", [0.438, 0.661, 0.202, 0.028], 11.2, color=blue, bold=True, align="center")
    add_text(texts, "center-h3", "简化流程，便捷办理", [0.398, 0.727, 0.230, 0.037], 16.5, color=blue, bold=True)
    add_text(texts, "center-b3", "▪ 新入网申请8元套餐便捷支撑。\n▪ 减少新入网降套。", [0.433, 0.774, 0.220, 0.067], 11.8, color=dark, target_lines=2)
    add_text(texts, "center-s3", "流程更简 · 办理更快 · 客户更满意", [0.438, 0.861, 0.202, 0.028], 11.2, color=blue, bold=True, align="center")
    add_text(texts, "right-header", "创新管理，防患未然    常宣贯·常提醒·防未然", [0.720, 0.229, 0.250, 0.039], 16.8, color="#FFFFFF", bold=True)
    add_text(texts, "right-title", "推行降套管控每日一讲群推送机制", [0.688, 0.304, 0.278, 0.044], 15.5, color=red, bold=True, align="center")
    add_text(texts, "right-bullets", "☑ 每日轮换宣讲业务规则。\n☑ 每日解读考核标准。\n☑ 每日分享标杆案例。\n☑ 每日通报典型警示。", [0.786, 0.357, 0.182, 0.151], 12.2, color=dark, target_lines=4)
    add_text(texts, "right-transition-text", "推动降套由事后考核向事前预防转变。", [0.703, 0.551, 0.250, 0.035], 13.8, color="#7D2A18", bold=True, align="center")
    add_text(texts, "right-card-1", "业务规则\n天天讲", [0.693, 0.668, 0.062, 0.078], 10.8, color=dark, bold=True, align="center", target_lines=2)
    add_text(texts, "right-card-2", "考核标准\n天天学", [0.772, 0.668, 0.062, 0.078], 10.8, color=dark, bold=True, align="center", target_lines=2)
    add_text(texts, "right-card-3", "标杆案例\n天天看", [0.851, 0.668, 0.062, 0.078], 10.8, color=dark, bold=True, align="center", target_lines=2)
    add_text(texts, "right-card-4", "典型警示\n天天醒", [0.930, 0.668, 0.052, 0.078], 10.5, color=dark, bold=True, align="center", target_lines=2)

    layout = {
        "project_id": "textfit-b5-unicom-fresh-replay",
        "replay_scope": "text-fit-only-current-main",
        "slide_width_in": 13.333,
        "slide_height_in": 7.5,
        "ref_width": 1536,
        "ref_height": 864,
        "units": "fraction",
        "font_family": "Noto Sans CJK SC",
        "editable_object_policy": "native-semantic-objects",
        "theme": {"font": "Noto Sans CJK SC", "text_color": dark, "size": 12},
        "slides": [{"layout_name": "Blank", "shapes": shapes, "texts": texts}],
    }
    plan = {
        "schema": "ai-ppt-plus/authoring-plan/v1",
        "replay_scope": "text-fit-only-current-main",
        "objects": [
            {
                "object_id": item["object_id"], "page": 1, "semantic_role": "formal-text",
                "implementation_type": "native_text", "bbox": item["bbox"],
                "text_spec": {"content": item["text"], "font_family": item["font"], "font_size_pt": item["font_size_pt"]},
            }
            for item in texts
        ],
    }
    manifest = {
        "schema": "ai-ppt-plus/slide-object-manifest/v1",
        "replay_scope": "text-fit-only-current-main",
        "slides": [{
            "slide_no": 1,
            "objects": [
                {
                    "object_id": item["object_id"], "object_type": "editable_text", "role": "formal-text",
                    "text_spec": {"content": item["text"]},
                }
                for item in texts
            ],
        }],
    }
    return layout, plan, manifest


def main() -> int:
    if CASE_ROOT.exists():
        shutil.rmtree(CASE_ROOT)
    CASE_ROOT.mkdir(parents=True)
    source = rebuild_source()
    layout, plan, manifest = build_layout()
    layout_path = CASE_ROOT / "layout.json"
    plan_path = CASE_ROOT / "authoring-plan.json"
    manifest_path = CASE_ROOT / "slide-object-manifest.json"
    write_json(layout_path, layout)
    write_json(plan_path, plan)
    write_json(manifest_path, manifest)

    font_candidates = sorted((ROOT / "ai-ppt-editable" / "assets" / "fonts").glob("NotoSansSC-Regular.ttf"))
    if not font_candidates:
        raise SystemExit("NotoSansSC-Regular.ttf missing; run runtime font materialization first")
    font = font_candidates[0]

    fit = CASE_ROOT / "text-fit-report.json"
    run(sys.executable, str(SCRIPTS / "text_fit_deck.py"), str(layout_path), "--font-file", str(font), "--report", str(fit), "--fail-on-target-not-fit", "--require-kind", "text")

    deck = CASE_ROOT / "candidate-current-main.pptx"
    run(sys.executable, str(SCRIPTS / "compose_pptx.py"), str(layout_path), str(deck), "--strict-input", "--authoring-backend", "python-pptx", "--embed-fonts", "--font-dir", str(font.parent))

    render_dir = CASE_ROOT / "fresh-render"
    render_report = CASE_ROOT / "render-report.json"
    run(sys.executable, str(SCRIPTS / "render_pptx.py"), str(deck), "--output-dir", str(render_dir), "--dpi", "144", "--font-dir", str(font.parent), "--report", str(render_report))
    candidate_render = render_dir / "slide-1.png"
    if not candidate_render.is_file():
        raise SystemExit("fresh candidate render missing")

    reference_dir = CASE_ROOT / "reference-render"
    reference_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(candidate_render) as candidate_image, Image.open(source) as source_image:
        reference = source_image.convert("RGB").resize(candidate_image.size, Image.Resampling.LANCZOS)
        reference.save(reference_dir / "slide-1.png")

    feedback = CASE_ROOT / "text-render-feedback.json"
    run(sys.executable, str(SCRIPTS / "text_render_feedback.py"), "--text-fit-report", str(fit), "--authoring-plan", str(plan_path), "--reference-render-dir", str(reference_dir), "--candidate-render-dir", str(render_dir), "--crop-dir", str(CASE_ROOT / "text-crops"), "--report", str(feedback))

    coverage = CASE_ROOT / "text-coverage.json"
    coverage_audit = CASE_ROOT / "text-coverage-audit.json"
    run(sys.executable, str(SCRIPTS / "build_text_coverage.py"), str(plan_path), str(fit), "--output", str(coverage))
    run(sys.executable, str(SCRIPTS / "audit_text_coverage.py"), str(plan_path), str(coverage), "--text-fit-report", str(fit), "--report", str(coverage_audit))

    native_raw = CASE_ROOT / "native-editability-raw.json"
    run(sys.executable, str(SCRIPTS / "validate_native_editability.py"), str(deck), "--forbid-whole-slide-pictures", "--report", str(native_raw))
    native = json.loads(native_raw.read_text(encoding="utf-8"))
    native_text_count = sum(
        1 for slide in native.get("slides", []) for item in slide.get("objects", [])
        if item.get("kind") == "editable_text"
    )
    editability = {
        "schema": "ai-ppt-plus/text-fit-case-editability/v1",
        "valid": native.get("valid") is True,
        "status": native.get("status"),
        "summary": {
            "whole_slide_raster_count": len(native.get("whole_slide_pictures", [])),
            "native_text_count": native_text_count,
        },
        "source_report": str(native_raw),
        "source_errors": native.get("errors", []),
    }
    write_json(CASE_ROOT / "editability-audit.json", editability)

    candidate_sha = sha256(deck)
    render_provenance = {
        "schema": "ai-ppt-plus/text-fit-render-provenance/v1",
        "valid": True,
        "fresh_candidate_render": True,
        "candidate_artifact": str(deck),
        "candidate_artifact_sha256": candidate_sha,
        "rendered_from_candidate_sha256": candidate_sha,
        "candidate_render": str(candidate_render),
        "candidate_render_sha256": sha256(candidate_render),
        "source_reference": str(source),
        "source_reference_sha256": sha256(source),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authoring_backend": "python-pptx-current-main-text-replay",
        "scope": "text-fit-regression-only-not-production-reconstruction",
    }
    write_json(CASE_ROOT / "render-provenance.json", render_provenance)

    replay = CASE_ROOT / "batch5-replay-report.json"
    run(sys.executable, str(SCRIPTS / "text_fit_case_replay.py"), "--manifest", str(ROOT / "evals" / "text-fit-batch5" / "cases.json"), "--root", str(ROOT / "evals" / "text-fit-batch5"), "--report", str(replay))
    replay_data = json.loads(replay.read_text(encoding="utf-8"))
    unicom = next(row for row in replay_data["cases"] if row["id"] == "china-unicom-downgrade-control")
    summary = {
        "schema": "ai-ppt-plus/unicom-textfit-fresh-replay/v1",
        "status": unicom["status"],
        "source_sha256": sha256(source),
        "candidate_sha256": candidate_sha,
        "native_text_count": native_text_count,
        "text_fit": json.loads(fit.read_text(encoding="utf-8")),
        "text_render_feedback_summary": json.loads(feedback.read_text(encoding="utf-8")).get("summary"),
        "checks": unicom["checks"],
        "note": "TextFit-only regression candidate. Historical v14 PPTX is not used. Brand/icon ImageGen fidelity is outside this Batch 5 text replay and is not claimed as production visual reconstruction.",
    }
    write_json(CASE_ROOT / "fresh-replay-summary.json", summary)
    print(json.dumps({"status": unicom["status"], "candidate": str(deck), "summary": str(CASE_ROOT / "fresh-replay-summary.json")}, ensure_ascii=False))
    return 0 if unicom["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
