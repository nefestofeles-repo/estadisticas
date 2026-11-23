// Mensajes, reacciones y fotos (API en functions/api). Lo usan el panel (comentarios de cada partido y
// contadores de las pestañas) y la página de directo (chat de grada). Si la API no responde (p. ej. con la
// página abierta como archivo en el ordenador), no se muestra nada.
const Social = (() => {
  const FOTO_MAX = 1600;   // px del lado mayor: el navegador la reduce (y le quita la ubicación) antes de subirla

  async function api(ruta, opciones = {}) {
    const r = await fetch('/api/' + ruta, { cache: 'no-store', ...opciones });
    const datos = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(datos.error || `Error ${r.status}`), { status: r.status });
    return datos;
  }
  const json = (ruta, datos) => api(ruta, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) });
  let yoP;
  const yo = () => yoP ||= api('yo').catch(() => null);

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  // Texto con los enlaces (p. ej. a Google Fotos) pulsables
  const conEnlaces = t => esc(t).replace(/https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"]/g,
    u => `<a href="${u}" target="_blank" rel="noopener noreferrer">${u.replace(/^https?:\/\//, '').slice(0, 48)}${u.length > 56 ? '…' : ''}</a>`);
  function cuando(ms) {
    const min = Math.round((Date.now() - ms) / 60000);
    if (min < 1) return 'ahora';
    if (min < 60) return `hace ${min} min`;
    const d = new Date(ms), hoy = new Date();
    const hora = d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    return d.toDateString() === hoy.toDateString() ? hora : `${d.toLocaleDateString('es-ES', { day: 'numeric', month: 'short' })} ${hora}`;
  }

  async function reduceFoto(archivo) {
    const img = await createImageBitmap(archivo, { imageOrientation: 'from-image' });
    const k = Math.min(1, FOTO_MAX / Math.max(img.width, img.height));
    const lienzo = Object.assign(document.createElement('canvas'), { width: Math.round(img.width * k), height: Math.round(img.height * k) });
    lienzo.getContext('2d').drawImage(img, 0, 0, lienzo.width, lienzo.height);
    return new Promise(ok => lienzo.toBlob(ok, 'image/jpeg', 0.82));
  }

  const ESTILO = `
.s-bloque { display: grid; gap: 12px; }
.s-reacciones { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; position: relative; }
.s-chip { font: inherit; font-size: 14px; padding: 2px 10px; border-radius: 999px; border: 1px solid var(--grid); background: var(--page); color: var(--ink); cursor: pointer; line-height: 1.6; }
.s-chip.mia { border-color: var(--s1); background: color-mix(in srgb, var(--s1) 14%, transparent); }
.s-chip:disabled { cursor: default; }
.s-mas { color: var(--muted); }
.s-elige { position: absolute; z-index: 5; top: 100%; margin-top: 4px; display: flex; gap: 2px; padding: 4px; border-radius: 999px;
           background: var(--surface); box-shadow: 0 0 0 1px var(--ring), 0 4px 16px rgba(0,0,0,.15); }
.s-elige button { font-size: 20px; border: 0; background: none; cursor: pointer; padding: 2px 6px; border-radius: 999px; }
.s-elige button:hover { background: var(--grid); }
.s-cabeza { display: grid; gap: 6px; padding-bottom: 12px; border-bottom: 1px solid var(--grid); }
.s-chat header .s-reacciones { margin-left: auto; }
.s-chat header .s-chip { font-size: 12px; padding: 0 8px; }
.s-chat header .s-elige { right: 0; }
.s-chat .s-lista { padding-top: 4px; }
.s-lista { list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }
.s-chat .s-lista { max-height: 420px; overflow-y: auto; overscroll-behavior: contain; }
.s-msg { display: grid; gap: 4px; }
.s-msg header { font-size: 13px; color: var(--muted); display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap; }
.s-msg header b { color: var(--ink); }
.s-msg .s-texto { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 15px; }
.s-msg .s-texto a { color: var(--s1); }
.s-msg img { max-width: min(100%, 360px); max-height: 360px; border-radius: 8px; display: block; cursor: zoom-in; }
.s-borrar { font: inherit; font-size: 12px; border: 0; background: none; color: var(--muted); cursor: pointer; padding: 0; text-decoration: underline; }
.s-vacio { color: var(--muted); font-size: 14px; }
.s-msg.s-oculto { padding-left: 10px; border-left: 3px solid var(--neg); }
.s-msg.s-oculto .s-texto, .s-msg.s-oculto img { opacity: .6; }
.s-reportado { color: var(--neg); font-size: 12px; }
#revisar { margin: -8px 0 16px; padding: 10px 14px; border-radius: 8px; font-size: 14px; display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: baseline;
           background: color-mix(in srgb, var(--neg) 10%, transparent); box-shadow: 0 0 0 1px color-mix(in srgb, var(--neg) 35%, transparent); }
#revisar a { color: var(--ink); }
.s-form { display: grid; gap: 8px; }
.s-form textarea { font: inherit; font-size: 15px; padding: 8px 12px; border-radius: 8px; border: 1px solid var(--axis); background: var(--page);
                   color: var(--ink); resize: vertical; min-height: 44px; }
.s-form .s-fila { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.s-form button, .s-form label.s-boton { font: inherit; font-size: 14px; padding: 6px 14px; border-radius: 999px; border: 1px solid var(--axis);
                   background: var(--surface); color: var(--ink); cursor: pointer; }
.s-form button[type=submit] { background: var(--s1); border-color: var(--s1); color: #fff; font-weight: 600; margin-left: auto; }
.s-form button:disabled { opacity: .6; cursor: default; }
.s-previa { display: flex; gap: 8px; align-items: center; font-size: 13px; color: var(--muted); }
.s-previa img { height: 48px; border-radius: 6px; }
.s-aviso { font-size: 13px; color: var(--muted); margin: 0; }
.s-error { font-size: 13px; color: var(--neg); margin: 0; min-height: 0; }
.s-nuevos { display: inline-block; min-width: 18px; padding: 0 6px; margin-left: 2px; border-radius: 999px; background: var(--neg); color: #fff;
            font-size: 11px; font-weight: 700; line-height: 18px; text-align: center; }`;
  let conEstilo = false;
  const ponEstilo = () => { if (!conEstilo) document.head.append(Object.assign(document.createElement('style'), { textContent: ESTILO })); conEstilo = true; };

  // Botones de reacciones de un objetivo ("hilo:…" o "mensaje:…"); el "+" abre el selector
  function botonesReacciones(lista, objetivo, puede, emojis) {
    return `<div class="s-reacciones" data-objetivo="${esc(objetivo)}">` +
      lista.map(r => `<button type="button" class="s-chip${r.mia ? ' mia' : ''}" data-emoji="${r.emoji}" title="${esc(r.quienes.join(', '))}" ${puede ? '' : 'disabled'}>${r.emoji} ${r.n}</button>`).join('') +
      (puede ? `<button type="button" class="s-chip s-mas" data-elegir aria-label="Reaccionar">${lista.length ? '+' : '+ 🙂'}</button>` : '') + '</div>';
  }

  // Un hilo: comentarios de un partido (modo "comentarios", con reacciones al partido) o chat de grada (modo "chat")
  async function hilo(el, id, { modo = 'comentarios', cada = 0, vacio = 'Todavía no hay mensajes.', soloLeer = false,
                                pregunta = '¿Qué te ha parecido el partido?', placeholder = '' } = {}) {
    const usuario = await yo();
    if (!usuario) return null;
    ponEstilo();
    const puede = usuario.puedeEscribir && !soloLeer;
    el.hidden = false;
    el.classList.add('s-bloque', modo === 'chat' ? 's-chat' : 's-comentarios');
    el.innerHTML = (modo === 'comentarios' ? `<div class="s-cabeza"><span class="s-aviso">${esc(pregunta)}</span><div class="s-hilo-reac"></div></div>` : '') + '<ul class="s-lista"></ul><p class="s-error" role="alert"></p>' +
      (puede ? `<form class="s-form">
        <textarea name="texto" rows="2" maxlength="1000" placeholder="${esc(placeholder || (modo === 'chat' ? 'Escribe en la grada…' : 'Escribe un comentario…'))}"></textarea>
        <div class="s-previa" hidden></div>
        <div class="s-fila"><label class="s-boton">📷 Foto<input type="file" accept="image/*" hidden></label>
          <button type="submit">Enviar</button></div>
        <p class="s-aviso">Puedes pegar enlaces, por ejemplo a un álbum de Google Fotos (lo podrá abrir cualquiera que tenga el enlace).</p>
      </form>` : soloLeer ? '' : '<p class="s-aviso">Para escribir o reaccionar hay que entrar con una cuenta de Google.</p>');
    const lista = el.querySelector('.s-lista'), fallo = el.querySelector('.s-error');
    let version = null, foto = null, parado = false, primera = true, cuantos = 0;

    async function carga() {
      try {
        const d = await api(`hilo/${id}${version ? '?version=' + version : ''}`);
        fallo.textContent = '';
        if (d.sinCambios) return;
        version = d.version;
        cuantos = d.mensajes.length;
        const abajo = lista.scrollHeight - lista.scrollTop - lista.clientHeight < 40;
        if (modo === 'comentarios') el.querySelector('.s-hilo-reac').innerHTML = botonesReacciones(d.reacciones, `hilo:${id}`, puede, usuario.emojis);
        // En el chat las reacciones van en la línea del nombre, para que ocupe poco
        const reac = m => m.reacciones.length || puede ? botonesReacciones(m.reacciones, `mensaje:${m.id}`, puede, usuario.emojis) : '';
        // Reportado: el administrador ve quién lo reportó y decide; su autor sabe que está oculto; los demás no lo ven
        const estado = m => m.oculto
          ? (usuario.admin ? `<span class="s-reportado">Reportado por ${esc(m.reportadoPor.join(', '))} · oculto para los demás</span>
               <button type="button" class="s-borrar" data-mantener="${m.id}">Mantener</button>`
             : '<span class="s-reportado">Oculto: lo está revisando un administrador</span>')
          : m.reportadoPorMi ? '<span class="s-reportado">Lo has reportado</span>'
          : m.puedeReportar ? `<button type="button" class="s-borrar" data-reportar="${m.id}" title="Ocultarlo hasta que lo revise un administrador">Reportar</button>` : '';
        lista.innerHTML = d.mensajes.map(m => `<li class="s-msg${m.oculto ? ' s-oculto' : ''}">
            <header><b>${esc(m.nombre)}</b><span>${cuando(m.creado)}</span>${m.puedeBorrar ? `<button type="button" class="s-borrar" data-borrar="${m.id}">Borrar</button>` : ''}${estado(m)}${modo === 'chat' ? reac(m) : ''}</header>
            ${m.texto ? `<div class="s-texto">${conEnlaces(m.texto)}</div>` : ''}
            ${m.foto ? `<a href="/api/foto/${m.foto}" target="_blank"><img src="/api/foto/${m.foto}" alt="Foto de ${esc(m.nombre)}" loading="lazy"></a>` : ''}
            ${modo === 'chat' ? '' : reac(m)}
          </li>`).join('') || `<li class="s-vacio">${esc(vacio)}</li>`;
        if (modo === 'chat' && (abajo || primera)) lista.scrollTop = lista.scrollHeight;
        primera = false;
        const ultimo = d.mensajes.at(-1)?.id;
        if (ultimo && !document.hidden) json('visto', { hilo: id, ultimo }).catch(() => {});
      } catch (e) { fallo.textContent = e.message; }
    }

    el.addEventListener('click', async e => {
      const b = e.target.closest('button');
      if (!b || !el.contains(b)) return;
      if (b.dataset.borrar) {
        if (!confirm('¿Borrar este mensaje?')) return;
        try { await api(`mensaje/${b.dataset.borrar}`, { method: 'DELETE' }); } catch (err) { fallo.textContent = err.message; }
        return carga();
      }
      if (b.dataset.reportar) {
        if (!confirm('¿Reportar este mensaje? Dejará de verse hasta que un administrador lo revise.')) return;
        try { await json('reporte', { mensaje: +b.dataset.reportar }); } catch (err) { fallo.textContent = err.message; }
        return carga();
      }
      if (b.dataset.mantener) {
        try { await json('revisar', { mensaje: +b.dataset.mantener }); } catch (err) { fallo.textContent = err.message; }
        return carga();
      }
      if (b.hasAttribute('data-elegir')) {
        el.querySelectorAll('.s-elige').forEach(x => x.remove());
        b.closest('.s-reacciones').insertAdjacentHTML('beforeend',
          `<div class="s-elige">${usuario.emojis.map(x => `<button type="button" data-emoji="${x}">${x}</button>`).join('')}</div>`);
        return;
      }
      if (b.dataset.emoji) {
        const objetivo = b.closest('.s-reacciones').dataset.objetivo;
        el.querySelectorAll('.s-elige').forEach(x => x.remove());
        try { await json('reaccion', { objetivo, emoji: b.dataset.emoji }); } catch (err) { fallo.textContent = err.message; }
        return carga();
      }
    });
    document.addEventListener('click', e => { if (!e.target.closest('.s-reacciones')) el.querySelectorAll('.s-elige').forEach(x => x.remove()); });

    const form = el.querySelector('.s-form');
    if (form) {
      const previa = form.querySelector('.s-previa');
      form.querySelector('input[type=file]').addEventListener('change', async e => {
        const archivo = e.target.files[0];
        e.target.value = '';
        if (!archivo) return;
        try {
          foto = await reduceFoto(archivo);
          previa.hidden = false;
          previa.innerHTML = `<img src="${URL.createObjectURL(foto)}" alt=""><span>Foto lista</span><button type="button" class="s-borrar">Quitar</button>`;
          previa.querySelector('button').onclick = () => { foto = null; previa.hidden = true; previa.innerHTML = ''; };
        } catch { fallo.textContent = 'No se ha podido leer la foto.'; }
      });
      const texto = form.querySelector('textarea');
      // En el ordenador, Intro envía y Mayús+Intro hace un salto de línea
      texto.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && matchMedia('(pointer: fine)').matches) { e.preventDefault(); form.requestSubmit(); } });
      form.addEventListener('submit', async e => {
        e.preventDefault();
        if (!texto.value.trim() && !foto) return;
        const datos = new FormData();
        datos.append('texto', texto.value);
        if (foto) datos.append('foto', foto, 'foto.jpg');
        const boton = form.querySelector('[type=submit]');
        boton.disabled = true;
        try {
          await api(`hilo/${id}`, { method: 'POST', body: datos });
          texto.value = ''; foto = null; previa.hidden = true; previa.innerHTML = '';
          await carga();
          if (modo === 'chat') lista.scrollTop = lista.scrollHeight;
        } catch (err) { fallo.textContent = err.message; }
        boton.disabled = false;
      });
    }

    await carga();
    if (cada) (function sigue() { setTimeout(async () => { if (parado) return; if (!document.hidden) await carga(); sigue(); }, cada); })();
    document.addEventListener('visibilitychange', () => { if (!document.hidden && !parado) carga(); });
    return { parar: () => { parado = true; }, get mensajes() { return cuantos; } };
  }

  // Mensajes sin ver: { hilos: { "partido:7438-3": 2, … } }
  let novP;
  const novedades = () => novP ||= api('novedades').catch(() => null);
  const globo = n => n ? `<span class="s-nuevos" title="${n} mensaje${n === 1 ? '' : 's'} nuevo${n === 1 ? '' : 's'}">${n > 99 ? '99+' : n}</span>` : '';
  // Pone el contador en cada elemento según los hilos que cuente (prefijo "partido:" o un hilo concreto)
  async function contadores(marcas) {
    const hilos = (await novedades())?.hilos;
    if (!hilos) return;
    ponEstilo();
    for (const [el, cuenta] of marcas) {
      const n = Object.entries(hilos).filter(([h]) => cuenta(h)).reduce((a, [, k]) => a + k, 0);
      el?.querySelector('.s-nuevos')?.remove();
      el?.insertAdjacentHTML('beforeend', globo(n));
    }
  }

  // Aviso para los administradores con enlaces a los mensajes reportados; enlace(hilo) → [texto, dirección]
  async function pendientes(el, enlace) {
    const revisar = Object.entries((await novedades())?.revisar || {});
    if (!el || !revisar.length) return;
    ponEstilo();
    const total = revisar.reduce((a, [, n]) => a + n, 0);
    el.innerHTML = `<b>⚠ ${total} mensaje${total === 1 ? '' : 's'} reportado${total === 1 ? '' : 's'} por revisar:</b>` +
      revisar.map(([h, n]) => { const [texto, href] = enlace(h); return `<a href="${esc(href)}">${esc(texto)}${n > 1 ? ` (${n})` : ''}</a>`; }).join('');
    el.hidden = false;
  }

  return { yo, hilo, contadores, pendientes };
})();
