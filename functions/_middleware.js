// Todo lo publicado en Cloudflare Pages pasa por aquí: sin sesión de una cuenta de Google autorizada solo se ve
// la pantalla de entrada. A quien entra se le da también la clave que descifra los datos de las páginas
// (la guardan en sessionStorage, como si hubieran escrito la contraseña), así que no tiene que escribirla.
import CONFIG from '../acceso/config.js';   // lo genera actualizar.py en cada publicación; nunca va al repositorio
import { COOKIE, DIAS, autorizado, correoDeGoogle, creaSesion, correoDeSesion } from '../acceso/google.js';

const ENTRAR = '/_acceso/google';
const SALIR = '/_acceso/salir';
const json = (datos, status = 200, cabeceras = {}) =>
  new Response(JSON.stringify(datos), { status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...cabeceras } });

export async function onRequest({ request, next }) {
  const url = new URL(request.url);

  if (url.pathname === ENTRAR && request.method === 'POST') {
    // Solo desde nuestra propia pantalla de entrada
    if (request.headers.get('Origin') !== url.origin) return json({ error: 'Origen no permitido' }, 403);
    const { credential } = await request.json().catch(() => ({}));
    const correo = await correoDeGoogle(CONFIG, credential || '');
    if (!correo) return json({ error: 'Google no ha confirmado la cuenta. Vuelve a intentarlo.' }, 401);
    if (!autorizado(CONFIG, correo)) return json({ error: `La cuenta ${correo} no tiene acceso.` }, 403);
    const sesion = await creaSesion(CONFIG, correo);
    return json({ ok: true }, 200, { 'Set-Cookie': `${COOKIE}=${sesion}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=${DIAS * 86400}` });
  }

  if (url.pathname === SALIR) {
    return new Response(null, { status: 303, headers: { Location: '/', 'Set-Cookie': `${COOKIE}=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0` } });
  }

  if (!await correoDeSesion(CONFIG, request.headers.get('Cookie'))) {
    return new Response(pantallaDeEntrada(url), { status: 401, headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } });
  }

  const respuesta = await next();
  const cabeceras = new Headers(respuesta.headers);
  cabeceras.set('Cache-Control', 'private, no-store');
  const protegida = new Response(respuesta.body, { status: respuesta.status, statusText: respuesta.statusText, headers: cabeceras });
  if (respuesta.status !== 200 || !(cabeceras.get('Content-Type') || '').includes('text/html')) return protegida;
  const clave = `<script>try{sessionStorage.setItem('clave',${JSON.stringify(CONFIG.clave)})}catch(e){}</script>`;
  return new HTMLRewriter().on('head', { element: e => e.prepend(clave, { html: true }) }).transform(protegida);
}

function pantallaDeEntrada(url) {
  const volver = url.pathname + url.search;
  return `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Estadísticas cadete femenino</title>
<style>
:root { color-scheme: light; --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --ring: rgba(11,11,11,0.10); --neg: #e34948; }
@media (prefers-color-scheme: dark) {
  :root { color-scheme: dark; --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --ring: rgba(255,255,255,0.10); --neg: #e66767; }
}
body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: var(--page); color: var(--ink);
       font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
.caja { margin: 16px; padding: 28px 24px; max-width: 360px; background: var(--surface); border-radius: 12px;
        box-shadow: 0 0 0 1px var(--ring); text-align: center; }
h1 { margin: 0 0 6px; font-size: 1.25rem; }
p { margin: 0 0 20px; color: var(--ink-2); }
.g_id_signin { display: flex; justify-content: center; min-height: 44px; }
#error { margin: 16px 0 0; color: var(--neg); min-height: 1.5em; }
</style>
<script src="https://accounts.google.com/gsi/client" async></script>
</head>
<body>
<div class="caja">
  <h1>Estadísticas</h1>
  <p>Entra con tu cuenta de Google. Solo pueden entrar las cuentas autorizadas.</p>
  ${CONFIG.googleClientId ? `
  <div id="g_id_onload" data-client_id="${CONFIG.googleClientId}" data-callback="conGoogle" data-auto_prompt="false"></div>
  <div class="g_id_signin" data-type="standard" data-size="large" data-text="signin_with" data-shape="pill" data-locale="es"></div>`
  : '<p>Falta configurar el inicio de sesión con Google.</p>'}
  <p id="error" role="alert"></p>
</div>
<script>
const VOLVER = ${JSON.stringify(volver)};
async function conGoogle(respuesta) {
  const error = document.getElementById('error');
  error.textContent = '';
  try {
    const r = await fetch(${JSON.stringify(ENTRAR)}, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                       body: JSON.stringify({ credential: respuesta.credential }) });
    if (r.ok) return location.replace(VOLVER);
    error.textContent = (await r.json()).error;
  } catch { error.textContent = 'No se ha podido entrar. Comprueba la conexión.'; }
}
</script>
</body>
</html>`;
}
