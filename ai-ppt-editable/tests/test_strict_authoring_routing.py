import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_validator(template: dict) -> tuple[int, dict]:
    path = ROOT / ".tmp-strict-routing-test.json"
    path.write_text(json.dumps(template, ensure_ascii=False), encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts/validate_routing_contract.py"), str(path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        return proc.returncode, json.loads(proc.stdout)
    finally:
        path.unlink(missing_ok=True)


def test_strict_authoring_route_is_valid():
    template = json.loads((ROOT / "assets/skill-routing.template.json").read_text(encoding="utf-8"))
    code, report = run_validator(template)
    assert code == 0, report
    assert report["valid"] is True


def test_commonjs_cannot_satisfy_strict_authoring_route():
    template = json.loads((ROOT / "assets/skill-routing.template.json").read_text(encoding="utf-8"))
    template["bindings"]["strict_authoring"]["module_format"] = "CommonJS"
    code, report = run_validator(template)
    assert code != 0
    assert any(item["code"] == "strict_authoring_binding_mismatch" for item in report["issues"])
