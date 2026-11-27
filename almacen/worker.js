// El almacén de los PDF archivados de cada ley: la copia propia de las
// capturas que historico-extractor baja de Wayback, para no depender de que
// Wayback las siga entregando.
//
// Cada PDF se guarda por su sha256, el mismo que lleva el manifiesto de su
// documento y el trailer `Fuente-Sha256` de su commit en OpenCodice/historico.
//
// - GET|HEAD /{sha256}: el PDF. Público.
// - GET /lista?cursor=…: las huellas guardadas, de mil en mil. Público.
// - PUT /{sha256}: guarda un PDF. Pide el token, y el cuerpo tiene que ser un
//   PDF con esa huella: con el token no se puede guardar otra cosa.
// - GET /salud.

const HUELLA = /^\/([0-9a-f]{64})$/;
export const MAX_BYTES = 95 * 1024 * 1024;

const json = (datos, status = 200) => Response.json(datos, { status, headers: { "Access-Control-Allow-Origin": "*" } });

async function sha256(bytes) {
  const d = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Comparación en tiempo constante: el token no se filtra por lo que tarda.
function igual(a, b) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

async function guardar(request, env, clave) {
  const token = (request.headers.get("Authorization") ?? "").replace(/^Bearer /, "");
  if (!env.TOKEN || !igual(token, env.TOKEN)) return json({ error: "no autorizado" }, 401);
  if (Number(request.headers.get("Content-Length") ?? 0) > MAX_BYTES) return json({ error: "demasiado grande" }, 413);
  const cuerpo = new Uint8Array(await request.arrayBuffer());
  if (cuerpo.length > MAX_BYTES) return json({ error: "demasiado grande" }, 413);
  if (new TextDecoder().decode(cuerpo.subarray(0, 4)) !== "%PDF") return json({ error: "no es un PDF" }, 400);
  if ((await sha256(cuerpo)) !== clave) return json({ error: "el contenido no tiene esa huella" }, 400);
  await env.CAPTURAS.put(clave, cuerpo, { httpMetadata: { contentType: "application/pdf" } });
  return json({ guardada: clave, bytes: cuerpo.length }, 201);
}

async function leer(request, env, clave) {
  const objeto = request.method === "HEAD" ? await env.CAPTURAS.head(clave) : await env.CAPTURAS.get(clave);
  if (!objeto) return json({ error: "no está en el almacén" }, 404);
  return new Response(request.method === "HEAD" ? null : objeto.body, {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Length": String(objeto.size),
      // El contenido de una huella no cambia nunca.
      "Cache-Control": "public, max-age=31536000, immutable",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const m = HUELLA.exec(url.pathname);
    if (m && request.method === "PUT") return guardar(request, env, m[1]);
    if (m && (request.method === "GET" || request.method === "HEAD")) return leer(request, env, m[1]);
    if (request.method !== "GET") return json({ error: "método no admitido" }, 405);
    if (url.pathname === "/lista") {
      const r = await env.CAPTURAS.list({ limit: 1000, cursor: url.searchParams.get("cursor") ?? undefined });
      return json({ huellas: r.objects.map((o) => o.key), cursor: r.truncated ? r.cursor : null });
    }
    if (url.pathname === "/salud") return json({ ok: true });
    return json({ error: "no encontrado", uso: "GET /{sha256} entrega el PDF con esa huella; GET /lista, las que hay." }, 404);
  },
};
