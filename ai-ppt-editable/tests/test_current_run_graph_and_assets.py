#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_current_run_imagegen import validate as validate_imagegen
from validate_embedded_imagegen_assets import validate as validate_embedded
from validate_page_graph_provenance import validate as validate_graph


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="current-run-provenance-") as temp:
        root = Path(temp)
        request_id = "run-20260905"
        source = root / "source.png"
        graph = root / "page-graph.json"
        asset = root / "icon.png"
        deck = root / "deck.pptx"
        source.write_bytes(b"source-v1")
        graph.write_bytes(b'{"nodes":[]}')
        asset.write_bytes(b"generated-icon-v1")

        graph_provenance = root / "page-graph-provenance.json"
        write_json(graph_provenance, {
            "schema": "ai-ppt-plus/page-graph-provenance/v1",
            "request_id": request_id,
            "producer": {"task": "visual-reconstruction", "provider": "test", "model": "test"},
            "source": {"path": str(source), "sha256": sha(source)},
            "page_graph": {"path": str(graph), "sha256": sha(graph)},
        })
        good_graph = validate_graph(graph_provenance, request_id, source, graph)
        assert good_graph["valid"], good_graph
        wrong_graph_run = validate_graph(graph_provenance, "other-run", source, graph)
        assert "page_graph_request_id_mismatch" in {i["code"] for i in wrong_graph_run["issues"]}

        manifest = root / "imagegen-assets-manifest.json"
        write_json(manifest, {
            "schema": "ai-ppt-plus/imagegen-assets/v2",
            "request_id": request_id,
            "assets": [{
                "id": "icon-1",
                "node_id": "icon-1",
                "request_id": request_id,
                "path": str(asset),
                "actual_sha256": sha(asset),
            }],
        })
        good_imagegen = validate_imagegen(manifest, request_id)
        assert good_imagegen["valid"], good_imagegen
        wrong_imagegen_run = validate_imagegen(manifest, "other-run")
        assert "manifest_request_id_mismatch" in {i["code"] for i in wrong_imagegen_run["issues"]}

        with zipfile.ZipFile(deck, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("ppt/media/image1.png", asset.read_bytes())
        embedded = validate_embedded(deck, manifest, request_id)
        assert embedded["valid"], embedded
        assert embedded["approved_assets"][0]["embedded_parts"] == ["ppt/media/image1.png"]

        # A transformed/replaced copy is not the approved final asset bytes.
        with zipfile.ZipFile(deck, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("ppt/media/image1.png", b"wrong-generated-icon")
        missing = validate_embedded(deck, manifest, request_id)
        assert "approved_asset_missing_from_pptx" in {i["code"] for i in missing["issues"]}, missing

    print("current-run PageGraph/ImageGen/embedded-media gates: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
