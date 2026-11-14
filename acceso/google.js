// Inicio de sesión con Google para la web publicada en Cloudflare Pages (lo usa functions/_middleware.js).
// Google firma un token con el correo de quien entra; si está en la lista de autorizados, se le da una
// cookie de sesión firmada con nuestra clave, que vale DIAS días.

export const COOKIE = '__Host-sesion';
export const DIAS = 30;
const CERTIFICADOS = 'https://www.googleapis.com/oauth2/v3/certs';
const EMISORES = ['accounts.google.com', 'https://accounts.google.com'];

const codifica = new TextEncoder();
const aBytes = b64 => Uint8Array.from(atob(b64.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
const aB64 = bytes => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const leeJson = b64 => JSON.parse(new TextDecoder().decode(aBytes(b64)));

export const autorizado = (config, correo) => !!correo && config.autorizados.includes(correo.toLowerCase());

// Devuelve el correo si el token de Google es válido y es para nuestra aplicación; si no, null.
export async function correoDeGoogle(config, token, ahora = Date.now()) {
  try {
    const [cabecera, cuerpo, firma] = token.split('.');
    const { alg, kid } = leeJson(cabecera);
    const datos = leeJson(cuerpo);
    if (alg !== 'RS256') return null;
    const { keys } = await (await fetch(CERTIFICADOS)).json();
    const jwk = keys.find(k => k.kid === kid);
    if (!jwk) return null;
    const llave = await crypto.subtle.importKey('jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
    const valida = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', llave, aBytes(firma), codifica.encode(`${cabecera}.${cuerpo}`));
    if (!valida || datos.aud !== config.googleClientId || !EMISORES.includes(datos.iss)
        || datos.exp * 1000 < ahora || !datos.email_verified || !datos.email) return null;
    return datos.email.toLowerCase();
  } catch { return null; }
}

const llaveSesion = config =>
  crypto.subtle.importKey('raw', aBytes(config.sesion), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify']);

export async function creaSesion(config, correo, ahora = Date.now()) {
  const datos = aB64(codifica.encode(JSON.stringify({ c: correo, e: ahora + DIAS * 864e5 })));
  const firma = await crypto.subtle.sign('HMAC', await llaveSesion(config), codifica.encode(datos));
  return `${datos}.${aB64(firma)}`;
}

// Correo de la sesión si la cookie es nuestra, no ha caducado y el correo sigue autorizado; si no, null.
export async function correoDeSesion(config, cookies, ahora = Date.now()) {
  try {
    const valor = (cookies || '').split(/;\s*/).find(c => c.startsWith(`${COOKIE}=`))?.slice(COOKIE.length + 1);
    if (!valor) return null;
    const [datos, firma] = valor.split('.');
    if (!await crypto.subtle.verify('HMAC', await llaveSesion(config), aBytes(firma), codifica.encode(datos))) return null;
    const { c, e } = leeJson(datos);
    return e > ahora && autorizado(config, c) ? c : null;
  } catch { return null; }
}
