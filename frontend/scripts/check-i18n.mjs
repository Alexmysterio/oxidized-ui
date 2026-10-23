import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const localesDir = path.join(root, "public", "locales");
const srcDir = path.join(root, "src");

function flatten(value, prefix = "", output = new Map()) {
  for (const [key, child] of Object.entries(value)) {
    const full = prefix ? `${prefix}.${key}` : key;
    if (child && typeof child === "object" && !Array.isArray(child)) flatten(child, full, output);
    else output.set(full, child);
  }
  return output;
}

function files(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) return files(full);
    return /\.(ts|tsx)$/.test(entry.name) ? [full] : [];
  });
}

const localeFiles = fs.readdirSync(localesDir).filter((name) => name.endsWith(".json")).sort();
if (localeFiles.length < 2) throw new Error("At least two locale files are required");
const locales = Object.fromEntries(
  localeFiles.map((file) => [path.basename(file, ".json"), flatten(JSON.parse(fs.readFileSync(path.join(localesDir, file), "utf8")))]),
);
const [primary, ...others] = Object.keys(locales);
const failures = [];

for (const language of others) {
  const missing = [...locales[primary].keys()].filter((key) => !locales[language].has(key));
  const extra = [...locales[language].keys()].filter((key) => !locales[primary].has(key));
  if (missing.length) failures.push(`${language}: missing keys: ${missing.slice(0, 30).join(", ")}`);
  if (extra.length) failures.push(`${language}: extra keys: ${extra.slice(0, 30).join(", ")}`);
}

const source = files(srcDir)
  .map((file) => fs.readFileSync(file, "utf8"))
  .join("\n");
const used = new Set();
for (const match of source.matchAll(/\bt\(\s*["']([^"']+)["']/g)) used.add(match[1]);
for (const match of source.matchAll(/\bi18n\.t\(\s*["']([^"']+)["']/g)) used.add(match[1]);
for (const match of source.matchAll(/usePageTitle\(\s*["']([^"']+)["']/g)) used.add(match[1]);

// These namespaces are built from runtime codes and cannot be enumerated statically.
const dynamicPrefixes = [
  "audit.actions.",
  "config.revisionStatus.",
  "config.tabs.",
  "errors.",
  "jobs.",
  "languages.",
  "logs.",
  "nav.",
  "nodeStatus.",
  "oxidized.",
  "roles.",
  "status.",
  "theme.",
  "warnings.",
];
const isDynamic = (key) => dynamicPrefixes.some((prefix) => key.startsWith(prefix)) || /^config\.[a-z]+Description$/.test(key);

const primaryKeys = locales[primary];
const missingUsed = [...used].filter((key) => !primaryKeys.has(key) && !isDynamic(key));
if (missingUsed.length) failures.push(`${primary}: keys used in code but missing: ${missingUsed.join(", ")}`);

const unused = [...primaryKeys.keys()].filter((key) => !used.has(key) && !isDynamic(key));
if (unused.length) failures.push(`${primary}: unused keys: ${unused.join(", ")}`);

// Backend error and audit catalogs are part of the public contract.
const backend = path.resolve(root, "..", "backend", "app", "data");
const errorCodes = Object.keys(JSON.parse(fs.readFileSync(path.join(backend, "error_codes.json"), "utf8")));
for (const code of errorCodes) {
  if (!primaryKeys.has(`errors.${code}`)) failures.push(`${primary}: missing error translation errors.${code}`);
}
const auditCodes = JSON.parse(fs.readFileSync(path.join(backend, "audit_actions.json"), "utf8"));
for (const code of auditCodes) {
  if (!primaryKeys.has(`audit.actions.${code}`)) failures.push(`${primary}: missing audit translation audit.actions.${code}`);
}

if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log(`i18n OK: ${localeFiles.length} languages, ${primaryKeys.size} keys, ${used.size} direct references.`);
