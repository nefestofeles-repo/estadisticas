// API de mensajes, reacciones y fotos. Antes pasa por functions/_middleware.js, que deja en data.usuario
// quién es ({ quien, nombre, google, admin }); los invitados con enlace solo pueden leer.
// Datos: base de datos D1 (env.DB, esquema en social/esquema.sql) y fotos en el almacén KV (env.FOTOS).

import { palabrasProhibidas } from '../../social/filtro.js';

const EMOJIS = ['👏', '🔥', '💪', '❤️', '😮', '😂'];
// partido:<grupo>-<jornada>, grada:<grupo>-<jornada> o jugadora:<nombre-en-minusculas-con-guiones>
const HILO = /^(?:(partido|grada):\d+-\d+|jugadora:[a-z#-]{3,80})$/;
const MAX_TEXTO = 1000, MAX_FOTO = 3 * 1024 * 1024, MAX_MENSAJES = 300;

const json = (datos, status = 200) =>
  new Response(JSON.stringify(datos), { status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
const error = (texto, status) => json({ error: texto }, status);
const cambia = (db, hilo) => db.prepare('INSERT INTO hilos (hilo, version) VALUES (?1, ?2) ON CONFLICT (hilo) DO UPDATE SET version = ?2')
  .bind(hilo, Date.now());

export async function onRequest({ request, env, data, params }) {
  const yo = data.usuario;
  const { DB, FOTOS } = env;
  if (!DB || !FOTOS) return error('Los mensajes todavía no están activados.', 503);
  if (request.method !== 'GET' && request.headers.get('Origin') !== new URL(request.url).origin) return error('Origen no permitido', 403);
  const [ruta, ...resto] = params.ruta || [];
  const arg = resto.join('/');
  const ruta2 = `${request.method} ${ruta}`;
  try {
    if (ruta2 === 'GET yo') return json({ nombre: yo.nombre, puedeEscribir: yo.google, admin: yo.admin, emojis: EMOJIS });
    if (ruta2 === 'GET hilo') return await leeHilo(DB, yo, arg, new URL(request.url).searchParams.get('version'));
    if (ruta2 === 'GET foto') return await daFoto(FOTOS, arg);
    if (ruta2 === 'GET novedades') return await novedades(DB, yo);
    if (ruta2 === 'POST visto') return await marcaVisto(DB, yo, await request.json());
    if (!yo.google) return error('Para escribir o reaccionar hay que entrar con una cuenta de Google.', 403);
    if (ruta2 === 'POST hilo') return await escribe(DB, FOTOS, yo, arg, await request.formData());
    if (ruta2 === 'DELETE mensaje') return await borra(DB, FOTOS, yo, Number(arg));
    if (ruta2 === 'POST reaccion') return await reacciona(DB, yo, await request.json());
    return error('No existe', 404);
  } catch (e) {
    console.error(e);
    return error('Algo ha fallado; vuelve a intentarlo.', 500);
  }
}

// Reacciones agrupadas por objetivo: { objetivo: [{ emoji, n, mia, quienes }] }
function agrupaReacciones(filas, yo) {
  const por = {};
  for (const r of filas) {
    const lista = por[r.objetivo] ||= [];
    let e = lista.find(x => x.emoji === r.emoji);
    if (!e) lista.push(e = { emoji: r.emoji, n: 0, mia: false, quienes: [] });
    e.n++; e.quienes.push(r.nombre);
    if (r.autor === yo.quien) e.mia = true;
  }
  for (const lista of Object.values(por)) lista.sort((a, b) => EMOJIS.indexOf(a.emoji) - EMOJIS.indexOf(b.emoji));
  return por;
}

async function leeHilo(db, yo, hilo, version) {
  if (!HILO.test(hilo)) return error('Hilo no válido', 400);
  const actual = (await db.prepare('SELECT version FROM hilos WHERE hilo = ?').bind(hilo).first('version')) || 0;
  if (version && Number(version) === actual) return json({ version: actual, sinCambios: true });
  const { results: mensajes } = await db.prepare(
    'SELECT * FROM (SELECT id, autor, nombre, texto, foto, creado FROM mensajes WHERE hilo = ? ORDER BY id DESC LIMIT ?) ORDER BY id')
    .bind(hilo, MAX_MENSAJES).all();
  const objetivos = [`hilo:${hilo}`, ...mensajes.map(m => `mensaje:${m.id}`)];
  const { results: filas } = await db.prepare(
    `SELECT objetivo, autor, nombre, emoji FROM reacciones WHERE objetivo IN (SELECT value FROM json_each(?))`)
    .bind(JSON.stringify(objetivos)).all();
  const reacciones = agrupaReacciones(filas, yo);
  return json({
    version: actual,
    reacciones: reacciones[`hilo:${hilo}`] || [],
    mensajes: mensajes.map(({ autor, ...m }) => ({
      ...m, propio: autor === yo.quien, puedeBorrar: autor === yo.quien || yo.admin, reacciones: reacciones[`mensaje:${m.id}`] || [],
    })),
  });
}

// Solo JPEG o WebP (el navegador las reduce y les quita los datos de ubicación antes de enviarlas)
const esImagen = b => (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) ? 'image/jpeg'
  : (String.fromCharCode(...b.slice(0, 4)) === 'RIFF' && String.fromCharCode(...b.slice(8, 12)) === 'WEBP') ? 'image/webp' : null;

async function escribe(db, fotos, yo, hilo, form) {
  if (!HILO.test(hilo)) return error('Hilo no válido', 400);
  const texto = String(form.get('texto') || '').trim().slice(0, MAX_TEXTO);
  if (palabrasProhibidas(texto)) return error('No se ha publicado: el mensaje tiene palabras que no se permiten en esta web.', 422);
  const archivo = form.get('foto');
  let foto = null;
  if (archivo && typeof archivo !== 'string' && archivo.size) {
    if (archivo.size > MAX_FOTO) return error('La foto es demasiado grande.', 413);
    const bytes = new Uint8Array(await archivo.arrayBuffer());
    const tipo = esImagen(bytes);
    if (!tipo) return error('Solo se pueden subir fotos.', 415);
    foto = [...crypto.getRandomValues(new Uint8Array(16))].map(b => b.toString(16).padStart(2, '0')).join('');
    await fotos.put(foto, bytes, { metadata: { tipo, autor: yo.quien } });
  }
  if (!texto && !foto) return error('El mensaje está vacío.', 400);
  const ahora = Date.now();
  const [r] = await db.batch([
    db.prepare('INSERT INTO mensajes (hilo, autor, nombre, texto, foto, creado) VALUES (?, ?, ?, ?, ?, ?) RETURNING id')
      .bind(hilo, yo.quien, yo.nombre, texto, foto, ahora),
    cambia(db, hilo),
  ]);
  const id = r.results[0].id;
  // Lo propio cuenta como visto
  await db.prepare('INSERT INTO visto (quien, hilo, ultimo) VALUES (?1, ?2, ?3) ON CONFLICT (quien, hilo) DO UPDATE SET ultimo = max(ultimo, ?3)')
    .bind(yo.quien, hilo, id).run();
  return json({ ok: true, id });
}

async function borra(db, fotos, yo, id) {
  const m = await db.prepare('SELECT hilo, autor, foto FROM mensajes WHERE id = ?').bind(id).first();
  if (!m) return error('Ese mensaje ya no existe.', 404);
  if (m.autor !== yo.quien && !yo.admin) return error('Solo puedes borrar tus mensajes.', 403);
  await db.batch([
    db.prepare('DELETE FROM mensajes WHERE id = ?').bind(id),
    db.prepare('DELETE FROM reacciones WHERE objetivo = ?').bind(`mensaje:${id}`),
    cambia(db, m.hilo),
  ]);
  if (m.foto) await fotos.delete(m.foto);
  return json({ ok: true });
}

// Pone o quita la reacción (mismo emoji otra vez = quitarla)
async function reacciona(db, yo, { objetivo, emoji }) {
  if (!EMOJIS.includes(emoji)) return error('Reacción no válida', 400);
  let hilo;
  if (/^hilo:/.test(objetivo || '') && HILO.test(objetivo.slice(5))) hilo = objetivo.slice(5);
  else if (/^mensaje:\d+$/.test(objetivo || '')) hilo = await db.prepare('SELECT hilo FROM mensajes WHERE id = ?').bind(Number(objetivo.slice(8))).first('hilo');
  if (!hilo) return error('No existe', 404);
  const borradas = await db.prepare('DELETE FROM reacciones WHERE objetivo = ? AND autor = ? AND emoji = ?').bind(objetivo, yo.quien, emoji).run();
  if (!borradas.meta.changes)
    await db.prepare('INSERT INTO reacciones (objetivo, autor, nombre, emoji) VALUES (?, ?, ?, ?)').bind(objetivo, yo.quien, yo.nombre, emoji).run();
  await cambia(db, hilo).run();
  return json({ ok: true });
}

async function daFoto(fotos, clave) {
  if (!/^[0-9a-f]{32}$/.test(clave)) return error('No existe', 404);
  const { value, metadata } = await fotos.getWithMetadata(clave, 'arrayBuffer');
  if (!value) return error('No existe', 404);
  return new Response(value, { headers: { 'Content-Type': metadata?.tipo || 'image/jpeg', 'Cache-Control': 'private, max-age=31536000, immutable' } });
}

// Mensajes de otros sin ver, por hilo
async function novedades(db, yo) {
  const { results } = await db.prepare(
    `SELECT m.hilo, COUNT(*) AS n FROM mensajes m LEFT JOIN visto v ON v.quien = ?1 AND v.hilo = m.hilo
     WHERE m.id > COALESCE(v.ultimo, 0) AND m.autor != ?1 GROUP BY m.hilo`).bind(yo.quien).all();
  return json({ hilos: Object.fromEntries(results.map(r => [r.hilo, r.n])) });
}

async function marcaVisto(db, yo, { hilo, ultimo }) {
  if (!HILO.test(hilo || '') || !Number.isInteger(ultimo)) return error('Datos no válidos', 400);
  await db.prepare('INSERT INTO visto (quien, hilo, ultimo) VALUES (?1, ?2, ?3) ON CONFLICT (quien, hilo) DO UPDATE SET ultimo = max(ultimo, ?3)')
    .bind(yo.quien, hilo, ultimo).run();
  return json({ ok: true });
}
