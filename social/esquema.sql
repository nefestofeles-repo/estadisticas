-- Mensajes y reacciones de la web (base de datos D1 "estadisticas-social" de Cloudflare).
-- Se aplica en cada publicación: solo crea lo que falte.

-- Hilos: "partido:<grupo>-<jornada>" (comentarios del detalle) y "grada:<grupo>-<jornada>" (chat del directo)
CREATE TABLE IF NOT EXISTS mensajes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hilo TEXT NOT NULL,
  autor TEXT NOT NULL,              -- correo de Google
  nombre TEXT NOT NULL,             -- "Ernesto H."
  texto TEXT NOT NULL DEFAULT '',
  foto TEXT,                        -- clave de la foto en el almacén KV (FOTOS)
  creado INTEGER NOT NULL           -- milisegundos
);
CREATE INDEX IF NOT EXISTS mensajes_hilo ON mensajes (hilo, id);

-- objetivo: "hilo:<hilo>" (reacción al partido) o "mensaje:<id>"
CREATE TABLE IF NOT EXISTS reacciones (
  objetivo TEXT NOT NULL,
  autor TEXT NOT NULL,
  nombre TEXT NOT NULL,
  emoji TEXT NOT NULL,
  PRIMARY KEY (objetivo, autor, emoji)
);

-- Cambia con cada mensaje, reacción o borrado: quien está mirando un hilo solo lo vuelve a leer si cambió
CREATE TABLE IF NOT EXISTS hilos (
  hilo TEXT PRIMARY KEY,
  version INTEGER NOT NULL
);

-- Último mensaje visto por cada persona en cada hilo (para los contadores de las pestañas)
CREATE TABLE IF NOT EXISTS visto (
  quien TEXT NOT NULL,
  hilo TEXT NOT NULL,
  ultimo INTEGER NOT NULL,
  PRIMARY KEY (quien, hilo)
);

-- Mensajes reportados: se ocultan a los demás hasta que un administrador los revisa (mantener o borrar)
CREATE TABLE IF NOT EXISTS reportes (
  mensaje INTEGER NOT NULL,
  autor TEXT NOT NULL,              -- quien lo reporta (correo o "invitación:<nombre>")
  nombre TEXT NOT NULL,
  creado INTEGER NOT NULL,
  PRIMARY KEY (mensaje, autor)
);
-- Reportados que un administrador decidió mantener: vuelven a verse y ya no se ocultan
CREATE TABLE IF NOT EXISTS revisados (
  mensaje INTEGER PRIMARY KEY,
  quien TEXT NOT NULL,
  creado INTEGER NOT NULL
);
