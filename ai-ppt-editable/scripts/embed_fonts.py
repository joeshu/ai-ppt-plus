#!/usr/bin/env python3
"""Embed licensed TTF/OTF assets into an existing PPTX.

The deterministic composer uses ``python-pptx``, which can declare a font on
text runs but cannot create PresentationML font parts.  This post-processor
adds the complete OOXML font package: ``p:embeddedFontLst``, presentation font
relationships, the ``ppt/fonts/*.fntdata`` EOT parts, and the corresponding
content type.  It deliberately embeds the complete supplied font file rather
than subsetting it, so later text edits are less likely to lose glyphs.

Usage:
    python3 scripts/embed_fonts.py input.pptx output.pptx \
        --font-dir project-fonts --manifest project-fonts/font-manifest.json \
        --report font-embedding.json

``--font`` may be repeated as ``family=path`` for an explicit, manifest-free
operation.  The input is never modified.  The output is refused when it
already exists unless ``--force`` is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import struct
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from atomic_output import atomic_write_json


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
P = f"{{{P_NS}}}"
R_ID = f"{{{R_NS}}}id"

ET.register_namespace("a", A_NS)
ET.register_namespace("r", R_NS)
ET.register_namespace("p", P_NS)
ET.register_namespace("", CT_NS)

FONT_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
FONT_CONTENT_TYPE = "application/x-fontdata"
SUPPORTED_EOT_VERSIONS = {0x00010000, 0x00020001, 0x00020002}
STYLE_TAGS = {
    "regular": "regular",
    "normal": "regular",
    "bold": "bold",
    "italic": "italic",
    "bolditalic": "boldItalic",
    "bold_italic": "boldItalic",
    "bold-italic": "boldItalic",
}
FAMILY_STYLE_SUFFIXES = {
    "thin", "extralight", "extra light", "light", "regular", "medium",
    "semibold", "semi bold", "bold", "extrabold", "extra bold", "black",
}


class EmbeddingError(ValueError):
    """A font or PPTX package cannot be embedded safely."""


@dataclass
class FontSpec:
    family: str
    path: Path
    style: str = "regular"
    expected_sha256: str | None = None
    license_name: str | None = None
    license_url: str | None = None


@dataclass
class FontMeta:
    family: str
    style_name: str
    version_name: str
    full_name: str
    panose: bytes
    charset: int
    italic: int
    weight: int
    fs_type: int
    unicode_range: bytes
    code_page_range: bytes
    checksum_adjustment: int
    sfnt_format: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise EmbeddingError(f"font field exceeds file at offset {offset}")
    return struct.unpack_from(">H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise EmbeddingError(f"font field exceeds file at offset {offset}")
    return struct.unpack_from(">I", data, offset)[0]


def _sfnt_tables(data: bytes) -> dict[str, bytes]:
    if len(data) < 12:
        raise EmbeddingError("font is shorter than an SFNT header")
    if data[:4] == b"ttcf":
        raise EmbeddingError("TrueType Collection (.ttc) requires an explicit face split before embedding")
    try:
        data[:4].decode("ascii")
    except UnicodeDecodeError as exc:
        raise EmbeddingError("font does not have a recognized SFNT signature") from exc
    count = u16(data, 4)
    if not 1 <= count <= 4096:
        raise EmbeddingError(f"invalid SFNT table count: {count}")
    tables: dict[str, bytes] = {}
    for index in range(count):
        offset = 12 + index * 16
        if offset + 16 > len(data):
            raise EmbeddingError("SFNT table directory is truncated")
        tag_bytes = data[offset:offset + 4]
        try:
            tag = tag_bytes.decode("ascii")
        except UnicodeDecodeError as exc:
            raise EmbeddingError("SFNT table tag is not ASCII") from exc
        table_offset = u32(data, offset + 8)
        table_length = u32(data, offset + 12)
        if table_offset + table_length > len(data):
            raise EmbeddingError(f"SFNT table {tag!r} exceeds font file")
        tables[tag] = data[table_offset:table_offset + table_length]
    return tables


def _decode_name(platform: int, raw: bytes) -> str:
    if platform in {0, 3}:
        return raw.decode("utf-16-be", errors="replace").rstrip("\x00")
    if platform == 1:
        return raw.decode("mac_roman", errors="replace").rstrip("\x00")
    return raw.decode("latin-1", errors="replace").rstrip("\x00")


def _name_records(table: bytes) -> list[tuple[int, int, int, int, str]]:
    if len(table) < 6:
        return []
    count = u16(table, 2)
    storage_offset = u16(table, 4)
    records: list[tuple[int, int, int, int, str]] = []
    for index in range(count):
        offset = 6 + index * 12
        if offset + 12 > len(table):
            break
        platform = u16(table, offset)
        encoding = u16(table, offset + 2)
        language = u16(table, offset + 4)
        name_id = u16(table, offset + 6)
        length = u16(table, offset + 8)
        value_offset = u16(table, offset + 10)
        start = storage_offset + value_offset
        end = start + length
        if start > len(table) or end > len(table):
            continue
        value = _decode_name(platform, table[start:end]).strip()
        if value:
            records.append((name_id, platform, encoding, language, value))
    return records


def _preferred_name(records: list[tuple[int, int, int, int, str]], name_id: int, fallback: str) -> str:
    candidates = [record for record in records if record[0] == name_id]
    if not candidates:
        return fallback

    def score(record: tuple[int, int, int, int, str]) -> tuple[int, int, int]:
        _, platform, encoding, language, _ = record
        platform_score = {3: 40, 0: 30, 1: 10}.get(platform, 0)
        language_score = 10 if language in {0x0004, 0x0404, 0x0804, 0x1004} else 0
        encoding_score = 2 if encoding in {1, 10} else 0
        return platform_score + language_score + encoding_score, -len(record[4]), -record[1]

    return max(candidates, key=score)[4]


def _panose_bytes(value) -> bytes:
    if value is None:
        return b"\0" * 10
    fields = (
        "bFamilyType", "bSerifStyle", "bWeight", "bProportion", "bContrast",
        "bStrokeVariation", "bArmStyle", "bLetterform", "bMidline", "bXHeight",
    )
    try:
        return bytes(max(0, min(255, int(getattr(value, field)))) for field in fields)
    except Exception:
        return b"\0" * 10


def parse_font_meta(data: bytes) -> FontMeta:
    tables = _sfnt_tables(data)
    head = tables.get("head")
    if not head or len(head) < 46:
        raise EmbeddingError("font has no usable head table")
    os2 = tables.get("OS/2", b"")
    names = _name_records(tables.get("name", b""))
    family = _preferred_name(names, 1, "")
    style = _preferred_name(names, 2, "Regular")
    version = _preferred_name(names, 5, "")
    full_name = _preferred_name(names, 4, family or "Embedded Font")
    if not family:
        family = full_name
    panose = os2[32:42].ljust(10, b"\0") if len(os2) >= 42 else b"\0" * 10
    weight = u16(os2, 4) if len(os2) >= 6 else 400
    fs_type = u16(os2, 8) if len(os2) >= 10 else 0
    fs_selection = u16(os2, 62) if len(os2) >= 64 else 0
    mac_style = u16(head, 44) if len(head) >= 46 else 0
    unicode_range = os2[42:58].ljust(16, b"\0") if len(os2) >= 58 else b"\0" * 16
    code_page_range = os2[78:86].ljust(8, b"\0") if len(os2) >= 86 else b"\0" * 8
    return FontMeta(
        family=family,
        style_name=style,
        version_name=version,
        full_name=full_name,
        panose=panose[:10],
        charset=1,
        italic=1 if (fs_selection & 0x0001 or mac_style & 0x0002) else 0,
        weight=max(1, min(1000, weight or 400)),
        fs_type=fs_type,
        unicode_range=unicode_range[:16],
        code_page_range=code_page_range[:8],
        checksum_adjustment=u32(head, 8) if len(head) >= 12 else 0,
        sfnt_format=data[:4].decode("ascii", errors="replace"),
    )


def _utf16le_bytes(value: str) -> bytes:
    encoded = value.encode("utf-16le", errors="replace")
    encoded = encoded[:65534]
    return encoded[:len(encoded) - (len(encoded) % 2)]


def make_eot(data: bytes, meta: FontMeta) -> tuple[bytes, dict]:
    names = [_utf16le_bytes(meta.family), _utf16le_bytes(meta.style_name), _utf16le_bytes(meta.version_name), _utf16le_bytes(meta.full_name)]
    header_size = 82
    variable_size = sum(4 + len(item) for item in names) + 2
    eot_size = header_size + variable_size + len(data)
    if eot_size > 0xFFFFFFFF or len(data) > 0xFFFFFFFF:
        raise EmbeddingError("font is too large for the EOT 32-bit size fields")
    header = b"".join([
        struct.pack("<IIII", eot_size, len(data), 0x00020001, 0),
        meta.panose,
        struct.pack("<BBIHH", meta.charset, meta.italic, meta.weight, meta.fs_type, 0x504C),
        meta.unicode_range,
        meta.code_page_range,
        struct.pack("<I", meta.checksum_adjustment),
        b"\0" * 16,
        struct.pack("<H", 0),
    ])
    if len(header) != header_size:
        raise AssertionError(f"unexpected EOT header size: {len(header)}")
    body = bytearray(header)
    for item in names:
        body.extend(struct.pack("<H", len(item)))
        body.extend(item)
        body.extend(struct.pack("<H", 0))
    body.extend(struct.pack("<H", 0))  # root string
    body.extend(data)
    if len(body) != eot_size:
        raise AssertionError(f"unexpected EOT size: {len(body)} != {eot_size}")
    return bytes(body), {
        "format": "EOT v2.0001",
        "compression": "none",
        "sfnt_format": meta.sfnt_format,
        "eot_size": eot_size,
        "font_data_size": len(data),
        "font_data_offset": eot_size - len(data),
    }


def _normalize_style(value: str | None) -> str:
    key = re.sub(r"\s+", "", str(value or "regular")).lower()
    try:
        return STYLE_TAGS[key]
    except KeyError as exc:
        raise EmbeddingError(f"unsupported font style {value!r}; use regular, bold, italic or boldItalic") from exc


def _parse_explicit_font(raw: str, cwd: Path) -> FontSpec:
    if "=" in raw:
        family, path_raw = raw.split("=", 1)
    else:
        family, path_raw = "", raw
    path = Path(path_raw).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return FontSpec(family=family.strip(), path=path.resolve())


def _manifest_specs(manifest_path: Path, font_dir: Path | None) -> list[FontSpec]:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise EmbeddingError(f"font manifest unreadable: {manifest_path}: {exc}") from exc
    entries = data.get("fonts") if isinstance(data, dict) and isinstance(data.get("fonts"), list) else [data]
    if not isinstance(entries, list) or not entries:
        raise EmbeddingError("font manifest must be an object or contain a non-empty fonts list")
    base = font_dir or manifest_path.parent
    specs: list[FontSpec] = []
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise EmbeddingError(f"font manifest entry {index} is not an object")
        raw_file = entry.get("file") or entry.get("path")
        if not raw_file:
            raise EmbeddingError(f"font manifest entry {index} has no file")
        path = Path(str(raw_file)).expanduser()
        if not path.is_absolute():
            path = base / path
        specs.append(FontSpec(
            family=str(entry.get("family") or "").strip(),
            path=path.resolve(),
            style=_normalize_style(entry.get("style") or entry.get("variant") or "regular"),
            expected_sha256=str(entry.get("sha256") or "").strip() or None,
            license_name=str(entry.get("license") or "").strip() or None,
            license_url=str(entry.get("license_url") or "").strip() or None,
        ))
    return specs


def load_specs(font_dir: str | None, manifest: str | None, explicit: list[str]) -> tuple[list[FontSpec], Path | None]:
    root = Path(font_dir).expanduser().resolve() if font_dir else None
    manifest_path: Path | None = Path(manifest).expanduser().resolve() if manifest else None
    if manifest_path is None and root and (root / "font-manifest.json").is_file():
        manifest_path = root / "font-manifest.json"
    specs = _manifest_specs(manifest_path, root) if manifest_path else []
    specs.extend(_parse_explicit_font(raw, Path.cwd()) for raw in explicit)
    if not specs:
        raise EmbeddingError("provide --font-dir with font-manifest.json, --manifest, or at least one --font")
    if root:
        for spec in specs:
            if not inside(root, spec.path):
                raise EmbeddingError(f"font path escapes --font-dir: {spec.path}")
    return specs, manifest_path


def _relationship_target(target: str) -> str:
    target = target.replace("\\", "/")
    return posixpath.normpath(posixpath.join("ppt", target.lstrip("/")))


def _next_rid(rels_root: ET.Element) -> str:
    values = []
    for rel in rels_root.findall(f"{{{REL_NS}}}Relationship"):
        match = re.fullmatch(r"rId(\d+)", rel.get("Id", ""))
        if match:
            values.append(int(match.group(1)))
    return f"rId{max(values, default=0) + 1}"


def _next_font_part(entries: dict[str, bytes]) -> str:
    numbers = []
    for name in entries:
        match = re.fullmatch(r"ppt/fonts/font(\d+)\.fntdata", name)
        if match:
            numbers.append(int(match.group(1)))
    return f"ppt/fonts/font{max(numbers, default=0) + 1}.fntdata"


def _prune_unreferenced_font_parts(
    entries: dict[str, bytes],
    rels_root: ET.Element,
) -> list[str]:
    """Remove font payloads that no presentation relationship can reach.

    A few PPTX writers leave a legacy ``ppt/fonts/font.dat`` payload behind
    while emitting a relationship with a malformed/absolute target.  Keeping
    that payload makes the final package look like it contains an orphaned
    embedded font, so the structural inspection gate blocks an otherwise
    usable deck.  Only files below ``ppt/fonts/`` are considered here; valid
    parts remain because their relationship targets are normalized to the
    package path before comparison.
    """
    referenced: set[str] = set()
    for rel in rels_root.findall(f"{{{REL_NS}}}Relationship"):
        target = rel.get("Target", "")
        if rel.get("Type") != FONT_REL_TYPE or not target:
            continue
        referenced.add(_relationship_target(target))
    removed: list[str] = []
    for name in list(entries):
        if not name.startswith("ppt/fonts/") or name in referenced:
            continue
        removed.append(name)
        entries.pop(name, None)
    return removed


def _remove_existing_family(
    presentation: ET.Element,
    rels_root: ET.Element,
    entries: dict[str, bytes],
    family: str,
) -> None:
    embedded_list = presentation.find(f"{P}embeddedFontLst")
    if embedded_list is None:
        return
    target_rids: set[str] = set()
    for node in list(embedded_list):
        if node.tag != f"{P}embeddedFont":
            continue
        font_node = node.find(f"{P}font")
        if font_node is None or font_node.get("typeface", "").casefold() != family.casefold():
            continue
        for child in list(node):
            rid = child.get(R_ID)
            if rid:
                target_rids.add(rid)
        embedded_list.remove(node)
    for rel in list(rels_root.findall(f"{{{REL_NS}}}Relationship")):
        if rel.get("Id") not in target_rids:
            continue
        target = rel.get("Target", "")
        part = _relationship_target(target)
        if part.startswith("ppt/fonts/"):
            entries.pop(part, None)
        rels_root.remove(rel)


def _ensure_content_type(content_types: ET.Element) -> None:
    for node in content_types.findall(f"{{{CT_NS}}}Default"):
        if node.get("Extension", "").casefold() == "fntdata":
            node.set("ContentType", FONT_CONTENT_TYPE)
            return
    content_types.insert(0, ET.Element(f"{{{CT_NS}}}Default", {"Extension": "fntdata", "ContentType": FONT_CONTENT_TYPE}))


def _ensure_embedded_list(presentation: ET.Element) -> ET.Element:
    embedded_list = presentation.find(f"{P}embeddedFontLst")
    if embedded_list is not None:
        return embedded_list
    embedded_list = ET.Element(f"{P}embeddedFontLst")
    default_text_style = presentation.find(f"{P}defaultTextStyle")
    if default_text_style is not None:
        presentation.insert(list(presentation).index(default_text_style), embedded_list)
    else:
        notes_size = presentation.find(f"{P}notesSz")
        if notes_size is not None:
            presentation.insert(list(presentation).index(notes_size) + 1, embedded_list)
        else:
            presentation.append(embedded_list)
    return embedded_list


def _write_xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True, short_empty_elements=True)


def _families_compatible(declared: str, actual: str) -> bool:
    """Allow a style-suffixed variable-font family to use its root family.

    Some redistributable variable fonts expose ``Family Style`` as name ID 1
    even though fontconfig also exposes the root family.  The manifest and
    PPTX runs should be able to use that stable root family without weakening
    the exact-family check to arbitrary aliases.
    """
    declared_norm = re.sub(r"\s+", " ", declared).strip().casefold()
    actual_norm = re.sub(r"\s+", " ", actual).strip().casefold()
    if declared_norm == actual_norm:
        return True
    if not actual_norm.startswith(declared_norm + " "):
        return False
    suffix = actual_norm[len(declared_norm):].strip()
    return suffix in FAMILY_STYLE_SUFFIXES


def _validate_spec(spec: FontSpec, root: Path | None) -> tuple[bytes, FontMeta, dict]:
    if not spec.path.is_file():
        raise EmbeddingError(f"font file missing: {spec.path}")
    if root and not inside(root, spec.path):
        raise EmbeddingError(f"font path escapes --font-dir: {spec.path}")
    data = spec.path.read_bytes()
    source_sha256 = hashlib.sha256(data).hexdigest()
    if spec.expected_sha256 and source_sha256.casefold() != spec.expected_sha256.casefold():
        raise EmbeddingError(f"font SHA-256 mismatch: {spec.path}")
    meta = parse_font_meta(data)
    family = spec.family or meta.family
    if not family:
        raise EmbeddingError(f"font family is unavailable: {spec.path}")
    if spec.family and meta.family and not _families_compatible(spec.family, meta.family):
        raise EmbeddingError(f"declared family {spec.family!r} does not match font name {meta.family!r}")
    if meta.fs_type & 0x0002:
        raise EmbeddingError(f"font forbids embedding under OS/2 fsType restricted-license bit: {spec.path}")
    meta.family = family
    eot, eot_info = make_eot(data, meta)
    return eot, meta, {
        "family": family,
        "style": spec.style,
        "file": str(spec.path),
        "source_sha256": source_sha256,
        "license": spec.license_name,
        "license_url": spec.license_url,
        "font_data_size": len(data),
        "eot_sha256": hashlib.sha256(eot).hexdigest(),
        "embedding_rights": {
            "fsType": meta.fs_type,
            "restricted_license": bool(meta.fs_type & 0x0002),
            "preview_print": bool(meta.fs_type & 0x0004),
            "editable": bool(meta.fs_type & 0x0008),
        },
        "metadata": {
            "family": meta.family,
            "style_name": meta.style_name,
            "full_name": meta.full_name,
            "weight": meta.weight,
            "italic": bool(meta.italic),
            "sfnt_format": meta.sfnt_format,
        },
        "eot": eot_info,
        "data": eot,
    }


def embed_pptx_fonts(
    input_path: Path,
    output_path: Path,
    specs: list[FontSpec],
    report_path: Path | None = None,
    overwrite: bool = False,
) -> dict:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    issues: list[dict] = []
    result = {
        "schema": "ai-ppt-plus/font-embedding/v1",
        "valid": False,
        "status": "blocked",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(input_path),
        "output": str(output_path),
        "fonts": [],
        "package": {},
        "issues": issues,
    }
    try:
        if input_path == output_path:
            raise EmbeddingError("input and output PPTX must be different paths")
        if not input_path.is_file() or not zipfile.is_zipfile(input_path):
            raise EmbeddingError(f"input is not a valid PPTX zip package: {input_path}")
        if output_path.exists() and not overwrite:
            raise EmbeddingError(f"output already exists; pass --force for an explicit replacement: {output_path}")
        with zipfile.ZipFile(input_path, "r") as source:
            infos = source.infolist()
            entries = {info.filename: source.read(info.filename) for info in infos}
        required = {"[Content_Types].xml", "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels"}
        missing = sorted(required - set(entries))
        if missing:
            raise EmbeddingError(f"PPTX required parts missing: {missing}")

        content_types = ET.fromstring(entries["[Content_Types].xml"])
        presentation = ET.fromstring(entries["ppt/presentation.xml"])
        rels_root = ET.fromstring(entries["ppt/_rels/presentation.xml.rels"])
        pruned_orphan_font_parts = _prune_unreferenced_font_parts(entries, rels_root)
        prepared = [_validate_spec(spec, None) for spec in specs]
        grouped: dict[str, list[dict]] = {}
        for _, _, item in prepared:
            grouped.setdefault(item["family"].casefold(), []).append(item)
        if len(grouped) == 0:
            raise EmbeddingError("no font entries to embed")
        for _, items in grouped.items():
            family = items[0]["family"]
            _remove_existing_family(presentation, rels_root, entries, family)
            seen_styles: set[str] = set()
            embedded_list = _ensure_embedded_list(presentation)
            entry = ET.SubElement(embedded_list, f"{P}embeddedFont")
            ET.SubElement(entry, f"{P}font", {"typeface": family})
            for item in items:
                style = item["style"]
                if style in seen_styles:
                    raise EmbeddingError(f"duplicate {style} font variant for family {family!r}")
                seen_styles.add(style)
                rid = _next_rid(rels_root)
                part = _next_font_part(entries)
                ET.SubElement(entry, f"{P}{style}", {R_ID: rid})
                ET.SubElement(rels_root, f"{{{REL_NS}}}Relationship", {
                    "Id": rid,
                    "Type": FONT_REL_TYPE,
                    "Target": posixpath.relpath(part, "ppt"),
                })
                entries[part] = item["data"]
                item.pop("data", None)
                item["relationship_id"] = rid
                item["part"] = part
                result["fonts"].append(item)
        presentation.set("embedTrueTypeFonts", "1")
        presentation.set("saveSubsetFonts", "0")
        _ensure_content_type(content_types)
        entries["[Content_Types].xml"] = _write_xml(content_types)
        entries["ppt/presentation.xml"] = _write_xml(presentation)
        entries["ppt/_rels/presentation.xml.rels"] = _write_xml(rels_root)
        modified = {"[Content_Types].xml", "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels"} | {item["part"] for item in result["fonts"]}
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=f".{output_path.stem}-", suffix=".pptx", dir=output_path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            original_names = {info.filename for info in infos}
            with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
                for info in infos:
                    if info.filename not in entries:
                        continue
                    if info.filename in modified:
                        target.writestr(info.filename, entries[info.filename])
                    else:
                        target.writestr(info, entries[info.filename])
                for name, data in entries.items():
                    if name not in original_names:
                        target.writestr(name, data)
            if not zipfile.is_zipfile(temporary_path):
                raise EmbeddingError("post-processed output is not a valid zip package")
            # os.replace() atomically replaces an existing destination.  Do
            # not unlink it first: a failed post-process must leave the last
            # valid delivery artifact available to callers.
            os.replace(temporary_path, output_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        result["valid"] = True
        result["status"] = "passed"
        result["package"] = {
            "embedTrueTypeFonts": True,
            "saveSubsetFonts": False,
            "content_type": FONT_CONTENT_TYPE,
            "font_parts": [item["part"] for item in result["fonts"]],
            "pruned_orphan_font_parts": pruned_orphan_font_parts,
            "output_sha256": sha256(output_path),
        }
    except Exception as exc:
        issues.append({"severity": "blocker", "code": "font_embedding_failed", "message": f"{type(exc).__name__}: {exc}"})
    if report_path:
        atomic_write_json(report_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_pptx")
    parser.add_argument("output_pptx")
    parser.add_argument("--font-dir")
    parser.add_argument("--manifest")
    parser.add_argument("--font", action="append", default=[], help="explicit family=font-file; repeat for variants")
    parser.add_argument("--report", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        specs, manifest_path = load_specs(args.font_dir, args.manifest, args.font)
        result = embed_pptx_fonts(Path(args.input_pptx), Path(args.output_pptx), specs, Path(args.report), args.force)
        if manifest_path:
            result["manifest"] = str(manifest_path)
            atomic_write_json(Path(args.report), result)
    except Exception as exc:
        result = {
            "schema": "ai-ppt-plus/font-embedding/v1",
            "valid": False,
            "status": "blocked",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "issues": [{"severity": "blocker", "code": "font_embedding_failed", "message": f"{type(exc).__name__}: {exc}"}],
        }
        atomic_write_json(Path(args.report), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
