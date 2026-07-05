#!/usr/bin/env node

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";

const DEFAULT_URL = "https://investmentsoc.com/";
const DEFAULT_OUT = "/tmp/nero-ux/investmentsoc-source/summary.json";
const ASSET_RE = /(?:src|href)=["']([^"']+)["']|url\(["']?([^)"']+)["']?\)|(["']?\/?(?:assets|img)\/[^"')\s]+\.(?:js|css|png|jpe?g|webp|svg|gif|woff2?|ico)["']?)/gi;
const SOURCE_RE = /(?:src|href)=["']([^"']+\.(?:js|css))["']/gi;
const HEX_RE = /#[0-9a-fA-F]{3,8}\b/g;

function parseArgs(argv) {
  const args = {
    url: DEFAULT_URL,
    out: DEFAULT_OUT,
    saveRaw: false
  };
  for (let index = 2; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--url") args.url = argv[++index];
    else if (value === "--out") args.out = argv[++index];
    else if (value === "--save-raw") args.saveRaw = true;
    else if (value === "--help") {
      console.log("Usage: node scripts/scrape_investmentsoc_source.mjs [--url URL] [--out FILE] [--save-raw]");
      process.exit(0);
    }
  }
  return args;
}

function absoluteUrl(candidate, base) {
  if (!candidate || candidate.startsWith("data:")) return null;
  return new URL(candidate.replace(/^["']|["']$/g, ""), base).href;
}

function unique(values) {
  return [...new Set(values.filter(Boolean))].sort();
}

async function fetchText(url) {
  const response = await fetch(url, {
    headers: {
      "user-agent": "Nero source inventory bot; design-reference audit"
    }
  });
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.text();
}

function extractSourceUrls(html, baseUrl) {
  const urls = [];
  for (const match of html.matchAll(SOURCE_RE)) {
    const href = absoluteUrl(match[1], baseUrl);
    if (href && new URL(href).hostname === new URL(baseUrl).hostname) urls.push(href);
  }
  return unique(urls);
}

function extractAssetUrls(source, baseUrl) {
  const urls = [];
  for (const match of source.matchAll(ASSET_RE)) {
    const href = absoluteUrl(match[1] || match[2] || match[3], baseUrl);
    if (href) urls.push(href);
  }
  return unique(urls);
}

function analyzeCss(css) {
  return {
    bytes: css.length,
    colors: unique(css.match(HEX_RE) || []).slice(0, 80),
    keyframes: unique([...css.matchAll(/@keyframes\s+([^{\s]+)/g)].map((match) => match[1])),
    animationRules: unique([...css.matchAll(/animation(?:-[a-z-]+)?\s*:\s*([^;}]+)/g)].map((match) => match[1].trim())).slice(0, 40),
    transitionRules: unique([...css.matchAll(/transition(?:-[a-z-]+)?\s*:\s*([^;}]+)/g)].map((match) => match[1].trim())).slice(0, 40),
    classCues: unique([
      ...[...css.matchAll(/\.((?:rounded|backdrop|bg-gradient|from-|to-|via-|shadow|ring|fade|hero|transition|duration|ease)[^,{:\s]*)/g)].map((match) => match[1])
    ]).slice(0, 120)
  };
}

function analyzeJs(js, baseUrl) {
  const imageRefs = extractAssetUrls(js, baseUrl).filter((url) => /\.(png|jpe?g|webp|svg|gif)$/i.test(url));
  return {
    bytes: js.length,
    libraries: {
      framerMotion: /framer-motion|AnimatePresence|whileHover|\bmotion\b/.test(js),
      lucide: /lucide-react|lucide-/.test(js),
      slickCarousel: /slick|react-slick/.test(js)
    },
    motionHints: unique([...js.matchAll(/\b(initial|animate|whileHover|transition|duration|ease|opacity|transform)\b/g)].map((match) => match[1])),
    imageRefs
  };
}

async function main() {
  const args = parseArgs(process.argv);
  const baseUrl = new URL(args.url).origin;
  const outPath = resolve(args.out);
  const rawDir = join(dirname(outPath), "raw");
  const html = await fetchText(args.url);
  const sourceUrls = extractSourceUrls(html, args.url);
  const bundleResults = [];

  await mkdir(dirname(outPath), { recursive: true });
  if (args.saveRaw) {
    await mkdir(rawDir, { recursive: true });
    await writeFile(join(rawDir, "index.html"), html);
  }

  for (const sourceUrl of sourceUrls) {
    const text = await fetchText(sourceUrl);
    const type = sourceUrl.endsWith(".css") ? "css" : "js";
    const filename = sourceUrl.split("/").pop();
    if (args.saveRaw) await writeFile(join(rawDir, filename), text);
    bundleResults.push({
      url: sourceUrl,
      type,
      ...(type === "css" ? analyzeCss(text) : analyzeJs(text, args.url))
    });
  }

  const htmlAssets = extractAssetUrls(html, args.url);
  const bundleAssets = unique(bundleResults.flatMap((bundle) => bundle.imageRefs || []));
  const report = {
    scrapedAt: new Date().toISOString(),
    source: args.url,
    sourceCode: {
      htmlBytes: html.length,
      bundles: sourceUrls,
      rawSaved: args.saveRaw ? rawDir : null
    },
    assets: {
      html: htmlAssets,
      images: unique([...htmlAssets, ...bundleAssets]).filter((url) => /\.(png|jpe?g|webp|svg|gif|ico)$/i.test(url)),
      sameOriginImages: unique([...htmlAssets, ...bundleAssets])
        .filter((url) => new URL(url).origin === baseUrl)
        .filter((url) => /\.(png|jpe?g|webp|svg|gif|ico)$/i.test(url))
    },
    bundles: bundleResults,
    designTakeaways: [
      "Dark #020817/#0A0B0E canvas with Inter Variable typography.",
      "Full-bleed photographic hero sections with black gradient overlays.",
      "Glass panels use white/5 backgrounds, white/10 borders, rounded-2xl/3xl radii, and subtle backdrop blur.",
      "Motion is understated: fade-in text, transform/opacity reveals, hover translations/scales, and short 150-300ms transitions.",
      "Primary actions use white/90 or indigo buttons with rounded-xl corners."
    ]
  };

  await writeFile(outPath, `${JSON.stringify(report, null, 2)}\n`);
  console.log(`Wrote ${outPath}`);
  console.log(`Found ${report.assets.sameOriginImages.length} same-origin images and ${sourceUrls.length} local bundles.`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
