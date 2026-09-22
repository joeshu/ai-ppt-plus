from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_finalization_preflight.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("finalization_preflight", SCRIPT)
preflight = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(preflight)


def _fixture(tmp_path: Path):
    workspace = tmp_path / "run"
    final_dir = workspace / "final"
    receipt_dir = workspace / ".finalizer"
    modules = workspace / "node_modules"
    fonts = workspace / "fonts"
    final_dir.mkdir(parents=True)
    receipt_dir.mkdir()
    (modules / "@oai" / "artifact-tool").mkdir(parents=True)
    fonts.mkdir()
    candidate = workspace / "candidate.pptx"
    node = workspace / "node"
    candidate.write_bytes(b"pptx")
    node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    node.chmod(0o755)
    (modules / "@oai" / "artifact-tool" / "package.json").write_text("{}\n", encoding="utf-8")
    (fonts / "font.ttf").write_bytes(b"font")
    return {
        "workspace": workspace,
        "candidate": candidate,
        "final": final_dir / "final.pptx",
        "receipt": receipt_dir / "receipt.json",
        "node": node,
        "node_modules": modules,
        "font_dir": fonts,
    }


def _validate(values):
    with mock.patch.object(preflight.shutil, "which", return_value="/usr/bin/tool"):
        return preflight.validate(**values)


def test_preflight_binds_runtime_and_paths(tmp_path):
    values = _fixture(tmp_path)
    result = _validate(values)
    assert result["valid"] is True
    assert result["runtime_env"]["RUNTIME_NODE"] == str(values["node"])
    assert result["visual_renderer"] == "libreoffice+poppler"


def test_missing_receipt_parent_fails_before_finalizer(tmp_path):
    values = _fixture(tmp_path)
    values["receipt"] = values["workspace"] / "missing" / "receipt.json"
    result = _validate(values)
    assert result["valid"] is False
    assert any(issue["code"] == "receipt_parent_missing" for issue in result["issues"])


def test_artifact_preview_is_not_visual_authority(tmp_path):
    values = _fixture(tmp_path)
    result = _validate(values)
    assert result["artifact_tool_preview_policy"] == "structural_diagnostic_only"


def test_libreoffice_render_binds_task_local_fonts(tmp_path):
    values = _fixture(tmp_path)
    result = _validate(values)
    binding = result["renderer_font_binding"]
    assert binding["required"] is True
    assert binding["mode"] == "task-local-fontconfig"
    assert binding["font_dir"] == str(values["font_dir"])
    assert binding["font_file_count"] == 1
    assert binding["render_command_requirement"] == "render_pptx.py --font-dir"


def test_prebuild_allows_reserved_candidate_path(tmp_path):
    values = _fixture(tmp_path)
    values["candidate"].unlink()
    values["stage"] = "prebuild"
    result = _validate(values)
    assert result["valid"] is True
    assert result["stage"] == "prebuild"


if __name__ == "__main__":
    tests = (
        test_preflight_binds_runtime_and_paths,
        test_missing_receipt_parent_fails_before_finalizer,
        test_artifact_preview_is_not_visual_authority,
        test_libreoffice_render_binds_task_local_fonts,
        test_prebuild_allows_reserved_candidate_path,
    )
    for index, test in enumerate(tests):
        with tempfile.TemporaryDirectory(prefix=f"finalization-preflight-{index}-") as folder:
            test(Path(folder))
    print("finalization preflight tests: ok")
