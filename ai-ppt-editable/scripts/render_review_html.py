#!/usr/bin/env python3
"""Render a project-level HTML review page from ``pipeline-result.json``."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_text


def _escape(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _relative_link(value: Any, *, base: Path, output: Path) -> str | None:
    if isinstance(value, Path):
        candidate = value
    elif isinstance(value, str) and value.strip():
        candidate = Path(value)
    else:
        return None
    if not candidate.is_absolute():
        candidate = (base / candidate).resolve()
    if not candidate.exists():
        return None
    try:
        return candidate.relative_to(output.parent.resolve()).as_posix()
    except ValueError:
        return None


def _badge(label: str, value: str, css: str) -> str:
    return f'<div class="status-card {css}"><span>{_escape(label)}</span><strong>{_escape(value)}</strong></div>'


def build_html(result: dict[str, Any], output: Path) -> str:
    output = output.resolve()
    run_dir = Path(str(result.get("run_dir") or output.parent)).resolve()
    technical_valid = result.get("technical_valid") is True
    release_eligible = result.get("release_eligible") is True
    human_required = result.get("human_visual_review_required") is True or result.get("human_signoff_required") is True
    human_status = str(result.get("human_review_status") or "pending")
    human_complete = human_status.lower() in {"approved", "passed", "complete", "completed", "signed-off", "signed_off"}
    technical_label = "技术通过" if technical_valid else "技术阻断"
    human_label = "人工已复核" if human_complete else "人工待审" if human_required else "无需人工复核"
    release_label = "可交付" if release_eligible else "未放行"
    technical_css = "pass" if technical_valid else "fail"
    human_css = "pass" if human_complete or not human_required else "pending"
    release_css = "pass" if release_eligible else "pending"

    deck_link = _relative_link(result.get("deck"), base=run_dir, output=output)
    pipeline_link = "pipeline-result.json" if (run_dir / "pipeline-result.json").parent == output.parent.resolve() else _relative_link(run_dir / "pipeline-result.json", base=run_dir, output=output)
    steps = result.get("steps") if isinstance(result.get("steps"), list) else []
    evidence = result.get("quality_evidence") if isinstance(result.get("quality_evidence"), dict) else {}
    rendered = sorted((run_dir / "rendered").glob("slide-*.png"), key=lambda path: int(path.stem.split("-")[-1])) if (run_dir / "rendered").is_dir() else []
    affected_pages = result.get("execution", {}).get("affected_pages", "all") if isinstance(result.get("execution"), dict) else "all"
    affected_regions = result.get("execution", {}).get("affected_regions", []) if isinstance(result.get("execution"), dict) else []

    step_rows = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        ok = step.get("ok") is True
        status = "通过" if ok else "阻断"
        if step.get("failure") == "dependency_failed":
            status = "依赖阻断"
        stdout_link = _relative_link(step.get("stdout"), base=run_dir, output=output)
        stderr_link = _relative_link(step.get("stderr"), base=run_dir, output=output)
        links = " ".join(
            f'<a href="{_escape(link)}">{label}</a>'
            for link, label in ((stdout_link, "stdout"), (stderr_link, "stderr"))
            if link
        )
        step_rows.append(
            "<tr>"
            f"<td><code>{_escape(step.get('name'))}</code></td>"
            f"<td class=\"{'ok' if ok else 'bad'}\">{status}</td>"
            f"<td>{_escape(step.get('duration_ms', 0))} ms</td>"
            f"<td>{'命中' if step.get('cache_hit') else '执行'}</td>"
            f"<td>{_escape(', '.join(step.get('deps', [])) if isinstance(step.get('deps'), list) else '')}</td>"
            f"<td>{links}</td>"
            "</tr>"
        )

    evidence_rows = []
    for name, item in sorted(evidence.items()):
        if not isinstance(item, dict):
            continue
        valid = item.get("valid") is True
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        source_path = source.get("path")
        source_hash = str(source.get("sha256") or "")
        source_link = _relative_link(source_path, base=run_dir, output=output)
        source_label = f'<a href="{_escape(source_link)}">{_escape(Path(str(source_path)).name)}</a>' if source_link else _escape(source_path or "")
        if source_hash:
            source_label += f' <code title="{_escape(source_hash)}">{_escape(source_hash[:16])}…</code>'
        evidence_rows.append(
            "<tr>"
            f"<td><code>{_escape(name)}</code></td>"
            f"<td class=\"{'ok' if valid else 'bad'}\">{'通过' if valid else '失败/待审'}</td>"
            f"<td>{_escape(item.get('status'))}</td>"
            f"<td>{'是' if item.get('human_review_required') or item.get('human_visual_review_required') else '否'}</td>"
            f"<td>{source_label}</td>"
            "</tr>"
        )

    image_cards = []
    for page in rendered:
        link = _relative_link(page, base=run_dir, output=output)
        if link:
            image_cards.append(f'<figure><img src="{_escape(link)}" loading="lazy" alt="{_escape(page.name)}"><figcaption>{_escape(page.name)}</figcaption></figure>')

    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI PPT Plus 项目审阅页 - {_escape(result.get('project'))}</title>
<style>
:root {{ color-scheme: light; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; color: #1f2937; background: #f4f6f8; }}
body {{ max-width: 1240px; margin: 0 auto; padding: 28px; }}
h1, h2 {{ color: #111827; }} h1 {{ margin-bottom: 4px; }}
.muted {{ color: #6b7280; }}
.status-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 22px 0; }}
.status-card {{ background: white; border-left: 6px solid #9ca3af; border-radius: 8px; padding: 14px 16px; box-shadow: 0 1px 4px #0001; }}
.status-card span {{ display: block; color: #6b7280; font-size: 13px; }} .status-card strong {{ font-size: 21px; }}
.status-card.pass {{ border-color: #16a34a; }} .status-card.fail {{ border-color: #dc2626; }} .status-card.pending {{ border-color: #d97706; }}
.facts, .table-wrap, .gallery {{ background: white; border-radius: 8px; padding: 16px; margin: 16px 0; box-shadow: 0 1px 4px #0001; }}
.facts {{ display: grid; grid-template-columns: max-content 1fr; gap: 7px 18px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }} th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }} th {{ color: #6b7280; font-weight: 600; }}
.ok {{ color: #15803d; }} .bad {{ color: #b91c1c; }} code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
.gallery-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }} figure {{ margin: 0; }} figure img {{ width: 100%; border: 1px solid #d1d5db; border-radius: 5px; }} figcaption {{ font-size: 13px; color: #6b7280; margin-top: 4px; }}
a {{ color: #2563eb; }} @media (max-width: 720px) {{ body {{ padding: 14px; }} .status-grid {{ grid-template-columns: 1fr; }} .facts {{ grid-template-columns: 1fr; gap: 2px; }} table {{ display: block; overflow-x: auto; white-space: nowrap; }} }}
</style>
</head>
<body>
<h1>AI PPT Plus 项目审阅页</h1>
<p class="muted">项目：{_escape(result.get('project'))}　运行：<code>{_escape(result.get('run_id'))}</code></p>
<div class="status-grid">
{_badge('技术状态', technical_label, technical_css)}
{_badge('人工状态', human_label, human_css)}
{_badge('交付状态', release_label, release_css)}
</div>
<section class="facts">
<strong>执行模式</strong><span>{_escape(result.get('execution', {}).get('mode') if isinstance(result.get('execution'), dict) else None)}</span>
<strong>技术判定</strong><span>{_escape(result.get('technical_status'))}</span>
<strong>人工判定</strong><span>{_escape(human_status)}</span>
<strong>交付判定</strong><span>{_escape(result.get('release_status'))}</span>
<strong>验证范围</strong><span>{_escape('增量页级' if result.get('validation_scope') == 'incremental' else '全量')}</span>
<strong>受影响页面</strong><span>{_escape(affected_pages)}</span>
<strong>受影响区域</strong><span>{_escape(', '.join(affected_regions) if isinstance(affected_regions, list) else affected_regions)}</span>
<strong>失败步骤</strong><span>{_escape(', '.join(result.get('failed_steps', []))) or '无'}</span>
<strong>文件</strong><span>{f'<a href="{_escape(deck_link)}">PPTX</a>' if deck_link else '不可用'}　{f'<a href="{_escape(pipeline_link)}">pipeline-result.json</a>' if pipeline_link else ''}</span>
</section>
<section class="table-wrap"><h2>检查步骤</h2>
<table><thead><tr><th>步骤</th><th>状态</th><th>耗时</th><th>缓存</th><th>依赖</th><th>日志</th></tr></thead><tbody>{''.join(step_rows) or '<tr><td colspan="6">无步骤</td></tr>'}</tbody></table>
</section>
<section class="table-wrap"><h2>质量证据</h2>
<table><thead><tr><th>报告</th><th>统一判定</th><th>原生状态</th><th>人工复核</th><th>来源</th></tr></thead><tbody>{''.join(evidence_rows) or '<tr><td colspan="5">无质量证据</td></tr>'}</tbody></table>
</section>
<section class="gallery"><h2>渲染预览</h2><div class="gallery-grid">{''.join(image_cards) or '<p class="muted">没有可展示的渲染页。</p>'}</div></section>
<p class="muted">技术通过不等同于人工审阅完成；人工签核完成且所有发布门禁满足后，才可标记为可交付。</p>
</body></html>
"""
    return html_doc


def write_review(result: dict[str, Any], output: Path) -> Path:
    output = Path(output).resolve()
    atomic_write_text(output, build_html(result, output))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pipeline_result")
    parser.add_argument("--output")
    args = parser.parse_args()
    source = Path(args.pipeline_result).resolve()
    try:
        result = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "code": "pipeline_result_invalid", "message": str(exc)}, ensure_ascii=False))
        return 2
    if not isinstance(result, dict):
        print(json.dumps({"valid": False, "code": "pipeline_result_not_object"}, ensure_ascii=False))
        return 2
    output = Path(args.output).resolve() if args.output else source.parent / "review.html"
    write_review(result, output)
    print(json.dumps({"schema": "ai-ppt-plus/review-html/v1", "valid": True, "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
