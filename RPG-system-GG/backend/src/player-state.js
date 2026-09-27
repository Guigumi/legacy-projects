import { db } from './database.js';
import { queueDetails } from './turn-queue.js';

export function getPlayerState() {
  const transmissao = db.prepare('SELECT * FROM transmissao WHERE id = 1').get() || { mostrar_fila: 1, mostrar_logs: 1, volume: 0.7 };
  const combate = db.prepare("SELECT id, nome, rodada, turno_atual_id, turno_atual_tipo, turno_atual_efeito_id, status FROM combates WHERE status = 'ativo' ORDER BY id DESC LIMIT 1").get();
  if (!combate) {
    const rolagens = db.prepare('SELECT * FROM rolagens ORDER BY id DESC LIMIT 30').all().reverse();
    return { combate: null, participantes: [], efeitos: [], fila: [], logs: [], rolagens, transmissao };
  }

  const participantes = db.prepare(`
    SELECT id, nome, tipo, iniciativa, hp_atual, hp_max, mp_atual, mp_max, ordem, foto
    FROM participantes
    WHERE combate_id = ?
    ORDER BY ordem ASC, iniciativa DESC, id ASC
  `).all(combate.id);
  const logs = db.prepare(`
    SELECT evento, detalhes, rodada, criado_em
    FROM log_eventos
    WHERE combate_id = ?
    ORDER BY id DESC
    LIMIT 20
  `).all(combate.id).reverse();

  const efeitos = db.prepare('SELECT * FROM efeitos WHERE combate_id = ? ORDER BY id ASC').all(combate.id);
  const rolagens = db.prepare('SELECT * FROM rolagens ORDER BY id DESC LIMIT 30').all().reverse();
  return { combate, participantes, efeitos, fila: queueDetails(combate.id), logs, rolagens, transmissao };
}
