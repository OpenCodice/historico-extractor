import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import worker from "./worker.js";

function entorno() {
  const objetos = new Map();
  return {
    TOKEN: "secreto",
    objetos,
    CAPTURAS: {
      async put(k, v) { objetos.set(k, v); },
      async get(k) { const v = objetos.get(k); return v ? { body: v, size: v.length } : null; },
      async head(k) { const v = objetos.get(k); return v ? { size: v.length } : null; },
      async list() { return { objects: [...objetos.keys()].map((key) => ({ key })), truncated: false }; },
    },
  };
}
const PDF = new TextEncoder().encode("%PDF-1.4 una ley");
const HUELLA = createHash("sha256").update(PDF).digest("hex");
const pedir = (env, ruta, init) => worker.fetch(new Request(`https://almacen.test${ruta}`, init), env);
const conToken = { Authorization: "Bearer secreto" };

test("guarda un PDF solo con el token y solo bajo su propia huella", async () => {
  const env = entorno();
  assert.equal((await pedir(env, `/${HUELLA}`, { method: "PUT", body: PDF })).status, 401);
  assert.equal((await pedir(env, `/${HUELLA}`, { method: "PUT", body: PDF, headers: { Authorization: "Bearer otro" } })).status, 401);
  assert.equal((await pedir(env, `/${"0".repeat(64)}`, { method: "PUT", body: PDF, headers: conToken })).status, 400);
  const html = new TextEncoder().encode("<html>");
  const huellaHtml = createHash("sha256").update(html).digest("hex");
  assert.equal((await pedir(env, `/${huellaHtml}`, { method: "PUT", body: html, headers: conToken })).status, 400);
  assert.equal(env.objetos.size, 0);
  assert.equal((await pedir(env, `/${HUELLA}`, { method: "PUT", body: PDF, headers: conToken })).status, 201);
  assert.deepEqual([...env.objetos.keys()], [HUELLA]);
});

test("sin token configurado no guarda nada", async () => {
  const env = entorno();
  env.TOKEN = "";
  assert.equal((await pedir(env, `/${HUELLA}`, { method: "PUT", body: PDF, headers: { Authorization: "Bearer " } })).status, 401);
});

test("lee por huella, lista y contesta salud sin token", async () => {
  const env = entorno();
  await pedir(env, `/${HUELLA}`, { method: "PUT", body: PDF, headers: conToken });
  const r = await pedir(env, `/${HUELLA}`);
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("Content-Type"), "application/pdf");
  assert.deepEqual(new Uint8Array(await r.arrayBuffer()), PDF);
  assert.equal((await pedir(env, `/${HUELLA}`, { method: "HEAD" })).status, 200);
  assert.equal((await pedir(env, `/${"1".repeat(64)}`)).status, 404);
  assert.deepEqual(await (await pedir(env, "/lista")).json(), { huellas: [HUELLA], cursor: null });
  assert.equal((await pedir(env, "/salud")).status, 200);
  assert.equal((await pedir(env, "/lista", { method: "DELETE" })).status, 405);
});
