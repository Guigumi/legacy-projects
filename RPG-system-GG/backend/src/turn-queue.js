import { db } from './database.js';

export function parseQueue(value) {
  try {
    const queue = JSON.parse(value || '[]');
    return Array.isArray(queue) ? queue.filter(token => typeof token === 'string') : [];
  } catch {
    return [];
  }
}

export function participantToken(id) {
  return `p:${Number(id)}`;
}

export function effectToken(id) {
  return `e:${Number(id)}`;
}

export function queueForCombat(combateId) {
  const combate = db.prepare('SELECT * FROM combates WHERE id = ?').get(combateId);
  if (!combate) return [];
  const storedQueue = parseQueue(combate.fila_turnos);
  let queue = [...storedQueue];
  const participants = db.prepare('SELECT id FROM participantes WHERE combate_id = ? ORDER BY ordem ASC, iniciativa DESC, id ASC').all(combateId);
  const effects = db.prepare("SELECT id FROM efeitos WHERE combate_id = ? AND tipo = 'evento'").all(combateId);
  const valid = new Set([
    ...participants.map(item => participantToken(item.id)),
    ...effects.map(item => effectToken(item.id)),
  ]);
  queue = queue.filter((token, index, tokens) => valid.has(token) && tokens.indexOf(token) === index);
  const present = new Set(queue);
  for (const participant of participants) {
    const token = participantToken(participant.id);
    if (!present.has(token)) queue.push(token);
  }
  if (storedQueue.length === 0 && combate.turno_atual_id) {
    const current = participantToken(combate.turno_atual_id);
    const currentIndex = queue.indexOf(current);
    if (currentIndex > 0) queue = [...queue.slice(currentIndex), ...queue.slice(0, currentIndex)];
  }
  if (queue.join('|') !== storedQueue.join('|')) {
    db.prepare('UPDATE combates SET fila_turnos = ? WHERE id = ?').run(JSON.stringify(queue), combateId);
  }
  return queue;
}

export function saveQueue(combateId, queue, current = {}) {
  const fields = ['fila_turnos = ?'];
  const values = [JSON.stringify(queue)];
  if (current.type !== undefined) {
    fields.push('turno_atual_tipo = ?');
    values.push(current.type);
  }
  if (current.participantId !== undefined) {
    fields.push('turno_atual_id = ?');
    values.push(current.participantId);
  }
  if (current.effectId !== undefined) {
    fields.push('turno_atual_efeito_id = ?');
    values.push(current.effectId);
  }
  values.push(combateId);
  db.prepare(`UPDATE combates SET ${fields.join(', ')} WHERE id = ?`).run(...values);
}

export function queueDetails(combateId, queue = queueForCombat(combateId)) {
  const participants = new Map(db.prepare('SELECT * FROM participantes WHERE combate_id = ?').all(combateId).map(item => [participantToken(item.id), item]));
  const effects = new Map(db.prepare("SELECT * FROM efeitos WHERE combate_id = ? AND tipo = 'evento'").all(combateId).map(item => [effectToken(item.id), item]));
  return queue.map((token, index) => {
    const participant = participants.get(token);
    if (participant) return { token, tipo: 'participante', posicao: index, participante: participant };
    const efeito = effects.get(token);
    if (efeito) return { token, tipo: 'evento', posicao: index, efeito };
    return null;
  }).filter(Boolean);
}
