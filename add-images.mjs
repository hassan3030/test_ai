// Usage: node add-images.mjs
// Node 18+. Put your JSON in products.json (the { "data": [...] } shape).
import fs from "node:fs/promises";

const CFG = {
  directusUrl: process.env.DIRECTUS_URL,       // e.g. https://cms.example.com
  directusToken: process.env.DIRECTUS_TOKEN,   // static token with files + items write access
  collection: process.env.COLLECTION || "products",
  imageField: process.env.IMAGE_FIELD || "image", // file (m2o) field on the collection
  folderId: process.env.FOLDER_ID || null,        // optional Directus folder uuid
  googleKey: process.env.GOOGLE_API_KEY,          // Google Programmable Search API key
  googleCx: process.env.GOOGLE_CX,                // search engine id (enable Image search)
  dryRun: process.env.DRY_RUN === "1",            // only produce the JSON, skip Directus
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function buildQuery(p) {
  const brand = p.brand_id?.name ?? "";
  const sub = p.subcategory_id?.name ?? "";
  return `${brand} ${p.name} ${sub} product photo`.replace(/\s+/g, " ").trim();
}

async function findImageUrls(query) {
  const u = new URL("https://www.googleapis.com/customsearch/v1");
  u.search = new URLSearchParams({
    key: CFG.googleKey,
    cx: CFG.googleCx,
    q: query,
    searchType: "image",
    num: "5",
    imgSize: "large",
    safe: "active",
  });
  const res = await fetch(u);
  if (!res.ok) throw new Error(`Search failed ${res.status}: ${await res.text()}`);
  const json = await res.json();
  return (json.items ?? []).map((i) => i.link).filter((l) => /^https:\/\//.test(l));
}

async function importToDirectus(url, title) {
  const res = await fetch(`${CFG.directusUrl}/files/import`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${CFG.directusToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      url,
      data: { title, ...(CFG.folderId && { folder: CFG.folderId }) },
    }),
  });
  if (!res.ok) throw new Error(`Import failed ${res.status}`);
  return (await res.json()).data.id;
}

async function linkImage(itemId, fileId) {
  const res = await fetch(`${CFG.directusUrl}/items/${CFG.collection}/${itemId}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${CFG.directusToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ [CFG.imageField]: fileId }),
  });
  if (!res.ok) throw new Error(`Patch failed ${res.status}`);
}

const input = JSON.parse(await fs.readFile("products.json", "utf8"));
const results = [];

for (const p of input.data) {
  const out = { ...p, image_source_url: null, image: null };
  try {
    const candidates = await findImageUrls(buildQuery(p));
    out.image_source_url = candidates[0] ?? null;

    if (!CFG.dryRun) {
      // try candidates until one imports successfully (some hosts block hotlinking)
      for (const url of candidates) {
        try {
          const fileId = await importToDirectus(url, p.name);
          await linkImage(p.id, fileId);
          out.image = fileId;
          out.image_source_url = url;
          break;
        } catch (e) {
          console.warn(`  candidate failed for ${p.name}: ${e.message}`);
        }
      }
    }
    console.log(`${out.image || out.image_source_url ? "✓" : "✗"} ${p.name}`);
  } catch (e) {
    console.error(`✗ ${p.name}: ${e.message}`);
  }
  results.push(out);
  await sleep(300); // be gentle with rate limits
}

await fs.writeFile("products-with-images.json", JSON.stringify({ data: results }, null, 2));
console.log("Saved products-with-images.json");
