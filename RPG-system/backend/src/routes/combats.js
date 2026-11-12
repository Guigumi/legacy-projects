import { Router } from 'express';
import { db } from '../database.js';
import { captureCombat, decrementEffectsForParticipant, recordCombatHistory, registrarLog, restoreCombat } from '../combat-service.js';
import { participantToken, queueDetails, queueForCombat, saveQueue } from '../turn-queue.js';
import { validateIdParam } from './validate-id.js';

const router = validateIdParam(Router());

function requireCombat(combateId, res) {
  const combate = db.prepare('SELECT * FROM combates WHERE id = ?').get(combateId);
  if (!combate) {
    res.status(404).json({ error: 'Combate não encontrado.' });
    return null;
  }
  return combate;
}

router.get('/combates', (req, res) => {
  res.json(db.prepare('SELECT * FROM combates ORDER BY criado_em DESC').all());
});

router.post('/combates', (req, res) => {
  const requestedName = typeof req.body?.nome === 'string' ? req.body.nome.trim() : '';
  if (requestedName.length > 120) return res.status(400).json({ error: 'O nome da sessão deve ter no máximo 120 caracteres.' });
  const nome = requestedName || `Sessão ${new Date().toISOString().slice(0, 16).replace('T', ' ')}`;
  try {
    const info = db.prepare('INSERT INTO combates (nome, rodada) VALUES (?, 1)').run(nome);
    const combate = db.prepare('SELECT * FROM combates WHERE id = ?').get(Number(info.lastInsertRowid));
    if (!combate) return res.status(500).json({ error: 'A sessão foi criada, mas houve um erro ao carregá-la.' });
    res.status(201).json(combate);
  } catch (error) {
    console.error('Falha ao criar sessão:', error);
    res.status(500).json({ error: 'Não foi possível criar a sessão. Tente novamente.' });
  }
});

router.get('/combates/:id', (req, res) => {
  const combateId = req.params.id;
  const combate = requireCombat(combateId, res);
  if (!combate) return;
  combate.participantes = db.prepare('SELECT * FROM participantes WHERE combate_id = ? ORDER BY ordem ASC, iniciativa DESC').all(combateId);
  combate.efeitos = db.prepare('SELECT * FROM efeitos WHERE combate_id = ? ORDER BY id ASC').all(combateId);
  const queue = queueForCombat(combateId);
  if (!combate.turno_atual_id && !combate.turno_atual_efeito_id && queue[0]) {
    if (queue[0].startsWith('p:')) saveQueue(combateId, queue, { type: 'participante', participantId: Number(queue[0].slice(2)), effectId: null });
    else saveQueue(combateId, queue, { type: 'evento', participantId: null, effectId: Number(queue[0].slice(2)) });
    combate.turno_atual_tipo = queue[0].startsWith('p:') ? 'participante' : 'evento';
    combate.turno_atual_id = queue[0].startsWith('p:') ? Number(queue[0].slice(2)) : null;
    combate.turno_atual_efeito_id = queue[0].startsWith('e:') ? Number(queue[0].slice(2)) : null;
  }
  combate.fila = queueDetails(combateId, queue);
  res.json(combate);
});

router.delete('/combates/:id', (req, res) => {
  const combateId = req.params.id;
  if (!requireCombat(combateId, res)) return;
  db.prepare('DELETE FROM participantes WHERE combate_id = ?').run(combateId);
  db.prepare('DELETE FROM log_eventos WHERE combate_id = ?').run(combateId);
  db.prepare('DELETE FROM combates WHERE id = ?').run(combateId);
  res.json({ ok: true });
});

router.put('/combates/:id', (req, res) => {
  if (!requireCombat(req.params.id, res)) return;
  const fields = ['nome', 'rodada', 'status', 'notas'];
  const sets = [];
  const values = { id: req.params.id };
  for (const field of fields) {
    if (req.body[field] !== undefined) {
      sets.push(`${field} = :${field}`);
      values[field] = req.body[field];
    }
  }
  if (sets.length > 0) db.prepare(`UPDATE combates SET ${sets.join(', ')} WHERE id = :id`).run(values);
  res.json({ ok: true });
});

router.put('/combates/:id/notas', (req, res) => {
  const combateId = req.params.id;
  if (!requireCombat(combateId, res)) return;
  const antes = captureCombat(combateId);
  db.prepare('UPDATE combates SET notas = ? WHERE id = ?').run(String(req.body.notas || ''), combateId);
  recordCombatHistory(combateId, 'notas', antes);
  res.json({ ok: true });
});

router.put('/combates/:id/ordem', (req, res) => {
  if (!requireCombat(req.params.id, res)) return;
  const ids = Array.isArray(req.body.ids) ? req.body.ids.map(Number) : [];
  const update = db.prepare('UPDATE participantes SET ordem = ? WHERE id = ? AND combate_id = ?');
  const combateId = req.params.id;
  const antes = captureCombat(combateId);
  db.exec('BEGIN');
  try {
    ids.forEach((id, index) => update.run(index, id, combateId));
    db.exec('COMMIT');
  } catch (error) {
    db.exec('ROLLBACK');
    throw error;
  }
  const queue = queueForCombat(combateId);
  const effects = queue.filter(token => token.startsWith('e:'));
  saveQueue(combateId, [...ids.map(participantToken), ...effects]);
  recordCombatHistory(combateId, 'ordem', antes);
  res.json({ ok: true });
});

router.put('/combates/:id/fila', (req, res) => {
  const combateId = req.params.id;
  if (!requireCombat(combateId, res)) return;
  const antes = captureCombat(combateId);
  const atual = queueForCombat(combateId);
  const tokens = Array.isArray(req.body?.tokens) ? req.body.tokens.filter(token => typeof token === 'string') : [];
  const currentSet = new Set(atual);
  if (tokens.length !== atual.length || new Set(tokens).size !== tokens.length || tokens.some(token => !currentSet.has(token))) {
    return res.status(400).json({ error: 'A nova ordem da fila é inválida.' });
  }
  const primeiro = tokens[0];
  if (primeiro?.startsWith('p:')) {
    saveQueue(combateId, tokens, { type: 'participante', participantId: Number(primeiro.slice(2)), effectId: null });
  } else if (primeiro?.startsWith('e:')) {
    saveQueue(combateId, tokens, { type: 'evento', participantId: null, effectId: Number(primeiro.slice(2)) });
  } else {
    saveQueue(combateId, tokens);
  }
  recordCombatHistory(combateId, 'fila_reordenada', antes);
  res.json({ fila: queueDetails(combateId, tokens) });
});

router.post('/combates/:id/participantes', (req, res) => {
  const combateId = req.params.id;
  if (!requireCombat(combateId, res)) return;
  const antes = captureCombat(combateId);
  const { nome, tipo, iniciativa, hp_atual, hp_max, mp_atual, mp_max, personagem_id, bestiario_id } = req.body;
  let finalNome = nome;
  let finalHpMax = hp_max ?? 100;
  let finalMpMax = mp_max ?? 100;
  let finalHpAtual = hp_atual ?? 100;
  let finalMpAtual = mp_atual ?? 100;
  let finalInit = iniciativa ?? 0;
  let finalTipo = tipo ?? 'jogador';
  let finalFoto = null;
  let finalPersonagemId = null;

  if (!['jogador', 'inimigo'].includes(finalTipo)) return res.status(400).json({ error: 'Tipo de participante inválido.' });

  if (personagem_id) {
    const pers = db.prepare('SELECT * FROM personagens WHERE id = ?').get(Number(personagem_id));
    if (!pers) return res.status(400).json({ error: 'Ficha de personagem não encontrada.' });
    finalNome = pers.nome;
    finalHpMax = pers.hp_max;
    finalMpMax = pers.mp_max;
    finalHpAtual = pers.hp_max;
    finalMpAtual = pers.mp_max;
    finalTipo = 'jogador';
    finalFoto = pers.foto || null;
    finalPersonagemId = Number(personagem_id);
  }

  if (bestiario_id) {
    const inimigo = db.prepare('SELECT * FROM bestiario WHERE id = ?').get(Number(bestiario_id));
    if (!inimigo) return res.status(400).json({ error: 'Preset de inimigo não encontrado.' });
    finalNome = inimigo.nome;
    finalHpMax = inimigo.hp_max;
    finalHpAtual = inimigo.hp_max;
    finalMpMax = 0;
    finalMpAtual = 0;
    finalTipo = 'inimigo';
    finalFoto = inimigo.foto || null;
  }

  if (typeof finalNome !== 'string' || !finalNome.trim()) return res.status(400).json({ error: 'Informe o nome do participante.' });

  const ordem = db.prepare('SELECT COUNT(*) as c FROM participantes WHERE combate_id = ?').get(combateId).c;
  const info = db.prepare(`INSERT INTO participantes (combate_id, nome, tipo, iniciativa, hp_atual, hp_max, mp_atual, mp_max, turnos_jogados, ordem, foto, personagem_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)`).run(combateId, finalNome, finalTipo, finalInit, finalHpAtual, finalHpMax, finalMpAtual, finalMpMax, ordem, finalFoto, finalPersonagemId);
  const queue = queueForCombat(combateId);
  const combate = db.prepare('SELECT turno_atual_id, turno_atual_efeito_id FROM combates WHERE id = ?').get(combateId);
  if (!combate.turno_atual_id && !combate.turno_atual_efeito_id) saveQueue(combateId, queue, { type: 'participante', participantId: Number(info.lastInsertRowid), effectId: null });
  else saveQueue(combateId, queue);
  recordCombatHistory(combateId, 'participante_adicionado', antes);
  res.json({ id: Number(info.lastInsertRowid) });
});

router.put('/participantes/:id', (req, res) => {
  const participant = db.prepare('SELECT combate_id FROM participantes WHERE id = ?').get(req.params.id);
  const antes = participant ? captureCombat(participant.combate_id) : null;
  const campos = ['nome', 'tipo', 'iniciativa', 'hp_atual', 'hp_max', 'mp_atual', 'mp_max', 'turnos_jogados', 'ordem', 'foto'];
  const sets = [];
  const vals = { id: req.params.id };
  for (const c of campos) {
    if (req.body[c] !== undefined) { sets.push(`${c} = :${c}`); vals[c] = req.body[c]; }
  }
  if (sets.length === 0) return res.json({ ok: true });
  db.prepare(`UPDATE participantes SET ${sets.join(', ')} WHERE id = :id`).run(vals);
  if (participant && antes) recordCombatHistory(participant.combate_id, 'participante_atualizado', antes);
  res.json({ ok: true });
});

router.delete('/participantes/:id', (req, res) => {
  const participantId = req.params.id;
  const p = db.prepare('SELECT combate_id FROM participantes WHERE id = ?').get(participantId);
  const antes = p ? captureCombat(p.combate_id) : null;
  db.prepare('DELETE FROM participantes WHERE id = ?').run(participantId);
  if (p) {
    const c = db.prepare('SELECT * FROM combates WHERE id = ?').get(p.combate_id);
    const queue = queueForCombat(p.combate_id);
    if (c && c.turno_atual_id === Number(participantId)) {
      const next = queue[0];
      if (next?.startsWith('p:')) saveQueue(p.combate_id, queue, { type: 'participante', participantId: Number(next.slice(2)), effectId: null });
      else if (next?.startsWith('e:')) saveQueue(p.combate_id, queue, { type: 'evento', participantId: null, effectId: Number(next.slice(2)) });
      else saveQueue(p.combate_id, queue, { type: 'participante', participantId: null, effectId: null });
    }
  }
  if (p && antes) recordCombatHistory(p.combate_id, 'participante_removido', antes);
  res.json({ ok: true });
});

router.get('/combates/:id/log', (req, res) => {
  if (!requireCombat(req.params.id, res)) return;
  res.json(db.prepare('SELECT * FROM log_eventos WHERE combate_id = ? ORDER BY id DESC LIMIT 50').all(req.params.id));
});

router.post('/combates/:id/avancar-turno', (req, res) => {
  const combateId = req.params.id;
  const antes = captureCombat(combateId);
  const combate = db.prepare('SELECT * FROM combates WHERE id = ?').get(combateId);
  if (!combate) return res.status(404).json({ error: 'Combate não encontrado.' });

  let queue = queueForCombat(combateId);
  if (queue.length === 0) return res.status(400).json({ error: 'Nenhum participante no combate.' });
  const current = queue.shift();
  const lastParticipant = db.prepare('SELECT id FROM participantes WHERE combate_id = ? ORDER BY ordem DESC, iniciativa ASC, id DESC LIMIT 1').get(combateId);
  const completedParticipantCycle = current.startsWith('p:') && Number(current.slice(2)) === lastParticipant?.id;
  let rodada = combate.rodada;

  if (current.startsWith('p:')) {
    const participanteId = Number(current.slice(2));
    const atual = db.prepare('SELECT * FROM participantes WHERE id = ? AND combate_id = ?').get(participanteId, combateId);
    if (atual) {
      const novosTurnos = atual.turnos_jogados + 1;
      const novoMp = novosTurnos % 2 === 0 ? Math.min(atual.mp_max, atual.mp_atual + 5) : atual.mp_atual;
      db.prepare('UPDATE participantes SET turnos_jogados = ?, mp_atual = ? WHERE id = ?').run(novosTurnos, novoMp, atual.id);
      registrarLog(combateId, atual.id, 'turno_finalizado', `Turno ${novosTurnos} concluido${novosTurnos % 2 === 0 ? ' (+5 MP)' : ''}`, rodada);
      decrementEffectsForParticipant(combateId, atual.id);
      queue.push(current);
    }
  } else if (current.startsWith('e:')) {
    const efeitoId = Number(current.slice(2));
    const efeito = db.prepare('SELECT * FROM efeitos WHERE id = ? AND combate_id = ?').get(efeitoId, combateId);
    if (efeito) {
      registrarLog(combateId, efeito.conjurador_id, efeito.tipo === 'evento' ? 'turno_evento' : 'turno_efeito', `${efeito.nome} agiu (${efeito.duracao} restante${efeito.duracao === 1 ? '' : 's'})`, rodada);
      if (efeito.duracao <= 1) {
        db.prepare('DELETE FROM efeitos WHERE id = ?').run(efeito.id);
        registrarLog(combateId, efeito.conjurador_id, 'efeito_expirado', `${efeito.nome} terminou`, rodada);
      } else {
        db.prepare('UPDATE efeitos SET duracao = duracao - 1 WHERE id = ?').run(efeito.id);
        queue.push(current);
      }
    }
  }

  if (completedParticipantCycle) rodada++;
  if (queue.length === 0) return res.status(400).json({ error: 'A fila ficou sem participantes.' });
  const next = queue[0];
  if (next.startsWith('p:')) {
    const nextId = Number(next.slice(2));
    saveQueue(combateId, queue, { type: 'participante', participantId: nextId, effectId: null });
    registrarLog(combateId, nextId, 'turno_iniciado', `Rodada ${rodada}`, rodada);
  } else {
    saveQueue(combateId, queue, { type: 'evento', participantId: null, effectId: Number(next.slice(2)) });
  }
  db.prepare('UPDATE combates SET rodada = ? WHERE id = ?').run(rodada, combateId);
  recordCombatHistory(combateId, 'turno_avancado', antes);
  res.json({ proximo: next, rodada, fila: queueDetails(combateId, queue) });
});

router.post('/combates/:id/turno-extra', (req, res) => {
  const combateId = req.params.id;
  const antes = captureCombat(combateId);
  const combate = db.prepare('SELECT * FROM combates WHERE id = ?').get(combateId);
  if (!combate) return res.status(404).json({ error: 'Combate não encontrado.' });

  const participanteId = Number(req.body?.participante_id);
  const alvo = db.prepare('SELECT * FROM participantes WHERE id = ? AND combate_id = ?').get(participanteId, combateId);
  if (!alvo) return res.status(400).json({ error: 'Escolha um participante válido para o turno extra.' });
  const queue = queueForCombat(combateId).filter(token => token !== participantToken(alvo.id));
  queue.unshift(participantToken(alvo.id));
  saveQueue(combateId, queue, { type: 'participante', participantId: alvo.id, effectId: null });
  registrarLog(combateId, alvo.id, 'turno_extra', `${alvo.nome} foi movido para o topo da fila`, combate.rodada);
  recordCombatHistory(combateId, 'turno_extra', antes);

  res.json({ alvo, rodada: combate.rodada, fila: queueDetails(combateId, queue) });
});

router.post('/combates/:id/rolar-iniciativa', (req, res) => {
  const combateId = req.params.id;
  if (!requireCombat(combateId, res)) return;
  const antes = captureCombat(combateId);
  const modificadores = req.body?.modificadores || {};
  const participantes = db.prepare('SELECT * FROM participantes WHERE combate_id = ?').all(combateId);
  for (const p of participantes) {
    const roll = Math.floor(Math.random() * 20) + 1;
    const iniciativa = roll + (modificadores[p.id] || 0);
    db.prepare('UPDATE participantes SET iniciativa = ? WHERE id = ?').run(iniciativa, p.id);
  }
  const atualizados = db.prepare('SELECT * FROM participantes WHERE combate_id = ? ORDER BY iniciativa DESC, ordem ASC').all(combateId);
  if (atualizados.length > 0) {
    const updateOrder = db.prepare('UPDATE participantes SET ordem = ? WHERE id = ?');
    atualizados.forEach((participante, index) => updateOrder.run(index, participante.id));
    const eventos = queueForCombat(combateId).filter(token => token.startsWith('e:'));
    saveQueue(combateId, [...atualizados.map(participante => participantToken(participante.id)), ...eventos], { type: 'participante', participantId: atualizados[0].id, effectId: null });
  }
  registrarLog(combateId, null, 'iniciativa_rolada', 'Iniciativa rolada para todos os participantes', 1);
  recordCombatHistory(combateId, 'iniciativa', antes);
  res.json({ participantes: atualizados });
});

router.get('/combates/:id/historico', (req, res) => {
  const combateId = req.params.id;
  if (!requireCombat(combateId, res)) return;
  const combate = db.prepare('SELECT historico_cursor FROM combates WHERE id = ?').get(combateId);
  const cursor = combate?.historico_cursor || 0;
  const canUndo = Boolean(db.prepare('SELECT id FROM historico_combate WHERE combate_id = ? AND id = ?').get(combateId, cursor));
  const canRedo = Boolean(db.prepare('SELECT id FROM historico_combate WHERE combate_id = ? AND id > ? ORDER BY id ASC LIMIT 1').get(combateId, cursor));
  res.json({ canUndo, canRedo });
});

router.post('/combates/:id/undo', (req, res) => {
  const combateId = req.params.id;
  if (!requireCombat(combateId, res)) return;
  const combate = db.prepare('SELECT historico_cursor FROM combates WHERE id = ?').get(combateId);
  const cursor = combate?.historico_cursor || 0;
  const current = db.prepare('SELECT * FROM historico_combate WHERE combate_id = ? AND id = ?').get(combateId, cursor);
  if (!current) return res.status(400).json({ error: 'Nada para desfazer.' });
  const previous = db.prepare('SELECT id FROM historico_combate WHERE combate_id = ? AND id < ? ORDER BY id DESC LIMIT 1').get(combateId, cursor);
  restoreCombat(current.antes);
  db.prepare('UPDATE combates SET historico_cursor = ? WHERE id = ?').run(previous?.id || 0, combateId);
  res.json({ ok: true, acao: current.acao, historico: { canUndo: Boolean(previous), canRedo: true } });
});

router.post('/combates/:id/redo', (req, res) => {
  const combateId = req.params.id;
  if (!requireCombat(combateId, res)) return;
  const combate = db.prepare('SELECT historico_cursor FROM combates WHERE id = ?').get(combateId);
  const cursor = combate?.historico_cursor || 0;
  const next = db.prepare('SELECT * FROM historico_combate WHERE combate_id = ? AND id > ? ORDER BY id ASC LIMIT 1').get(combateId, cursor);
  if (!next) return res.status(400).json({ error: 'Nada para refazer.' });
  restoreCombat(next.depois);
  db.prepare('UPDATE combates SET historico_cursor = ? WHERE id = ?').run(next.id, combateId);
  const following = db.prepare('SELECT id FROM historico_combate WHERE combate_id = ? AND id > ? ORDER BY id ASC LIMIT 1').get(combateId, next.id);
  res.json({ ok: true, acao: next.acao, historico: { canUndo: true, canRedo: Boolean(following) } });
});

export default router;
