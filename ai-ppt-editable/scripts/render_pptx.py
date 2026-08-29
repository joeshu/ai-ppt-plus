#!/usr/bin/env python3
"""Render PPTX through LibreOffice and Poppler with decoded-PNG verification.

R13 hardening: a Poppler process returning exit code 0 is not sufficient. Every
produced PNG must be decodable. If pdftoppm produces invalid PNG output, retry
with pdftocairo before reporting success. When a page cache is supplied, the
renderer reuses only page artifacts whose content fingerprint, DPI, renderer
contract, and font-directory fingerprint still match.
"""
import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from atomic_output import atomic_write_json, atomic_write_text


PAGE_CACHE_SCHEMA = "ai-ppt-plus/page-render-cache/v1"
PAGE_CACHE_ENGINE = "render-pptx-page-cache-v1"
SLIDE_PART_PATTERN = re.compile(r"ppt/slides/slide(\d+)\.xml$")


def png_decodable(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 32:
        return False
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        # verify() checks the PNG structure but may not decode all IDAT data.
        # Re-open and force a full pixel load so truncated renders cannot pass.
        with Image.open(path) as im:
            im.load()
        return True
    except ImportError:
        try:
            data = path.read_bytes()
            return data.startswith(b"\x89PNG\r\n\x1a\n") and b"IEND" in data[-64:]
        except OSError:
            return False
    except Exception:
        return False


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zip_parts(path: Path) -> dict[str, bytes]:
    """Read a PPTX package into a deterministic part map."""
    with zipfile.ZipFile(path) as package:
        parts = {}
        for info in package.infolist():
            if info.is_dir():
                continue
            parts[info.filename] = package.read(info)
    return parts


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _resolve_target(source_part: str, target: str) -> str:
    target = str(target).replace("\\", "/")
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def _rels_part(part: str) -> str:
    directory, filename = posixpath.split(part)
    return posixpath.join(directory, "_rels", filename + ".rels")


def _relationship_targets(parts: dict[str, bytes], source_part: str) -> list[str]:
    """Resolve local relationship targets while preserving missing targets in the rels hash."""
    relationship_part = _rels_part(source_part)
    raw = parts.get(relationship_part)
    if raw is None:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"invalid OOXML relationships: {relationship_part}: {exc}") from exc
    targets = []
    for relationship in root:
        if _local_name(relationship.tag) != "Relationship":
            continue
        if relationship.attrib.get("TargetMode", "").lower() == "external":
            continue
        target = relationship.attrib.get("Target")
        if target:
            targets.append(_resolve_target(source_part, target))
    return targets


def _reachable_parts(parts: dict[str, bytes], root_part: str) -> set[str]:
    """Return a slide's local relationship closure, including each rels part."""
    seen: set[str] = set()
    pending = [root_part]
    while pending:
        part = pending.pop()
        if part in seen:
            continue
        seen.add(part)
        relationship_part = _rels_part(part)
        if relationship_part in parts:
            seen.add(relationship_part)
            for target in _relationship_targets(parts, part):
                if target in parts and target not in seen:
                    pending.append(target)
    return seen


def _presentation_slide_parts(parts: dict[str, bytes]) -> list[str]:
    """Return slide parts in presentation order, not ZIP filename order."""
    presentation = "ppt/presentation.xml"
    presentation_rels = "ppt/_rels/presentation.xml.rels"
    slide_parts = sorted(
        (name for name in parts if SLIDE_PART_PATTERN.fullmatch(name)),
        key=lambda name: int(SLIDE_PART_PATTERN.fullmatch(name).group(1)),
    )
    if presentation not in parts or presentation_rels not in parts:
        return slide_parts
    try:
        presentation_root = ET.fromstring(parts[presentation])
        rels_root = ET.fromstring(parts[presentation_rels])
    except ET.ParseError as exc:
        raise ValueError(f"invalid presentation XML: {exc}") from exc
    relationships = {}
    for relationship in rels_root:
        if _local_name(relationship.tag) == "Relationship" and relationship.attrib.get("Id"):
            relationships[relationship.attrib["Id"]] = relationship.attrib.get("Target")
    ordered = []
    for element in presentation_root.iter():
        if _local_name(element.tag) != "sldId":
            continue
        relationship_id = next(
            (
                value
                for key, value in element.attrib.items()
                if _local_name(key) == "id" and ("relationships" in key or key.startswith("r:"))
            ),
            None,
        )
        target = relationships.get(relationship_id)
        if target:
            slide_part = _resolve_target(presentation, target)
            if slide_part in parts and slide_part not in ordered:
                ordered.append(slide_part)
    # A valid package should have an exact list. Keeping unlisted slide parts
    # makes the fingerprint diagnostic useful even for partially malformed decks.
    ordered.extend(part for part in slide_parts if part not in ordered)
    return ordered


def _hash_parts(parts: dict[str, bytes], names: set[str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(names):
        if name not in parts:
            continue
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(parts[name])
        digest.update(b"\0")
    return digest.hexdigest()


def slide_fingerprints(path: Path) -> list[dict]:
    """Fingerprint each rendered page's OOXML closure plus shared render inputs."""
    parts = _zip_parts(path)
    ordered_slides = _presentation_slide_parts(parts)
    if not ordered_slides:
        raise ValueError("PPTX contains no slide parts")
    shared = {
        "[Content_Types].xml",
        "ppt/presentation.xml",
        "ppt/_rels/presentation.xml.rels",
    }
    shared.update(name for name in parts if name.startswith(("ppt/theme/", "ppt/slideMasters/", "ppt/slideLayouts/")))
    fingerprints = []
    for page, slide_part in enumerate(ordered_slides, 1):
        names = _reachable_parts(parts, slide_part) | shared
        fingerprints.append({"page": page, "part": slide_part, "fingerprint": _hash_parts(parts, names)})
    return fingerprints


def _font_directory_digest(font_dir: Path | None) -> str | None:
    if font_dir is None:
        return None
    if not font_dir.is_dir():
        raise ValueError(f"font directory not found: {font_dir}")
    digest = hashlib.sha256()
    for child in sorted(
        (item for item in font_dir.rglob("*") if item.is_file()),
        key=lambda item: str(item.relative_to(font_dir)),
    ):
        relative = str(child.relative_to(font_dir)).replace(os.sep, "/")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_file_sha256(child).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _page_cache_namespace(dpi: int, font_digest: str | None) -> str:
    payload = {
        "schema": PAGE_CACHE_SCHEMA,
        "engine": PAGE_CACHE_ENGINE,
        "renderer_code_sha256": _file_sha256(Path(__file__).resolve()),
        "dpi": int(dpi),
        "font_directory_sha256": font_digest,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cache_path(page_cache_dir: Path, namespace: str, page: int, fingerprint: str) -> Path:
    return page_cache_dir / namespace / f"slide-{page}-{fingerprint}.png"


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as destination, source.open("rb") as origin:
            shutil.copyfileobj(origin, destination)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_cached_page(cache_path: Path, target: Path) -> bool:
    if not png_decodable(cache_path):
        return False
    try:
        _atomic_copy(cache_path, target)
    except OSError:
        return False
    return png_decodable(target)


def _store_cached_page(source: Path, cache_path: Path) -> bool:
    if not png_decodable(source):
        return False
    try:
        if png_decodable(cache_path):
            return True
        _atomic_copy(source, cache_path)
    except OSError:
        return False
    return png_decodable(cache_path)


def _page_number(path: Path) -> int | None:
    match = re.fullmatch(r"slide-(\d+)\.png", path.name)
    return int(match.group(1)) if match else None


def _render_selected_pages(pdf: Path, out: Path, dpi: int, selected: set[int], binary: str, backend: str):
    rendered = {}
    attempts = []
    for page in sorted(selected):
        prefix = out / f".selected-{page}"
        for stale in out.glob(f".selected-{page}*"):
            stale.unlink()
        command = [binary, "-png", "-r", str(dpi), "-f", str(page), "-l", str(page), "-singlefile", str(pdf), str(prefix)]
        cp = subprocess.run(command, capture_output=True, text=True)
        candidates = [prefix.with_suffix(".png"), *sorted(out.glob(f".selected-{page}*.png"))]
        candidate = next((path for path in candidates if path.is_file()), None)
        decoded = bool(candidate and png_decodable(candidate))
        attempts.append({"backend": backend, "page": page, "exit_code": cp.returncode, "decoded": decoded, "stderr": cp.stderr.strip()})
        if cp.returncode == 0 and decoded:
            target = out / f"slide-{page}.png"
            if target.exists():
                target.unlink()
            candidate.replace(target)
            rendered[page] = target
        else:
            for stale in out.glob(f".selected-{page}*"):
                stale.unlink()
    return rendered, attempts


def render_pdf(pdf: Path, out: Path, dpi: int, selected: set[int] | None = None):
    attempts = []
    for old in out.glob("slide-*.png"):
        page = _page_number(old)
        if selected is None or page in selected:
            old.unlink()
    pdftoppm = shutil.which("pdftoppm")
    pdftocairo = shutil.which("pdftocairo")
    if selected is not None:
        rendered = {}
        backends = [(pdftoppm, "pdftoppm"), (pdftocairo, "pdftocairo")]
        for binary, backend in backends:
            if not binary:
                continue
            remaining = set(selected) - set(rendered)
            if not remaining:
                break
            page_results, page_attempts = _render_selected_pages(pdf, out, dpi, remaining, binary, backend)
            rendered.update(page_results)
            attempts.extend(page_attempts)
        files = [rendered[page] for page in sorted(rendered)]
        backends_used = sorted({item["backend"] for item in attempts if item.get("decoded")})
        return files, "+".join(backends_used) if backends_used else None, attempts
    if pdftoppm:
        cp = subprocess.run([pdftoppm, "-png", "-r", str(dpi), str(pdf), str(out / "slide")], capture_output=True, text=True)
        files = sorted(out.glob("slide-*.png"), key=lambda x: int(x.stem.split("-")[-1]))
        valid = bool(files) and all(png_decodable(p) for p in files)
        attempts.append({"backend": "pdftoppm", "exit_code": cp.returncode, "decoded": valid, "stderr": cp.stderr.strip()})
        if cp.returncode == 0 and valid:
            return files, "pdftoppm", attempts
    for old in out.glob("slide-*.png"):
        old.unlink()
    if pdftocairo:
        cp = subprocess.run([pdftocairo, "-png", "-r", str(dpi), str(pdf), str(out / "slide")], capture_output=True, text=True)
        files = sorted(out.glob("slide-*.png"), key=lambda x: int(x.stem.split("-")[-1]))
        valid = bool(files) and all(png_decodable(p) for p in files)
        attempts.append({"backend": "pdftocairo", "exit_code": cp.returncode, "decoded": valid, "stderr": cp.stderr.strip()})
        if cp.returncode == 0 and valid:
            return files, "pdftocairo", attempts
    return [], None, attempts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pptx")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--dpi", type=int, default=144)
    ap.add_argument("--pages", help="comma-separated pages/ranges, e.g. 1,3-5")
    ap.add_argument("--font-dir", help="task-local TTF/OTF/TTC directory")
    ap.add_argument("--page-cache-dir", help="content-addressed cache for validated per-page PNG artifacts")
    ap.add_argument("--report")
    a = ap.parse_args()
    src = Path(a.pptx).resolve()
    out = Path(a.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    poppler_available = bool(shutil.which("pdftoppm") or shutil.which("pdftocairo"))
    errors = []
    pages = []
    renderer = None
    attempts = []
    conversion_attempted = False
    conversion_skipped = False
    cache_warnings = []
    font_dir = Path(a.font_dir).resolve() if a.font_dir else None
    if font_dir and not font_dir.is_dir(): errors.append("font directory not found")
    page_cache_dir = Path(a.page_cache_dir).resolve() if a.page_cache_dir else None
    selected = None
    if a.pages:
        try:
            selected = set()
            for part in a.pages.split(","):
                if "-" in part:
                    lo, hi = map(int, part.split("-", 1)); selected.update(range(lo, hi + 1))
                else: selected.add(int(part))
            if not selected or min(selected) < 1:
                raise ValueError
        except Exception:
            errors.append("invalid --pages expression")

    fingerprints = []
    requested_pages: set[int] = set()
    cache_hits: set[int] = set()
    missing_pages: set[int] = set()
    font_digest = None
    namespace = None
    if not src.is_file():
        errors.append("PPTX not found")
    if not errors:
        try:
            fingerprints = slide_fingerprints(src)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            errors.append(f"could not fingerprint PPTX pages: {type(exc).__name__}: {exc}")
        if fingerprints:
            page_count = len(fingerprints)
            requested_pages = set(range(1, page_count + 1)) if selected is None else set(selected)
            if min(requested_pages, default=0) < 1 or max(requested_pages, default=0) > page_count:
                errors.append(f"requested page is outside PPTX page range 1-{page_count}")
                requested_pages = set()
        if page_cache_dir:
            try:
                font_digest = _font_directory_digest(font_dir)
                namespace = _page_cache_namespace(a.dpi, font_digest)
            except (OSError, ValueError) as exc:
                errors.append(f"could not prepare page cache: {type(exc).__name__}: {exc}")

    # A run directory is an immutable render result. Remove stale page files
    # before restoring cache hits so a selected-page run cannot leak old pages.
    for old in out.glob("slide-*.png"):
        if old.is_file():
            old.unlink()

    if not errors and requested_pages:
        if page_cache_dir:
            for page in sorted(requested_pages):
                fingerprint = fingerprints[page - 1]["fingerprint"]
                cached = _cache_path(page_cache_dir, namespace, page, fingerprint)
                target = out / f"slide-{page}.png"
                if _load_cached_page(cached, target):
                    cache_hits.add(page)
            missing_pages = requested_pages - cache_hits
        else:
            missing_pages = set(requested_pages)

        if page_cache_dir and not missing_pages:
            conversion_skipped = True

        if missing_pages:
            if not soffice:
                errors.append("LibreOffice/soffice not found")
            if not poppler_available:
                errors.append("Poppler PNG renderer not found")
            if not errors:
                conversion_attempted = True
                with tempfile.TemporaryDirectory() as td:
                    profile = (Path(td) / "lo-profile").resolve()
                    profile.mkdir()
                    env = os.environ.copy()
                    if font_dir:
                        conf = Path(td) / "fonts.conf"
                        atomic_write_text(
                            conf,
                            f'<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir>{font_dir}</dir><include ignore_missing="yes">/etc/fonts/fonts.conf</include></fontconfig>',
                        )
                        env["FONTCONFIG_FILE"] = str(conf)
                    cp = subprocess.run(
                        [soffice, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--convert-to", "pdf", "--outdir", td, str(src)],
                        capture_output=True,
                        text=True,
                        env=env,
                    )
                    pdf = Path(td) / (src.stem + ".pdf")
                    if cp.returncode or not pdf.exists():
                        errors.append("LibreOffice conversion failed: " + (cp.stderr or cp.stdout).strip())
                    else:
                        # Render each missing page through the selected-page
                        # path.  A full pdftoppm stream can return exit code 0
                        # while a target PNG is still truncated on some
                        # environments; the per-page path verifies and retries
                        # each artifact before publishing it.  This is slightly
                        # slower, but makes the default no-cache render obey the
                        # same decoded-PNG contract as incremental rendering.
                        render_selection = set(missing_pages)
                        rendered, renderer, attempts = render_pdf(pdf, out, a.dpi, render_selection)
                        rendered_by_page = {page: path for path in rendered if (page := _page_number(path)) is not None}
                        rendered_missing = missing_pages.intersection(rendered_by_page)
                        if rendered_missing != missing_pages:
                            errors.append("one or more requested pages do not exist or could not be rendered")
                        if page_cache_dir:
                            for page in sorted(rendered_missing):
                                cache_path = _cache_path(page_cache_dir, namespace, page, fingerprints[page - 1]["fingerprint"])
                                if _store_cached_page(rendered_by_page[page], cache_path):
                                    cache_warnings.append({"page": page, "status": "stored"})
                                else:
                                    cache_warnings.append({"page": page, "status": "store_failed"})

    expected_paths = [out / f"slide-{page}.png" for page in sorted(requested_pages)]
    if not errors and (not expected_paths or not all(png_decodable(path) for path in expected_paths)):
        errors.append("Poppler rendering failed or produced undecodable PNG output")
    pages = [str(path.resolve()) for path in expected_paths if path.is_file() and png_decodable(path)]
    page_cache_report = {
        "schema": PAGE_CACHE_SCHEMA,
        "enabled": page_cache_dir is not None,
        "dir": str(page_cache_dir) if page_cache_dir else None,
        "namespace": namespace,
        "requested": len(requested_pages),
        "hits": len(cache_hits),
        "misses": len(missing_pages) if page_cache_dir else 0,
        "stored": sum(1 for item in cache_warnings if item["status"] == "stored"),
        "warnings": [item for item in cache_warnings if item["status"] != "stored"],
    }
    page_report = []
    for item in fingerprints:
        page_report.append({**item, "selected": item["page"] in requested_pages, "cache_hit": item["page"] in cache_hits})
    digest = _file_sha256(src) if src.is_file() else None
    if conversion_skipped:
        renderer_label = "page-cache"
    elif renderer:
        renderer_label = f"LibreOffice+{renderer}"
    else:
        renderer_label = "LibreOffice+Poppler"
    report = {
        "schema": "ai-ppt-plus/render/v1",
        "ok": not errors and len(pages) == len(requested_pages),
        "source": str(src),
        "deck_sha256": digest,
        "renderer": renderer_label,
        "render_attempts": attempts,
        "conversion": {"attempted": conversion_attempted, "skipped": conversion_skipped, "reason": "all_requested_pages_cached" if conversion_skipped else "page_cache_miss" if page_cache_dir and missing_pages else "cache_disabled" if missing_pages else "not_run"},
        "font_dir": str(font_dir) if font_dir else None,
        "dpi": a.dpi,
        "selected_pages": sorted(selected) if selected is not None else "all",
        "page_fingerprints": page_report,
        "page_cache": page_cache_report,
        "pages": pages,
        "errors": errors,
    }
    if a.report:
        atomic_write_json(Path(a.report), report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
