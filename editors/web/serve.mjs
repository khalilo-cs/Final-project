// خادم محلي بسيط لمجلد dist (WebAssembly يتطلب http لا file://).
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const dist = join(dirname(fileURLToPath(import.meta.url)), "dist");
const port = Number(process.env.PORT || process.argv[2] || 8080);
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".wasm": "application/wasm", ".json": "application/json" };

export function serve(p = port) {
  const server = createServer(async (req, res) => {
    const path = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const file = normalize(join(dist, path === "/" ? "index.html" : path));
    if (!file.startsWith(dist)) { res.writeHead(403).end(); return; }
    try {
      const body = await readFile(file);
      res.writeHead(200, { "content-type": types[extname(file)] || "application/octet-stream" }).end(body);
    } catch {
      res.writeHead(404).end("not found");
    }
  });
  return new Promise((r) => server.listen(p, "127.0.0.1", () => r(server)));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  await serve();
  console.log(`ساحة ضاد تعمل على http://127.0.0.1:${port}`);
}
