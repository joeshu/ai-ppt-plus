#!/usr/bin/env node
/**
 * Strict native authoring entrypoint for approved layout JSON.
 *
 * The input contract is the same flat deck contract consumed by compose_pptx.py:
 * coordinates are fractions by default (or pixels when `units` is `px`), and
 * each slide keeps text, shapes, tables, charts and independent image assets
 * in separate arrays.  This file deliberately owns the authoring operation so
 * the strict route can be audited without loading the historical composer.
 */
import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { loadArtifactTool, registerFonts, resolveNodeModules } from "./artifact_tool_runtime.mjs";

const PX_PER_INCH = 96;
const PT_TO_PX = PX_PER_INCH / 72;
const DEFAULT_WIDTH = 1280;
const DEFAULT_HEIGHT = 720;

function value(argv, name, fallback = undefined) {
  const index = argv.indexOf(name);
  return index >= 0 && argv[index + 1] !== undefined ? argv[index + 1] : fallback;
}

function has(argv, name) {
  return argv.includes(name);
}

function fail(message) {
  throw new Error(message);
}

function finiteNumber(raw, field, fallback = undefined) {
  if (raw === undefined || raw === null || raw === "") {
    if (fallback !== undefined) return fallback;
    fail(`${field} is required`);
  }
  const number = Number(raw);
  if (!Number.isFinite(number)) fail(`${field} must be finite`);
  return number;
}

function positiveNumber(raw, field, fallback = undefined) {
  const number = finiteNumber(raw, field, fallback);
  if (number <= 0) fail(`${field} must be positive`);
  return number;
}

function sha256(file) {
  return crypto.createHash("sha256").update(file).digest("hex");
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function canonicalSha256(value) {
  return sha256(Buffer.from(canonicalJson(value), "utf8"));
}

function normaliseColor(value, fallback = "#111111") {
  if (value === undefined || value === null || value === "") return fallback;
  if (typeof value === "object") return value;
  return String(value);
}

function withOpacity(color, opacity) {
  if (opacity === undefined || opacity === null || typeof color !== "string") return color;
  const amount = Math.max(0, Math.min(1, Number(opacity)));
  if (!Number.isFinite(amount) || amount >= 0.999) return color;
  if (color.startsWith("#") || /^[A-Za-z][A-Za-z0-9-]*$/.test(color)) {
    return `${color}/${Math.round(amount * 100)}`;
  }
  return color;
}

function fillConfig(spec, fallback = "none") {
  if (!spec) return fallback;
  const gradient = spec.gradient || spec.fill_gradient;
  if (gradient && typeof gradient === "object") {
    const stops = Array.isArray(gradient.stops) ? gradient.stops : [];
    if (stops.length < 2) fail("gradient fill requires at least two stops");
    return {
      type: "gradient",
      gradientKind: gradient.gradientKind || gradient.kind || "linear",
      angleDeg: finiteNumber(gradient.angleDeg ?? gradient.angle ?? 0, "gradient.angle"),
      stops: stops.map((stop, index) => {
        if (!stop || typeof stop !== "object") fail(`gradient stop ${index + 1} must be an object`);
        const raw = stop.offset ?? stop.position ?? stop.pos ?? 0;
        let offset = finiteNumber(raw, `gradient.stop[${index}].offset`);
        if (offset <= 1) offset *= 100000;
        else if (offset <= 1000) offset *= 100;
        offset = Math.max(0, Math.min(100000, Math.round(offset)));
        return {
          offset,
          color: withOpacity(normaliseColor(stop.color, "#FFFFFF"), stop.opacity),
        };
      }),
    };
  }
  if (spec.fill !== undefined) return withOpacity(normaliseColor(spec.fill), spec.opacity);
  if (typeof spec === "string") return spec;
  return fallback;
}

function lineConfig(spec) {
  const raw = spec.line;
  if (raw === undefined || raw === null || raw === "" || raw === "none") {
    return { style: "solid", fill: "none", width: 0 };
  }
  if (typeof raw === "object") {
    return {
      style: raw.style || "solid",
      fill: fillConfig(raw.fill ?? raw.color, "#D9D9D9"),
      width: finiteNumber(raw.width ?? raw.weight ?? spec.line_width ?? 1, "line.width"),
    };
  }
  return {
    style: "solid",
    fill: withOpacity(String(raw), spec.line_opacity),
    width: finiteNumber(spec.line_width ?? 1, "line.width"),
  };
}

function shapeGeometry(raw) {
  const key = String(raw || "rect").trim().toLowerCase().replace(/[ -]/g, "_");
  const map = {
    rounded_rect: "roundRect",
    rounded_rectangle: "roundRect",
    round_rect: "roundRect",
    rectangle: "rect",
    oval: "ellipse",
    circle: "ellipse",
    right_arrow: "rightArrow",
    left_arrow: "leftArrow",
    up_arrow: "upArrow",
    down_arrow: "downArrow",
    line: "line",
    connector: "line",
  };
  return map[key] || raw || "rect";
}

const AUTHORABLE_GEOMETRY = new Set([
  "RECT", "ROUNDRECT", "ELLIPSE", "TRAPEZOID", "FUNNEL",
  "FILLED_ARROW", "CONNECTOR", "FREEFORM_BEZIER",
]);

function geometryBindingKey(page, objectId) {
  return `${page}:${objectId}`;
}

function geometryBindingFor(bindings, page, spec) {
  if (!bindings) return null;
  const objectId = spec?.object_id || spec?.name;
  return objectId ? bindings.get(geometryBindingKey(page, String(objectId))) || null : null;
}

function geometryFromBinding(binding, fallback) {
  if (!binding) return fallback;
  const primitive = String(binding.primitive || "").toUpperCase();
  const parameters = binding.parameters && typeof binding.parameters === "object" ? binding.parameters : {};
  if (primitive === "RECT" || primitive === "TRAPEZOID" || primitive === "FUNNEL" || primitive === "FREEFORM_BEZIER") return "rect";
  if (primitive === "ROUNDRECT") return "roundRect";
  if (primitive === "ELLIPSE") return "ellipse";
  if (primitive === "CONNECTOR") return "line";
  if (primitive === "FILLED_ARROW") {
    const direction = String(parameters.direction || "right").toLowerCase();
    return ({ up: "upArrow", down: "downArrow", left: "leftArrow", right: "rightArrow" })[direction] || "rightArrow";
  }
  return fallback;
}

function collectLayoutObjectIds(value, output) {
  if (!value || typeof value !== "object") return;
  const objectId = value.object_id || value.name;
  if (objectId) output.add(String(objectId));
  if (Array.isArray(value.children)) value.children.forEach((child) => collectLayoutObjectIds(child, output));
}

async function loadGeometryResolution(argv, deck) {
  const rawPath = value(argv, "--geometry-resolution");
  if (!rawPath) return { path: null, map: null, targets: [], report: null };
  const resolutionPath = path.resolve(rawPath);
  const bytes = await fs.readFile(resolutionPath).catch((error) => fail(`geometry resolution cannot be read: ${error.message}`));
  let resolution;
  try { resolution = JSON.parse(bytes.toString("utf8")); } catch (error) { fail(`geometry resolution is not valid JSON: ${error.message}`); }
  if (resolution.schema !== "ai-ppt-plus/geometry-primitive-resolution/v2" || resolution.valid !== true || resolution.repair_required) {
    fail("geometry resolution must be a strict-ready v2 report");
  }
  const map = new Map();
  const targets = [];
  for (const item of resolution.resolutions || []) {
    const primitive = String(item?.primitive || "").toUpperCase();
    if (!AUTHORABLE_GEOMETRY.has(primitive)) continue;
    const objectId = String(item?.object_id || "").trim();
    const page = Number(item?.page);
    if (!objectId || !Number.isInteger(page) || page < 1 || page > deck.slides.length) fail(`geometry binding target is invalid: page ${item?.page}, object ${item?.object_id}`);
    const key = geometryBindingKey(page, objectId);
    if (map.has(key)) fail(`geometry binding target is duplicated: ${key}`);
    const binding = { object_id: objectId, page, primitive, parameters: item.parameters && typeof item.parameters === "object" ? item.parameters : {} };
    map.set(key, binding);
    targets.push(binding);
    const ids = new Set();
    const slide = deck.slides[page - 1] || {};
    for (const spec of slide.shapes || []) collectLayoutObjectIds(spec, ids);
    for (const group of slide.groups || []) collectLayoutObjectIds(group, ids);
    if (!ids.has(objectId)) fail(`geometry binding target is absent from layout: page ${page}, object ${objectId}`);
  }
  return {
    path: resolutionPath,
    map,
    targets,
    report: {
      schema: "ai-ppt-plus/geometry-artifact-tool-binding/v1",
      valid: true,
      status: "passed",
      resolution_sha256: canonicalSha256(resolution),
      target_count: targets.length,
      targets,
    },
  };
}

function slideDimensions(deck) {
  const canvas = deck.canvas && typeof deck.canvas === "object" ? deck.canvas : {};
  const width = positiveNumber(deck.slide_width_px ?? canvas.width, "slide_width_px", positiveNumber(deck.slide_width_in, "slide_width_in", DEFAULT_WIDTH / PX_PER_INCH) * PX_PER_INCH);
  const height = positiveNumber(deck.slide_height_px ?? canvas.height, "slide_height_px", positiveNumber(deck.slide_height_in, "slide_height_in", DEFAULT_HEIGHT / PX_PER_INCH) * PX_PER_INCH);
  return { width, height };
}

function coordinate(spec, key, axis, deck, dimensions) {
  const bbox = Array.isArray(spec.bbox) ? spec.bbox : null;
  const index = axis === "x" ? 0 : 1;
  const sizeIndex = axis === "x" ? 2 : 3;
  const raw = bbox ? bbox[index] : spec[key] ?? spec[axis === "x" ? "left" : "top"];
  if (raw === undefined) fail(`${key} coordinate is required`);
  const units = deck.units || "fraction";
  if (units === "px") {
    const reference = positiveNumber(axis === "x" ? (deck.ref_width ?? deck.reference_width ?? dimensions.width) : (deck.ref_height ?? deck.reference_height ?? dimensions.height), `${axis === "x" ? "ref_width" : "ref_height"}`);
    return finiteNumber(raw, key) / reference * (axis === "x" ? dimensions.width : dimensions.height);
  }
  if (units !== "fraction") fail(`unsupported coordinate units: ${units}`);
  return finiteNumber(raw, key) * (axis === "x" ? dimensions.width : dimensions.height);
}

function sizeCoordinate(spec, key, axis, deck, dimensions) {
  const bbox = Array.isArray(spec.bbox) ? spec.bbox : null;
  const index = axis === "x" ? 2 : 3;
  const raw = bbox ? bbox[index] : spec[key] ?? spec[axis === "x" ? "width" : "height"];
  if (raw === undefined) fail(`${key} coordinate is required`);
  const units = deck.units || "fraction";
  if (units === "px") {
    const reference = positiveNumber(axis === "x" ? (deck.ref_width ?? deck.reference_width ?? dimensions.width) : (deck.ref_height ?? deck.reference_height ?? dimensions.height), `${axis === "x" ? "ref_width" : "ref_height"}`);
    return positiveNumber(raw, key) / reference * (axis === "x" ? dimensions.width : dimensions.height);
  }
  if (units !== "fraction") fail(`unsupported coordinate units: ${units}`);
  return positiveNumber(raw, key) * (axis === "x" ? dimensions.width : dimensions.height);
}

function position(spec, deck, dimensions) {
  const left = coordinate(spec, "x", "x", deck, dimensions);
  const top = coordinate(spec, "y", "y", deck, dimensions);
  const width = sizeCoordinate(spec, "w", "x", deck, dimensions);
  const height = sizeCoordinate(spec, "h", "y", deck, dimensions);
  if (deck.strict_input && spec.allow_bleed !== true && (left < 0 || top < 0 || left + width > dimensions.width + 0.01 || top + height > dimensions.height + 0.01)) {
    fail(`object ${spec.object_id || spec.name || "unnamed"} is outside the slide`);
  }
  return { left, top, width, height, ...(spec.rotation !== undefined ? { rotation: finiteNumber(spec.rotation, "rotation") } : {}) };
}

function fontPixels(spec = {}, theme = {}, deck = {}, dimensions = { height: DEFAULT_HEIGHT }) {
  const referenceHeight = positiveNumber(deck.ref_height ?? deck.reference_height ?? dimensions.height, "reference_height");
  let points;
  if (spec.font_size_px ?? spec.size_px ?? spec.fontSizePx) {
    const raw = Number(spec.font_size_px ?? spec.size_px ?? spec.fontSizePx);
    points = raw * (positiveNumber(deck.slide_height_in, "slide_height_in", dimensions.height / PX_PER_INCH) * 72) / referenceHeight;
  } else if (spec.size_ratio !== undefined) {
    points = finiteNumber(spec.size_ratio, "size_ratio") * positiveNumber(deck.slide_height_in, "slide_height_in", dimensions.height / PX_PER_INCH) * 72;
  } else if (spec.size_pct !== undefined) {
    points = finiteNumber(spec.size_pct, "size_pct") / 100 * positiveNumber(deck.slide_height_in, "slide_height_in", dimensions.height / PX_PER_INCH) * 72;
  } else {
    points = finiteNumber(spec.font_size_pt ?? spec.size ?? theme.size ?? 18, "font_size_pt");
  }
  if (points <= 0) fail("font size must be positive");
  return points * PT_TO_PX;
}

function baseTextStyle(spec = {}, theme = {}, deck = {}, dimensions) {
  const alignment = String(spec.align ?? spec.alignment ?? "left").toLowerCase();
  const vertical = String(spec.valign ?? spec.vertical_alignment ?? "top").toLowerCase();
  const alignmentMap = { left: "left", center: "center", right: "right", justify: "justify" };
  const verticalMap = { top: "top", middle: "middle", center: "middle", bottom: "bottom" };
  if (deck.strict_input && !alignmentMap[alignment]) fail(`unsupported text alignment: ${alignment}`);
  if (deck.strict_input && !verticalMap[vertical]) fail(`unsupported vertical alignment: ${vertical}`);
  const insets = {
    top: finiteNumber(spec.margin_top ?? 0, "margin_top"),
    right: finiteNumber(spec.margin_right ?? 0, "margin_right"),
    bottom: finiteNumber(spec.margin_bottom ?? 0, "margin_bottom"),
    left: finiteNumber(spec.margin_left ?? 0, "margin_left"),
  };
  return {
    typeface: String(spec.font ?? spec.font_family ?? theme.font ?? deck.font_family ?? "Microsoft YaHei"),
    fontSize: fontPixels(spec, theme, deck, dimensions),
    color: withOpacity(normaliseColor(spec.color ?? theme.text_color, "#111111"), spec.opacity),
    bold: Boolean(spec.bold),
    italic: Boolean(spec.italic),
    alignment: alignmentMap[alignment] || "left",
    verticalAlignment: verticalMap[vertical] || "top",
    wrap: spec.wrap || "square",
    autoFit: spec.auto_fit || spec.autoFit || "none",
    insets,
    ...(spec.line_spacing !== undefined ? { lineSpacing: finiteNumber(spec.line_spacing, "line_spacing") } : {}),
  };
}

function runInput(run, theme, deck, dimensions, inherited = {}) {
  if (typeof run === "string" || typeof run === "number") return String(run);
  if (!run || typeof run !== "object") return "";
  const rawText = run.text ?? run.run ?? "";
  const style = run.textStyle && typeof run.textStyle === "object" ? run.textStyle : {};
  const merged = {
    ...inherited,
    ...style,
    ...(run.font ? { font: run.font } : {}),
    ...(run.font_family ? { font_family: run.font_family } : {}),
    ...(run.typeface ? { typeface: run.typeface } : {}),
    ...(run.color !== undefined ? { color: run.color } : {}),
    ...(run.bold !== undefined ? { bold: run.bold } : {}),
    ...(run.italic !== undefined ? { italic: run.italic } : {}),
    ...(run.underline !== undefined ? { underline: run.underline } : {}),
    ...(run.fontSize !== undefined ? { fontSize: run.fontSize } : {}),
    ...(run.font_size !== undefined ? { font_size: run.font_size } : {}),
    ...(run.font_size_pt !== undefined ? { font_size_pt: run.font_size_pt } : {}),
    ...(run.size !== undefined ? { size: run.size } : {}),
    ...(run.size_pt !== undefined ? { size_pt: run.size_pt } : {}),
  };
  const textStyle = {};
  if (merged.bold !== undefined) textStyle.bold = Boolean(merged.bold);
  if (merged.italic !== undefined) textStyle.italic = Boolean(merged.italic);
  if (merged.underline !== undefined) textStyle.underline = merged.underline;
  if (merged.typeface ?? merged.font ?? merged.font_family) textStyle.typeface = String(merged.typeface ?? merged.font ?? merged.font_family);
  if (merged.color !== undefined) textStyle.color = withOpacity(normaliseColor(merged.color), merged.opacity);
  if (merged.fontSize !== undefined) {
    // Artifact Tool's structured run contract uses a unit string for this
    // field.  Numeric `fontSize` values are already pixels in that contract.
    textStyle.fontSize = typeof merged.fontSize === "string" ? merged.fontSize : `${finiteNumber(merged.fontSize, "run.fontSize")}px`;
  } else if (merged.font_size !== undefined || merged.size !== undefined || merged.size_pt !== undefined || merged.font_size_pt !== undefined) {
    textStyle.fontSize = `${fontPixels({ ...merged, size: merged.size ?? merged.size_pt, font_size_pt: merged.font_size_pt ?? merged.font_size }, theme, deck, dimensions)}px`;
  }
  const result = { run: String(rawText), textStyle };
  if (run.link && typeof run.link === "object") result.link = run.link;
  return result;
}

function structuredText(spec, theme, deck, dimensions) {
  const inherited = {
    font: spec.font ?? spec.font_family ?? theme.font ?? deck.font_family ?? "Microsoft YaHei",
    size: spec.size ?? spec.size_pt ?? theme.size ?? 18,
    color: spec.color ?? theme.text_color ?? "#111111",
    bold: spec.bold,
    italic: spec.italic,
  };
  const rawRuns = Array.isArray(spec.runs) ? spec.runs : null;
  if (rawRuns) {
    return [rawRuns.map((run) => runInput(run, theme, deck, dimensions, inherited))];
  }
  const paragraphs = Array.isArray(spec.paragraphs) ? spec.paragraphs : null;
  if (paragraphs) {
    return paragraphs.map((paragraph) => {
      if (Array.isArray(paragraph)) return paragraph.map((run) => runInput(run, theme, deck, dimensions, inherited));
      const runs = Array.isArray(paragraph?.runs) ? paragraph.runs : [paragraph?.text ?? ""];
      return {
        ...(paragraph && typeof paragraph === "object" ? Object.fromEntries(["bulletCharacter", "marginLeft", "indent", "spaceBefore", "spaceAfter", "styleId", "paragraphStyle"].filter((key) => paragraph[key] !== undefined).map((key) => [key, paragraph[key]])) : {}),
        runs: runs.map((run) => runInput(run, theme, deck, dimensions, inherited)),
      };
    });
  }
  return null;
}

function applyText(shape, spec, theme, deck, dimensions) {
  const style = baseTextStyle(spec, theme, deck, dimensions);
  const rich = structuredText(spec, theme, deck, dimensions);
  if (rich) {
    // Apply the base style first; the Artifact Tool preserves local run styles
    // only when the shape style is established before the structured value.
    shape.text.style = style;
    shape.text.set(rich);
  } else if (spec.text !== undefined) {
    shape.text = Array.isArray(spec.text) ? spec.text.map(String) : String(spec.text);
    shape.text.style = style;
  }
  return shape;
}

function addShape(slide, spec, theme, deck, dimensions, namePrefix = "", page = 1, geometryBindings = null) {
  const name = `${namePrefix}${spec.object_id || spec.name || "shape"}`;
  const binding = geometryBindingFor(geometryBindings, page, spec);
  const geometry = geometryFromBinding(binding, shapeGeometry(spec.type || spec.geometry || "rect"));
  if (geometry === "line") {
    const x1 = coordinate(spec, "x", "x", deck, dimensions);
    const y1 = coordinate(spec, "y", "y", deck, dimensions);
    let x2 = x1 + (spec.w !== undefined ? (deck.units === "px" ? finiteNumber(spec.w, "w") / positiveNumber(deck.ref_width ?? deck.reference_width ?? dimensions.width, "ref_width") * dimensions.width : finiteNumber(spec.w, "w") * dimensions.width) : 0);
    let y2 = y1 + (spec.h !== undefined ? (deck.units === "px" ? finiteNumber(spec.h, "h") / positiveNumber(deck.ref_height ?? deck.reference_height ?? dimensions.height, "ref_height") * dimensions.height : finiteNumber(spec.h, "h") * dimensions.height) : 0);
    if (spec.x2 !== undefined || spec.y2 !== undefined) {
      if (spec.x2 === undefined || spec.y2 === undefined) fail(`line ${name} requires both x2 and y2`);
      // `coordinate` reads the value from the key passed as its second
      // argument.  The line endpoint is supplied through the normalized x/y
      // fields of the temporary spec; passing "x2"/"y2" here makes the
      // helper look for a non-existent x2/y2 property and rejects every
      // otherwise valid endpoint under strict input.
      x2 = coordinate({ x: spec.x2 }, "x", "x", deck, dimensions);
      y2 = coordinate({ y: spec.y2 }, "y", "y", deck, dimensions);
    }
    const left = Math.min(x1, x2); const top = Math.min(y1, y2);
    const line = slide.shapes.add({
      geometry: "line",
      name,
      position: { left, top, width: Math.abs(x2 - x1), height: Math.abs(y2 - y1), horizontalFlip: x2 < x1, verticalFlip: y2 < y1 },
      fill: "none",
      line: lineConfig(spec),
    });
    return line;
  }
  const pos = position(spec, deck, dimensions);
  const shape = slide.shapes.add({
    geometry,
    name,
    position: pos,
    fill: fillConfig(spec, "none"),
    line: lineConfig(spec),
    ...(spec.border_radius !== undefined || spec.radius !== undefined ? { borderRadius: Number(spec.border_radius ?? spec.radius) } : {}),
    ...(spec.shadow ? { shadow: typeof spec.shadow === "string" ? spec.shadow : "shadow-sm" } : {}),
    ...(spec.className ? { className: spec.className } : {}),
  });
  if (spec.text !== undefined || spec.runs || spec.paragraphs) applyText(shape, spec, theme, deck, dimensions);
  return shape;
}

function addGroupChildren(slide, group, theme, deck, dimensions, page = 1, geometryBindings = null) {
  const children = Array.isArray(group.children) ? group.children : [];
  const hasBox = ["x", "y", "w", "h"].every((key) => group[key] !== undefined);
  const groupPos = hasBox ? position(group, deck, dimensions) : null;
  const local = group.children_coordinate_space === "local";
  return children.map((raw, index) => {
    if (!raw || typeof raw !== "object") fail(`group child ${index + 1} must be an object`);
    const child = { ...raw };
    if (local && groupPos) {
      const gx = finiteNumber(child.x ?? 0, "group child x");
      const gy = finiteNumber(child.y ?? 0, "group child y");
      const gw = finiteNumber(child.w ?? 0, "group child w");
      const gh = finiteNumber(child.h ?? 0, "group child h");
      child.x = groupPos.left / dimensions.width + gx * groupPos.width / dimensions.width;
      child.y = groupPos.top / dimensions.height + gy * groupPos.height / dimensions.height;
      child.w = gw * groupPos.width / dimensions.width;
      child.h = gh * groupPos.height / dimensions.height;
      child.children_coordinate_space = undefined;
    }
    const childDeck = local && groupPos ? { ...deck, units: "fraction" } : deck;
    return addShape(slide, child, theme, childDeck, dimensions, `${group.object_id || group.name || `group-${index + 1}`}/`, page, geometryBindings);
  });
}

function mimeFor(file) {
  const extension = path.extname(file).toLowerCase();
  return ({ ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml" })[extension] || "application/octet-stream";
}

async function assetPath(raw, assetsDir, field) {
  if (!raw) fail(`${field} is missing`);
  const candidate = path.isAbsolute(String(raw)) ? path.resolve(String(raw)) : path.resolve(assetsDir, String(raw));
  const stat = await fs.stat(candidate).catch(() => null);
  if (!stat || !stat.isFile()) fail(`${field} not found: ${candidate}`);
  return candidate;
}

async function addImage(slide, spec, assetsDir, deck, dimensions, name, fullFrame = false) {
  const source = spec.file ?? spec.path ?? spec.source_path ?? spec.image ?? spec.source?.path ?? spec.source?.file;
  const file = await assetPath(source, assetsDir, `${name}.file`);
  const pos = fullFrame ? { left: 0, top: 0, width: dimensions.width, height: dimensions.height } : position(spec, deck, dimensions);
  const config = {
    alt: String(spec.alt_text ?? spec.alt ?? name),
    fit: spec.fit || "cover",
    position: pos,
  };
  if (path.extname(file).toLowerCase() === ".svg") config.svg = await fs.readFile(file, "utf8");
  else {
    // Artifact Tool's path reference is intended for host-resolved images and
    // can produce zero-byte media during standalone PPTX export. Read local
    // assets as byte-backed images so the generated package contains the
    // actual PNG/JPEG bytes (including alpha for independently replaceable
    // icon assets).
    const bytes = await fs.readFile(file);
    config.blob = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    config.contentType = mimeFor(file);
  }
  if (spec.crop) config.crop = spec.crop;
  if (spec.geometry) config.geometry = shapeGeometry(spec.geometry);
  if (spec.border_radius !== undefined) config.borderRadius = spec.border_radius;
  const image = slide.images.add(config);
  // Image names are used by the semantic inventory/audit.  Artifact Tool
  // does not currently accept `name` in ImageAddOptions, but the returned
  // element exposes the same writable metadata used by inspect().
  try { image.name = String(name); } catch { /* exporter may expose a readonly name */ }
  return image;
}

function cellValue(value, theme, deck, dimensions) {
  if (!value || typeof value !== "object" || !Array.isArray(value.runs)) return value ?? "";
  return { runs: value.runs.map((run) => runInput(run, theme, deck, dimensions)) };
}

function cellStyleValue(style, theme, deck, dimensions) {
  if (!style || typeof style !== "object") return {};
  const output = {};
  if (style.font || style.font_family || theme.font) output.typeface = String(style.font ?? style.font_family ?? theme.font);
  if (style.size !== undefined || style.size_pt !== undefined || style.font_size_pt !== undefined) output.fontSize = fontPixels({ ...style, size: style.size ?? style.size_pt, font_size_pt: style.font_size_pt }, theme, deck, dimensions);
  if (style.color !== undefined) output.color = normaliseColor(style.color);
  if (style.bold !== undefined) output.bold = Boolean(style.bold);
  if (style.italic !== undefined) output.italic = Boolean(style.italic);
  if (style.align) output.alignment = style.align;
  if (style.valign) output.verticalAlignment = style.valign === "center" ? "middle" : style.valign;
  return output;
}

function addTable(slide, spec, theme, deck, dimensions) {
  const rows = Array.isArray(spec.rows) ? spec.rows : [];
  if (!rows.length) fail(`table ${spec.object_id || spec.name || "unnamed"} requires rows`);
  const columns = Number(spec.columns || Math.max(...rows.map((row) => Array.isArray(row) ? row.length : 0)));
  if (!Number.isInteger(columns) || columns <= 0) fail("table columns must be positive");
  const pos = position(spec, deck, dimensions);
  const values = rows.map((row) => Array.from({ length: columns }, (_, index) => cellValue(Array.isArray(row) ? row[index] : "", theme, deck, dimensions)));
  const table = slide.tables.add({
    name: String(spec.object_id || spec.name || "table"),
    rows: rows.length,
    columns,
    left: pos.left,
    top: pos.top,
    width: pos.width,
    height: pos.height,
    values,
  });
  table.styleOptions = { headerRow: Boolean(spec.header_fill || spec.header_bold), bandedRows: Boolean(spec.banded_rows) };
  const widths = Array.isArray(spec.column_widths) ? spec.column_widths : [];
  if (widths.length) {
    table.columnWidths = widths.map((raw) => (deck.units === "px" ? finiteNumber(raw, "column_width") / positiveNumber(deck.ref_width ?? deck.reference_width ?? dimensions.width, "ref_width") * dimensions.width : finiteNumber(raw, "column_width") * dimensions.width));
  }
  const rowHeights = Array.isArray(spec.row_heights) ? spec.row_heights : [];
  rowHeights.forEach((raw, index) => {
    if (index < table.rows.length) table.rows[index].height = deck.units === "px" ? finiteNumber(raw, "row_height") / positiveNumber(deck.ref_height ?? deck.reference_height ?? dimensions.height, "ref_height") * dimensions.height : finiteNumber(raw, "row_height") * dimensions.height;
  });
  const styles = spec.cell_styles && typeof spec.cell_styles === "object" ? spec.cell_styles : {};
  for (let row = 0; row < rows.length; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const cell = table.getCell(row, column);
      const style = styles[`${row},${column}`] || styles[String(row)] || {};
      const fill = style.fill ?? (row === 0 ? spec.header_fill : spec.fill);
      if (fill) cell.fill = fill;
      const textStyle = cellStyleValue({
        ...style,
        bold: style.bold ?? (row === 0 && spec.header_bold !== false),
        color: style.color ?? spec.color ?? theme.text_color,
      }, theme, deck, dimensions);
      if (Object.keys(textStyle).length) cell.text.style = textStyle;
      // Re-apply structured cell runs after the base cell style so local
      // emphasis (colour/weight/size) survives the table-level defaults.
      const rawValue = Array.isArray(rows[row]) ? rows[row][column] : "";
      if (rawValue && typeof rawValue === "object" && Array.isArray(rawValue.runs)) cell.text.set([rawValue.runs.map((run) => runInput(run, theme, deck, dimensions))]);
    }
  }
  for (const merge of spec.merges || []) {
    if (!Array.isArray(merge) || merge.length !== 4) fail("table merge must be [row1,column1,row2,column2]");
    table.merge({ startRow: Number(merge[0]), startColumn: Number(merge[1]), endRow: Number(merge[2]), endColumn: Number(merge[3]) });
  }
  if (spec.border) table.borders.assign({ style: spec.border.style || "solid", fill: spec.border.color || spec.border.fill || "#D9D9D9", width: Number(spec.border.width || 1) });
  return table;
}

function addChart(slide, spec, theme, deck, dimensions) {
  const pos = position(spec, deck, dimensions);
  const type = String(spec.type || "column").toLowerCase();
  const chartType = type === "column" ? "bar" : type;
  const series = spec.series || [];
  const config = {
    position: pos,
    title: spec.title,
    categories: (spec.categories || []).map(String),
    series,
    hasLegend: spec.legend !== undefined ? Boolean(spec.legend) : series.length > 1,
    ...(type === "column" ? { barOptions: { direction: "column" } } : {}),
    ...(spec.colors ? { series: series.map((item, index) => ({ ...item, fill: item.fill || spec.colors[index] })) } : {}),
    ...(spec.data_labels ? { dataLabels: spec.data_labels } : {}),
    ...(spec.x_axis ? { xAxis: spec.x_axis } : {}),
    ...(spec.y_axis ? { yAxis: spec.y_axis } : {}),
    ...(spec.display_blanks_as || spec.displayBlanksAs
      ? { displayBlanksAs: spec.display_blanks_as || spec.displayBlanksAs }
      : {}),
  };
  return slide.charts.add(chartType, config);
}

async function main() {
  const argv = process.argv.slice(2);
  const layoutValue = value(argv, "--layout", argv[0]);
  const outputValue = value(argv, "--output", value(argv, "--out", argv[1]));
  if (!layoutValue || !outputValue) fail("usage: artifact_tool_authoring.mjs --layout DECK.json --output FINAL.pptx");
  const layoutPath = path.resolve(layoutValue);
  const outputPath = path.resolve(outputValue);
  const deck = JSON.parse(await fs.readFile(layoutPath, "utf8"));
  if (!deck || typeof deck !== "object") fail("layout must be a JSON object");
  if (!Array.isArray(deck.slides) || !deck.slides.length) fail("layout must contain at least one slide");
  deck.strict_input = Boolean(deck.strict_input || has(argv, "--strict-input"));
  const geometryResolution = await loadGeometryResolution(argv, deck);
  const dimensions = slideDimensions(deck);
  const theme = deck.theme && typeof deck.theme === "object" ? deck.theme : {};
  const assetsDir = path.resolve(deck.assets_dir || path.dirname(layoutPath));
  const nodeModules = resolveNodeModules(argv);
  const fonts = [];
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--font-path" && argv[index + 1]) {
      const fontPath = path.resolve(argv[++index]);
      const family = argv[index + 1] && !argv[index + 1].startsWith("--") ? argv[++index] : undefined;
      fonts.push({ path: fontPath, family });
    }
  }
  const fontDir = value(argv, "--font-dir");
  if (fontDir) {
    const root = path.resolve(fontDir);
    const files = (await fs.readdir(root, { withFileTypes: true }).catch(() => [])).filter((entry) => entry.isFile() && /\.(ttf|otf|ttc)$/i.test(entry.name)).sort((a, b) => a.name.localeCompare(b.name));
    for (const entry of files) fonts.push({ path: path.join(root, entry.name), family: value(argv, "--font-family", theme.font || deck.font_family || "Microsoft YaHei") });
  }
  const { Presentation, PresentationFile } = await loadArtifactTool(nodeModules);
  const registeredFonts = await registerFonts(fonts, nodeModules);
  const presentation = Presentation.create({ slideSize: { width: dimensions.width, height: dimensions.height } });
  const objectInventory = [];
  const previews = [];
  for (let slideIndex = 0; slideIndex < deck.slides.length; slideIndex += 1) {
    const slideSpec = deck.slides[slideIndex] || {};
    const slide = presentation.slides.add();
    if (slideSpec.background_fill || deck.background_fill) slide.background.fill = slideSpec.background_fill || deck.background_fill;
    if (slideSpec.background) {
      const image = await addImage(slide, { file: slideSpec.background, alt_text: slideSpec.background_alt_text }, assetsDir, deck, dimensions, slideSpec.background_object_id || "background", true);
      objectInventory.push({ slide: slideIndex + 1, object_id: slideSpec.background_object_id || "background", kind: "image", image });
    }
    if (slideSpec.frame) {
      const image = await addImage(slide, { file: slideSpec.frame, alt_text: slideSpec.frame_alt_text }, assetsDir, deck, dimensions, slideSpec.frame_object_id || "frame", true);
      objectInventory.push({ slide: slideIndex + 1, object_id: slideSpec.frame_object_id || "frame", kind: "image", image });
    }
    for (const panel of slideSpec.panels || []) {
      const image = await addImage(slide, panel, assetsDir, deck, dimensions, panel.object_id || panel.panel_id || "panel");
      objectInventory.push({ slide: slideIndex + 1, object_id: panel.object_id || panel.panel_id || "panel", kind: "image", image });
    }
    for (const spec of slideSpec.shapes || []) {
      const binding = geometryBindingFor(geometryResolution.map, slideIndex + 1, spec);
      const shape = addShape(slide, spec, theme, deck, dimensions, "", slideIndex + 1, geometryResolution.map);
      objectInventory.push({ slide: slideIndex + 1, object_id: spec.object_id || spec.name || "shape", kind: "shape", shape, ...(binding ? { geometry_binding: binding } : {}) });
    }
    for (const group of slideSpec.groups || []) {
      const children = addGroupChildren(slide, group, theme, deck, dimensions, slideIndex + 1, geometryResolution.map);
      objectInventory.push({ slide: slideIndex + 1, object_id: group.object_id || group.name || "group", kind: "group", children: children.length });
    }
    for (const spec of slideSpec.tables || []) {
      const table = addTable(slide, spec, theme, deck, dimensions);
      objectInventory.push({ slide: slideIndex + 1, object_id: spec.object_id || spec.name || "table", kind: "table", table });
    }
    for (const spec of slideSpec.charts || []) {
      const chart = addChart(slide, spec, theme, deck, dimensions);
      objectInventory.push({ slide: slideIndex + 1, object_id: spec.object_id || spec.name || "chart", kind: "chart", chart });
    }
    for (const spec of slideSpec.icons || []) {
      const image = await addImage(slide, spec, assetsDir, deck, dimensions, spec.object_id || spec.name || "icon");
      objectInventory.push({ slide: slideIndex + 1, object_id: spec.object_id || spec.name || "icon", kind: "image", image });
    }
    for (const spec of slideSpec.texts || []) {
      const shape = slide.shapes.add({ geometry: "textbox", name: String(spec.object_id || spec.name || "text"), position: position(spec, deck, dimensions), fill: "none", line: { style: "solid", fill: "none", width: 0 } });
      applyText(shape, spec, theme, deck, dimensions);
      objectInventory.push({ slide: slideIndex + 1, object_id: spec.object_id || spec.name || "text", kind: "textbox", shape });
    }
    const notes = slideSpec.speaker_notes ?? slideSpec.notes;
    if (notes) slide.speakerNotes.textFrame.setText(String(notes));
    if (value(argv, "--preview-dir")) {
      const previewDir = path.resolve(value(argv, "--preview-dir"));
      await fs.mkdir(previewDir, { recursive: true });
      const blob = await presentation.export({ slide, format: "png", scale: Number(value(argv, "--preview-scale", "1")) });
      const previewPath = path.join(previewDir, `slide-${String(slideIndex + 1).padStart(2, "0")}.png`);
      await fs.writeFile(previewPath, new Uint8Array(await blob.arrayBuffer()));
      previews.push({ slide: slideIndex + 1, path: previewPath, sha256: sha256(await fs.readFile(previewPath)) });
    }
  }
  const inspect = await presentation.inspect({ kind: "slide,textbox,shape,image,table,chart,notes", maxChars: 200000 });
  const inspectPath = value(argv, "--inspect") ? path.resolve(value(argv, "--inspect")) : `${outputPath}.artifact-tool.inspect.ndjson`;
  await fs.mkdir(path.dirname(inspectPath), { recursive: true });
  await fs.writeFile(inspectPath, inspect.ndjson, "utf8");
  const stagingPath = `${outputPath}.artifact-tool-${process.pid}.tmp`;
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  try {
    const pptx = await PresentationFile.exportPptx(presentation);
    await pptx.save(stagingPath);
    const existing = await fs.stat(outputPath).catch(() => null);
    if (existing && !has(argv, "--overwrite")) fail(`output already exists; pass --overwrite explicitly: ${outputPath}`);
    if (existing) await fs.rm(outputPath, { force: true });
    await fs.rename(stagingPath, outputPath);
  } finally {
    await fs.rm(stagingPath, { force: true }).catch(() => {});
    // Artifact Tool emits a sibling inspect receipt when exporting.  Remove
    // the staging receipt together with the temporary package so a failed or
    // successful run cannot leave untracked intermediate evidence beside the
    // requested deliverable.
    await fs.rm(`${stagingPath}.inspect.ndjson`, { force: true }).catch(() => {});
  }
  const reportPath = value(argv, "--report") ? path.resolve(value(argv, "--report")) : `${outputPath}.artifact-tool.json`;
  const outputBytes = await fs.readFile(outputPath);
  const records = inspect.ndjson.split(/\r?\n/).filter(Boolean).map((line) => { try { return JSON.parse(line); } catch { return null; } }).filter(Boolean);
  const counts = records.reduce((acc, record) => { const kind = record.kind || record.type || "unknown"; acc[kind] = (acc[kind] || 0) + 1; return acc; }, {});
  let packageVersion = null;
  try {
    const packageJson = JSON.parse(await fs.readFile(path.join(nodeModules, "@oai", "artifact-tool", "package.json"), "utf8"));
    packageVersion = packageJson.version || null;
  } catch {
    // The import itself is authoritative; leave the version null if a
    // package manager omits package.json from the runtime mirror.
  }
  const report = {
    schema: "ai-ppt-plus/artifact-tool-authoring/v1",
    valid: true,
    status: "passed",
    backend: "@oai/artifact-tool",
    package_version: packageVersion,
    layout: { path: layoutPath, sha256: sha256(await fs.readFile(layoutPath)), slides: deck.slides.length, slide_size_px: dimensions },
    output: { path: outputPath, sha256: crypto.createHash("sha256").update(outputBytes).digest("hex"), bytes: outputBytes.length },
    inspect: { path: inspectPath, sha256: sha256(await fs.readFile(inspectPath)), record_count: records.length, counts },
    fonts: registeredFonts,
    previews,
    native_object_count: objectInventory.length,
    // The binding map is consumed for both top-level shapes and group
    // children.  Group children are intentionally not flattened into the
    // inventory, so applied_count must come from the validated target map,
    // not only from top-level inventory rows.
    geometry_binding: geometryResolution.report ? { ...geometryResolution.report, applied_count: geometryResolution.targets.length } : null,
    object_inventory: objectInventory.map(({ slide, object_id, kind, children, geometry_binding }) => ({ slide, object_id, kind, ...(children !== undefined ? { children } : {}), ...(geometry_binding ? { geometry_binding } : {}) })),
  };
  await fs.mkdir(path.dirname(reportPath), { recursive: true });
  await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(report));
}

main().catch((error) => {
  console.error(JSON.stringify({ schema: "ai-ppt-plus/artifact-tool-authoring/v1", valid: false, status: "blocked", code: "authoring_failed", message: error.stack || String(error) }));
  process.exitCode = 2;
});
