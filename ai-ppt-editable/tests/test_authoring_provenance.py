#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_authoring_provenance import validate


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="authoring-provenance-") as temp:
        root = Path(temp)
        source = root / "source.png"
        layout = root / "layout.json"
        graph = root / "page-graph.json"
        objects = root / "slide-object-manifest.json"
        imagegen = root / "imagegen-assets-manifest.json"
        deck = root / "deck.pptx"
        for path, payload in [
            (source, b"source"), (layout, b"layout"), (graph, b"graph"),
            (objects, b"objects"), (imagegen, b"imagegen"), (deck, b"deck-v1"),
        ]:
            path.write_bytes(payload)
        inputs = {
            "source": {"path": str(source), "sha256": sha(source)},
            "layout": {"path": str(layout), "sha256": sha(layout)},
            "page_graph": {"path": str(graph), "sha256": sha(graph)},
            "object_manifest": {"path": str(objects), "sha256": sha(objects)},
            "imagegen_manifest": {"path": str(imagegen), "sha256": sha(imagegen)},
        }
        request = root / "run-request.json"
        provenance = root / "authoring-provenance.json"
        write_json(request, {"request_id": "run-new", "inputs": inputs})
        write_json(provenance, {
            "request_id": "run-new",
            "entrypoint": "strict_reference_rerun.py",
            "inputs": inputs,
            "deck_sha256": sha(deck),
        })
        good = validate(request, provenance, deck)
        assert good["valid"], good

        # Copying an old provenance/deck into a newly-requested rerun must fail.
        write_json(request, {"request_id": "run-newer", "inputs": inputs})
        stale = validate(request, provenance, deck)
        codes = {item["code"] for item in stale["issues"]}
        assert "rerun_request_id_mismatch" in codes, stale

        # Modifying/replacing the deck after authoring must also fail.
        write_json(request, {"request_id": "run-new", "inputs": inputs})
        deck.write_bytes(b"copied-old-deck")
        stale_deck = validate(request, provenance, deck)
        codes = {item["code"] for item in stale_deck["issues"]}
        assert "stale_authoring_deck" in codes, stale_deck

        # Changing the source underneath a run invalidates the claimed rerun.
        deck.write_bytes(b"deck-v1")
        source.write_bytes(b"source-changed")
        stale_source = validate(request, provenance, deck)
        codes = {item["code"] for item in stale_source["issues"]}
        assert "source_hash_mismatch" in codes, stale_source

    print("authoring provenance rerun gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
