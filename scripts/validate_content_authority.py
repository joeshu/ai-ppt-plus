#!/usr/bin/env python3
"""Validate formal-copy provenance from source through outline to rendered PPTX."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from atomic_output import atomic_write_json
from validate_outline import read_rows

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve(base: Path, raw: str) -> Path:
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def object_ids(value, found=None):
    found = found if found is not None else {}
    if isinstance(value, dict):
        object_id = value.get("object_id") or value.get("text_id") or value.get("id")
        if isinstance(object_id, str) and object_id:
            found[object_id] = value
        for child in value.values(): object_ids(child, found)
    elif isinstance(value, list):
        for child in value: object_ids(child, found)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("authority")
    parser.add_argument("--report")
    parser.add_argument("--require-pptx-refs", action="store_true")
    parser.add_argument("--require-render-refs", action="store_true")
    args = parser.parse_args()
    path = Path(args.authority).resolve()
    issues = []
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result={"schema":"ai-ppt-plus/content-authority-validation/v1","valid":False,"issues":[{"severity":"blocker","code":"authority_unreadable","message":f"{type(exc).__name__}: {exc}"}]}
        if args.report: atomic_write_json(Path(args.report).resolve(), result)
        print(json.dumps(result,ensure_ascii=False)); return 3
    if not isinstance(data, dict) or data.get("schema") != "ai-ppt-plus/content-authority/v1":
        issues.append({"severity":"blocker","code":"authority_schema_invalid"})
        data = data if isinstance(data, dict) else {}
    for field in ("project_id", "revision", "outline_contract", "entries"):
        if field not in data: issues.append({"severity":"blocker","code":"authority_field_missing","field":field})
    contract_ref = data.get("outline_contract") if isinstance(data.get("outline_contract"),dict) else {}
    contract_path = resolve(path.parent, str(contract_ref.get("path") or ""))
    contract = {}
    if not contract_path.is_file():
        issues.append({"severity":"blocker","code":"outline_contract_missing","path":str(contract_path)})
    else:
        observed=sha256(contract_path)
        if contract_ref.get("sha256") != observed: issues.append({"severity":"blocker","code":"outline_contract_hash_mismatch","expected":contract_ref.get("sha256"),"observed":observed})
        try: contract=json.loads(contract_path.read_text(encoding="utf-8"))
        except Exception as exc: issues.append({"severity":"blocker","code":"outline_contract_unreadable","message":str(exc)})
    outline_path = resolve(contract_path.parent, str(contract.get("outline_path") or "")) if contract else contract_path
    rows = []
    if outline_path.is_file():
        try: rows=read_rows(outline_path)
        except Exception as exc: issues.append({"severity":"blocker","code":"outline_unreadable","message":str(exc)})
    else: issues.append({"severity":"blocker","code":"outline_missing","path":str(outline_path)})
    row_map={int(row.get("slide_no")):row for row in rows if str(row.get("slide_no") or "").isdigit()}
    sources={ref.get("source_id"):ref for ref in data.get("sources",[]) if isinstance(ref,dict) and ref.get("source_id")}
    for source_id, source_ref in sources.items():
        source_path = resolve(path.parent, str(source_ref.get("path") or ""))
        if not source_path.is_file():
            issues.append({"severity":"blocker","code":"source_missing","source_id":source_id,"path":str(source_path)})
            continue
        declared_hash = source_ref.get("sha256")
        observed_hash = sha256(source_path)
        if not isinstance(declared_hash, str) or not SHA256_RE.fullmatch(declared_hash):
            issues.append({"severity":"blocker","code":"source_hash_missing","source_id":source_id})
        elif declared_hash.lower() != observed_hash.lower():
            issues.append({"severity":"blocker","code":"source_hash_mismatch","source_id":source_id,"expected":observed_hash,"observed":declared_hash})
    seen=set()
    for index, entry in enumerate(data.get("entries",[]) or []):
        if not isinstance(entry,dict): issues.append({"severity":"blocker","code":"entry_invalid","index":index}); continue
        aid=entry.get("authority_id")
        if not isinstance(aid,str) or not aid: issues.append({"severity":"blocker","code":"entry_id_missing","index":index})
        elif aid in seen: issues.append({"severity":"blocker","code":"duplicate_authority_id","authority_id":aid})
        seen.add(aid)
        slide_no=entry.get("slide_no"); ref=entry.get("outline_ref") if isinstance(entry.get("outline_ref"),dict) else {}
        ref_slide=ref.get("slide_no"); field=ref.get("field")
        if slide_no != ref_slide: issues.append({"severity":"blocker","code":"slide_reference_mismatch","authority_id":aid})
        row=row_map.get(ref_slide)
        if not row or field not in row: issues.append({"severity":"blocker","code":"outline_reference_missing","authority_id":aid,"slide_no":ref_slide,"field":field})
        else:
            expected=str(row.get(field) or "")
            if entry.get("content") != expected: issues.append({"severity":"blocker","code":"formal_content_mismatch","authority_id":aid,"expected":expected,"observed":entry.get("content")})
        for source_ref in entry.get("source_refs",[]) or []:
            if not isinstance(source_ref,dict) or source_ref.get("source_id") not in sources: issues.append({"severity":"blocker","code":"source_ref_unresolved","authority_id":aid})
        pptx_ref=entry.get("pptx_object_ref")
        if args.require_pptx_refs and not isinstance(pptx_ref,dict): issues.append({"severity":"blocker","code":"pptx_object_ref_missing","authority_id":aid})
        if isinstance(pptx_ref,dict):
            manifest_path=resolve(path.parent,str(pptx_ref.get("manifest_path") or ""))
            if not manifest_path.is_file(): issues.append({"severity":"blocker","code":"pptx_manifest_missing","authority_id":aid})
            else:
                try: manifest=json.loads(manifest_path.read_text(encoding="utf-8")); objects=object_ids(manifest)
                except Exception: objects={}
                object_id=pptx_ref.get("object_id") or entry.get("object_id")
                if object_id not in objects: issues.append({"severity":"blocker","code":"pptx_object_missing","authority_id":aid,"object_id":object_id})
                elif entry.get("content"):
                    observed_object = objects[object_id]
                    observed_values = [observed_object.get(key) for key in ("content", "text", "value", "title")]
                    if not any(value == entry.get("content") for value in observed_values):
                        issues.append({"severity":"blocker","code":"pptx_object_content_unverified","authority_id":aid,"object_id":object_id})
        render_ref=entry.get("render_ref")
        if args.require_render_refs and not isinstance(render_ref,dict): issues.append({"severity":"blocker","code":"render_ref_missing","authority_id":aid})
        if isinstance(render_ref,dict):
            render_path=resolve(path.parent,str(render_ref.get("path") or ""))
            if not render_path.is_file(): issues.append({"severity":"blocker","code":"render_missing","authority_id":aid})
            bbox=render_ref.get("bbox")
            if not isinstance(bbox,list) or len(bbox)!=4 or not all(isinstance(v,(int,float)) for v in bbox): issues.append({"severity":"blocker","code":"render_bbox_invalid","authority_id":aid})
    result={"schema":"ai-ppt-plus/content-authority-validation/v1","valid":not issues,"project_id":data.get("project_id"),"revision":data.get("revision"),"entry_count":len(data.get("entries",[]) or []),"issues":issues}
    if args.report: atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result,ensure_ascii=False)); return 0 if not issues else 2


if __name__ == "__main__": raise SystemExit(main())
