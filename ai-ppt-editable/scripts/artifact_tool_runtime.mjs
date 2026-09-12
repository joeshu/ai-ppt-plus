import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

function argumentValue(argv, name) {
  const index = argv.indexOf(name);
  return index >= 0 ? argv[index + 1] : undefined;
}

export function resolveNodeModules(argv = process.argv.slice(2)) {
  const explicit = argumentValue(argv, "--node-modules");
  const candidates = [explicit, process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES,
    process.env.RUNTIME_NODE_MODULES, path.resolve(process.cwd(), "node_modules")];
  const result = candidates.find((candidate) => candidate && fs.existsSync(path.join(candidate, "@oai", "artifact-tool")));
  if (!result) throw new Error("@oai/artifact-tool runtime not found; pass --node-modules or set CODEX_PRIMARY_RUNTIME_NODE_MODULES");
  return path.resolve(result);
}

export function runtimeRequire(nodeModules) {
  return createRequire(path.join(nodeModules, ".ai-ppt-plus-runtime.cjs"));
}

export async function loadArtifactTool(nodeModules) {
  const require = runtimeRequire(nodeModules);
  const artifactPath = require.resolve("@oai/artifact-tool");
  return import(pathToFileURL(artifactPath).href);
}

export async function registerFonts(fonts, nodeModules) {
  const require = runtimeRequire(nodeModules);
  const canvas = require("@napi-rs/canvas");
  const registrations = [];
  for (const item of fonts ?? []) {
    const fontPath = typeof item === "string" ? item : item?.path;
    const family = typeof item === "string" ? undefined : item?.family;
    if (!fontPath || !fs.existsSync(fontPath)) throw new Error(`font file not found: ${fontPath}`);
    const resolvedFamily = family || path.basename(fontPath).replace(/\.(ttf|otf|ttc)$/i, "");
    if (!canvas.GlobalFonts.registerFromPath(fontPath, resolvedFamily)) {
      throw new Error(`GlobalFonts registration failed for ${resolvedFamily}: ${fontPath}`);
    }
    registrations.push({ family: resolvedFamily, path: path.resolve(fontPath) });
  }
  const skiaPath = path.join(nodeModules, "@oai", "artifact-tool", "node_modules", "skia-canvas", "lib", "index.mjs");
  if (registrations.length && !fs.existsSync(skiaPath)) throw new Error(`artifact-tool skia FontLibrary not found: ${skiaPath}`);
  if (registrations.length) {
    const { FontLibrary } = await import(pathToFileURL(skiaPath).href);
    for (const item of registrations) FontLibrary.use(item.family, item.path);
  }
  return registrations;
}

export function parseFontArgs(argv = process.argv.slice(2)) {
  const fonts = [];
  for (let i = 0; i < argv.length; i += 1) if (argv[i] === "--font-path" && argv[i + 1]) {
    const family = argv[i + 2] && !argv[i + 2].startsWith("--") ? argv[++i] : undefined;
    fonts.push({ path: argv[++i], family });
  }
  return fonts;
}

export function resolveFontEntries(argv = process.argv.slice(2), defaultPath, defaultFamily) {
  const parsed = parseFontArgs(argv);
  if (parsed.length) return parsed.map((item) => ({ path: item.path, family: item.family || defaultFamily }));
  return defaultPath ? [{ path: defaultPath, family: defaultFamily }] : [];
}
