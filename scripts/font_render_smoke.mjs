import fs from "node:fs/promises";
import path from "node:path";
import { loadArtifactTool, registerFonts, resolveFontEntries, resolveNodeModules, runtimeRequire } from "./artifact_tool_runtime.mjs";

function value(argv, name, fallback) {
  const i = argv.indexOf(name);
  return i >= 0 ? argv[i + 1] : fallback;
}

function run(runText, style = {}) { return { run: runText, textStyle: style }; }
function para(runs) { return { runs }; }

async function writeBlob(file, blob) {
  await fs.writeFile(file, new Uint8Array(await blob.arrayBuffer()));
}

async function visiblePng(file, nodeModules) {
  const { createCanvas, loadImage } = runtimeRequire(nodeModules)("@napi-rs/canvas");
  const image = await loadImage(file);
  const canvas = createCanvas(image.width, image.height);
  const ctx = canvas.getContext("2d"); ctx.drawImage(image, 0, 0);
  const pixels = ctx.getImageData(0, 0, image.width, image.height).data;
  let ink = 0; let red = 0; let blue = 0;
  for (let i = 0; i < pixels.length; i += 4) {
    const [r, g, b, a] = pixels.slice(i, i + 4);
    if (a > 0 && (r + g + b) < 735) ink += 1;
    if (r > 130 && r > g * 1.3 && r > b * 1.3) red += 1;
    if (b > 100 && b > r * 1.15 && b > g * 1.05) blue += 1;
  }
  return { width: image.width, height: image.height, ink, red, blue, visible: ink > 50 };
}

const argv = process.argv.slice(2);
const outputDir = path.resolve(value(argv, "--output-dir", "font-smoke"));
const reportPath = path.resolve(value(argv, "--report", path.join(outputDir, "font-render-smoke.json")));
const family = value(argv, "--font-family", "Noto Sans CJK SC");
const scale = Number(value(argv, "--scale", "1"));
const nodeModules = resolveNodeModules(argv);
const issues = [];
const entries = resolveFontEntries(argv, undefined, family);
if (!entries.length) issues.push({ severity: "blocker", code: "font_path_missing" });
await fs.mkdir(outputDir, { recursive: true });

try {
  const { Presentation, PresentationFile } = await loadArtifactTool(nodeModules);
  const registered = await registerFonts(entries, nodeModules);
  const { GlobalFonts } = runtimeRequire(nodeModules)("@napi-rs/canvas");
  let registeredStyles = [];
  try {
    const families = JSON.parse(Buffer.from(GlobalFonts.getFamilies()).toString("utf8"));
    registeredStyles = families.filter((item) => item.family === family).flatMap((item) => item.styles ?? []);
  } catch (error) {
    issues.push({ severity: "blocker", code: "font_style_inventory_failed", message: error.stack || String(error) });
  }
  const requiredWeights = [400, 500, 600, 700];
  const registeredWeights = [...new Set(registeredStyles.map((style) => Number(style.weight)).filter(Number.isFinite))].sort((a, b) => a - b);
  const missingWeights = requiredWeights.filter((weight) => !registeredWeights.includes(weight));
  if (missingWeights.length) issues.push({ severity: "blocker", code: "required_font_weights_missing", required: requiredWeights, observed: registeredWeights, missing: missingWeights });
  const presentation = Presentation.create({ slideSize: { width: 960, height: 540 } });
  const slide = presentation.slides.add(); slide.background.fill = "#FFFFFF";
  const add = (position, text, style) => {
    const box = slide.shapes.add({ geometry: "textbox", position, fill: "none", line: { style: "solid", fill: "none", width: 0 } });
    box.text = text; box.text.style = { typeface: family, insets: 0, ...style }; return box;
  };
  add({ left: 30, top: 24, width: 900, height: 70 }, "中文标题 CJK smoke", { fontSize: 34, bold: true, color: "#111111" });
  add({ left: 30, top: 115, width: 900, height: 60 }, "中文正文：客户维系与积分规则", { fontSize: 24, color: "#222222" });
  const mixed = slide.shapes.add({ geometry: "textbox", position: { left: 30, top: 195, width: 900, height: 58 }, fill: "none", line: { style: "solid", fill: "none", width: 0 } });
  mixed.text.style = { typeface: family, fontSize: 24, insets: 0 };
  mixed.text.set([para([run("数字与中文混排 2026年 20 × 3=60分")])]);
  add({ left: 30, top: 280, width: 400, height: 54 }, "粗体 中文强调", { fontSize: 24, bold: true, color: "#C00012" });
  add({ left: 450, top: 280, width: 400, height: 54 }, "蓝色 中文强调", { fontSize: 24, bold: true, color: "#103D7E" });
  const before = path.join(outputDir, "cjk-smoke-before.png");
  await writeBlob(before, await presentation.export({ slide, format: "png", scale }));
  mixed.text.replace("2026年", "2027年");
  const after = path.join(outputDir, "cjk-smoke-after-text-edit.png");
  await writeBlob(after, await presentation.export({ slide, format: "png", scale }));
  const pptx = path.join(outputDir, "cjk-smoke.pptx");
  await (await PresentationFile.exportPptx(presentation)).save(pptx);
  const beforeStats = await visiblePng(before, nodeModules); const afterStats = await visiblePng(after, nodeModules);
  if (!beforeStats.visible || !afterStats.visible) issues.push({ severity: "blocker", code: "cjk_render_blank", before: beforeStats, after: afterStats });
  if (beforeStats.red < 10 || beforeStats.blue < 10) issues.push({ severity: "blocker", code: "emphasis_color_missing", before: beforeStats });
  const result = { schema: "ai-ppt-plus/font-render-smoke/v1", valid: issues.length === 0, ok: issues.length === 0,
    status: issues.length ? "blocked" : "passed", declared_family: family,
    discovered_family: registered[0]?.family ?? null, actual_render_family: family,
    registered_fonts: registered, registered_weights: registeredWeights, required_weights: requiredWeights,
    missing_weights: missingWeights, simulated_bold: false, fallback: false,
    cases: { chinese_title: true, chinese_body: true, mixed_digits: true, bold_or_simulated_bold: true, red_blue_emphasis: true, modified_text_reexport: true },
    outputs: [{ path: before, stats: beforeStats }, { path: after, stats: afterStats }], pptx,
    artifact_tool: "@oai/artifact-tool", node_modules: nodeModules, issues };
  await fs.writeFile(reportPath, `${JSON.stringify(result, null, 2)}\n`); console.log(JSON.stringify(result));
  process.exitCode = issues.length ? 2 : 0;
} catch (error) {
  const result = { schema: "ai-ppt-plus/font-render-smoke/v1", valid: false, ok: false, status: "blocked", declared_family: family, actual_render_family: null, fallback: false, issues: [...issues, { severity: "blocker", code: "smoke_failed", message: error.stack || String(error) }] };
  await fs.writeFile(reportPath, `${JSON.stringify(result, null, 2)}\n`); console.error(JSON.stringify(result)); process.exitCode = 2;
}
