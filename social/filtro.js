// Filtro automático de mensajes: no deja publicar insultos, palabrotas ni comentarios sexuales u ofensivos.
// Es una lista de palabras: frena lo evidente, pero no entiende el contexto (un administrador puede borrar
// cualquier mensaje que se cuele). Se comprueba en el servidor (functions/api/[[ruta]].js) al escribir.

// Palabras que empiezan así (cubre femenino, plural, aumentativos…)
const RAICES = [
  'put', 'mierd', 'gilipoll', 'subnormal', 'imbecil', 'idiot', 'estupid', 'cabron', 'capull', 'pendej',
  'retrasad', 'mongol', 'maric', 'boller', 'tortiller', 'jod', 'follar', 'follad', 'mamad', 'pajiller',
  'chupame', 'chupala', 'chupamela', 'asquero', 'guarr', 'furcia', 'ramer', 'inutil', 'zorr', 'malparid',
  'cagon', 'fuck', 'shit', 'bitch', 'whore', 'slut',
];
// Palabras exactas (como raíz darían falsos positivos: "tontería", "fearless", "cerdo asado"…)
const EXACTAS = new Set([
  'tonta', 'tonto', 'tontas', 'tontos', 'gorda', 'gordas', 'gordo', 'gordos', 'fea', 'feas', 'feo', 'feos',
  'cerda', 'cerdas', 'perra', 'perras', 'golfa', 'golfas', 'polla', 'pollas', 'co#o', 'co#os', 'nazi', 'basura',
  'caca', 'culo', 'culos', 'tetas', 'pechos', 'sexy', 'cachonda', 'buenorra',
]);
const LEET = { 0: 'o', 1: 'i', 3: 'e', 4: 'a', 5: 's', 7: 't', '@': 'a', $: 's' };

export function palabrasProhibidas(texto) {
  const limpio = String(texto || '').toLowerCase()
    .replace(/ñ/g, '#')                                   // "coño" no es "cono"
    .normalize('NFKD').replace(/[̀-ͯ]/g, '')    // sin tildes
    .replace(/[013457@$]/g, c => LEET[c])                 // "put0", "m13rda"
    .replace(/([a-z#])\1{2,}/g, '$1');                    // "putaaaa"
  const palabras = limpio.split(/[^a-z#]+/).filter(Boolean);
  // También juntando letras sueltas: "p u t a", "p.u.t.a"
  const sueltas = limpio.split(/[^a-z#]+/).join(' ').match(/(?:\b[a-z#]\b ?){3,}/g)?.map(s => s.replace(/ /g, '')) || [];
  return [...palabras, ...sueltas].some(p => EXACTAS.has(p) || RAICES.some(r => p.startsWith(r)));
}
