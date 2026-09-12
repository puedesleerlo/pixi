// Fails when a t("key") used in the source is missing from messages/en.json or messages/es.json, when the two
// languages disagree on keys, or when a file calls t() without a resolvable namespace. Run: node scripts/check-i18n.mjs
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const langs = ["en", "es"];
const messages = Object.fromEntries(langs.map((l) => [l, JSON.parse(readFileSync(join(root, "messages", `${l}.json`), "utf8"))]));

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* walk(p);
    else if (/\.(tsx?|jsx?)$/.test(name)) yield p;
  }
}
const lookup = (lang, ns, key) => key.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), messages[lang]?.[ns]);

const problems = [];
let checked = 0;
for (const file of walk(join(root, "src"))) {
  const src = readFileSync(file, "utf8");
  const rel = relative(root, file);
  // const t = useTranslations("ns")  /  const tx = useTranslations("ns")  /  getTranslations("ns")
  const scopes = [...src.matchAll(/const\s+(\w+)\s*=\s*(?:use|get)Translations\(\s*["'`]([\w.-]+)["'`]\s*\)/g)].map((m) => ({ fn: m[1], ns: m[2] }));
  if (!scopes.length) continue;
  for (const { fn, ns } of scopes) {
    const re = new RegExp(`(?<![\\w.])${fn}\\(\\s*["'\`]([\\w.-]+)["'\`]`, "g");
    for (const m of src.matchAll(re)) {
      checked++;
      for (const lang of langs) {
        if (lookup(lang, ns, m[1]) === undefined) problems.push(`${rel}: t("${m[1]}") not found under "${ns}" in ${lang}.json`);
      }
    }
  }
}
// language parity
const flat = (o, prefix = "") => Object.entries(o).flatMap(([k, v]) => (v && typeof v === "object" ? flat(v, `${prefix}${k}.`) : [`${prefix}${k}`]));
const en = new Set(flat(messages.en)), es = new Set(flat(messages.es));
for (const k of en) if (!es.has(k)) problems.push(`es.json is missing "${k}"`);
for (const k of es) if (!en.has(k)) problems.push(`en.json is missing "${k}"`);

if (problems.length) {
  console.error(`i18n check: ${problems.length} problem(s) after checking ${checked} t() calls`);
  for (const p of problems.slice(0, 40)) console.error("  " + p);
  process.exit(1);
}
console.log(`i18n check: ${checked} t() calls resolve in en and es; ${en.size} keys in parity`);
