import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_execution_profile.py"
spec = importlib.util.spec_from_file_location("profile_gate", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)

def main():
    data = json.loads((ROOT / "assets" / "execution-profile.template.json").read_text(encoding="utf-8"))
    assert module.validate(data) == []
    data["budgets"]["full_render_limit"] = 99
    assert module.validate(data)
    print("execution profile contracts: ok")

if __name__ == "__main__": main()
