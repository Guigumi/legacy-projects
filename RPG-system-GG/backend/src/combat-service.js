import { db } from './database.js';

export function captureCombat(combateId) {
  return JSON.stringify({
    combate: db.prepare('SELECT * FROM combates WHERE id = ?').get(combateId),
    participantes: db.prepare('SELECT * FROM participantes WHERE combate_id = ? ORDER BY id ASC').all(combateId),
    efeitos: db.prepare('SELECT * FROM efeitos WHERE combate_id = ? ORDER BY id ASC').all(combateId),
    logs: db.prepare('SELECT * FROM log_eventos WHERE combate_id = ? ORDER BY id ASC').all(combateId),
  });
}

export function restoreCombat(snapshot) {
  const state = typeof snapshot === 'string' ? JSON.parse(snapshot) : snapshot;
  const combate = state.combate;
  db.prepare('UPDATE combates SET nome=:nome, rodada=:rodada, turno_atual_id=:turno_atual_id, turno_atual_tipo=:turno_atual_tipo, turno_atual_efeito_id=:turno_atual_efeito_id, fila_turnos=:fila_turnos, status=:status, notas=:notas WHERE id=:id').run({
    id: combate.id,
    nome: combate.nome,
    rodada: combate.rodada,
    turno_atual_id: combate.turno_atual_id,
    turno_atual_tipo: combate.turno_atual_tipo === 'magia' ? 'evento' : (combate.turno_atual_tipo || 'participante'),
    turno_atual_efeito_id: combate.turno_atual_efeito_id || null,
    fila_turnos: combate.fila_turnos || '[]',
    status: combate.status,
    notas: combate.notas || '',
  });
  db.prepare('DELETE FROM efeitos WHERE combate_id = ?').run(combate.id);
  db.prepare('DELETE FROM participantes WHERE combate_id = ?').run(combate.id);
  db.prepare('DELETE FROM log_eventos WHERE combate_id = ?').run(combate.id);
  const insertParticipant = db.prepare(`INSERT INTO participantes (id, combate_id, nome, tipo, iniciativa, hp_atual, hp_max, mp_atual, mp_max, turnos_jogados, ordem, foto, personagem_id) VALUES (:id,:combate_id,:nome,:tipo,:iniciativa,:hp_atual,:hp_max,:mp_atual,:mp_max,:turnos_jogados,:ordem,:foto,:personagem_id)`);
  for (const participant of state.participantes) insertParticipant.run({ ...participant, foto: participant.foto ?? null, personagem_id: participant.personagem_id ?? null });
  const insertEffect = db.prepare(`INSERT INTO efeitos (id, combate_id, nome, tipo, descricao, alvo_id, conjurador_id, duracao, decaimento, criado_em) VALUES (:id,:combate_id,:nome,:tipo,:descricao,:alvo_id,:conjurador_id,:duracao,:decaimento,:criado_em)`);
  for (const efeito of state.efeitos || []) insertEffect.run({ ...efeito, tipo: efeito.tipo || 'magia', descricao: efeito.descricao || '', alvo_id: efeito.alvo_id ?? null, conjurador_id: efeito.conjurador_id ?? null });
  const insertLog = db.prepare('INSERT INTO log_eventos (id, combate_id, participante_id, evento, detalhes, rodada, criado_em) VALUES (:id,:combate_id,:participante_id,:evento,:detalhes,:rodada,:criado_em)');
  for (const log of state.logs) insertLog.run(log);
}

export function recordCombatHistory(combateId, acao, antes) {
  const depois = captureCombat(combateId);
  const combate = db.prepare('SELECT historico_cursor FROM combates WHERE id = ?').get(combateId);
  const cursor = combate?.historico_cursor || 0;
  db.prepare('DELETE FROM historico_combate WHERE combate_id = ? AND id > ?').run(combateId, cursor);
  const info = db.prepare('INSERT INTO historico_combate (combate_id, acao, antes, depois) VALUES (?, ?, ?, ?)').run(combateId, acao, antes, depois);
  db.prepare('UPDATE combates SET historico_cursor = ? WHERE id = ?').run(Number(info.lastInsertRowid), combateId);
}

export function registrarLog(combateId, participanteId, evento, detalhes, rodada) {
  db.prepare('INSERT INTO log_eventos (combate_id, participante_id, evento, detalhes, rodada) VALUES (?, ?, ?, ?, ?)').run(combateId, participanteId, evento, detalhes, rodada);
}

export function decrementEffectsForParticipant(combateId, participanteId) {
  const effects = db.prepare(`
    SELECT * FROM efeitos
    WHERE combate_id = ?
      AND ((decaimento = 'alvo' AND alvo_id = ?) OR (decaimento = 'conjurador' AND conjurador_id = ?))
  `).all(combateId, participanteId, participanteId);
  for (const efeito of effects) {
    if (efeito.duracao <= 1) {
      db.prepare('DELETE FROM efeitos WHERE id = ?').run(efeito.id);
      registrarLog(combateId, participanteId, 'efeito_expirado', `${efeito.nome} terminou`, null);
    } else {
      db.prepare('UPDATE efeitos SET duracao = duracao - 1 WHERE id = ?').run(efeito.id);
    }
  }
}
