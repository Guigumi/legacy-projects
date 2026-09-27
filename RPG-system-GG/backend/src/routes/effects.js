import { Router } from 'express';
import { db } from '../database.js';
import { captureCombat, recordCombatHistory, registrarLog } from '../combat-service.js';
import { applyMechanics } from '../mechanics.js';
import { effectToken, participantToken, queueForCombat, saveQueue } from '../turn-queue.js';
import { validateIdParam } from './validate-id.js';

const router = validateIdParam(Router());

router.post('/combates/:id/magia-instantanea', (req, res) => {
  const combateId = req.params.id;
  const combate = db.prepare('SELECT * FROM combates WHERE id = ?').get(combateId);
  const participanteId = Number(req.body?.participante_id);
  const magiaId = Number(req.body?.magia_id);
  const participante = db.prepare('SELECT * FROM participantes WHERE id = ? AND combate_id = ?').get(participanteId, combateId);
  const magia = db.prepare('SELECT * FROM magias WHERE id = ?').get(magiaId);
  if (!combate) return res.status(404).json({ error: 'Combate não encontrado.' });
  if (!participante || !magia) return res.status(400).json({ error: 'Participante ou magia inválido.' });

  const custo = req.body?.custo === undefined ? Number(magia.custo || 0) : Number(req.body.custo);
  if (!Number.isInteger(custo) || custo < 0) return res.status(400).json({ error: 'Custo de mana inválido.' });
  if (participante.mp_atual < custo) return res.status(400).json({ error: 'Mana insuficiente para lançar essa magia.' });

  const alvoId = req.body?.alvo_id ? Number(req.body.alvo_id) : null;
  if (alvoId && !db.prepare('SELECT id FROM participantes WHERE id = ? AND combate_id = ?').get(alvoId, combateId)) {
    return res.status(400).json({ error: 'Alvo inválido.' });
  }

  const antes = captureCombat(combateId);
  try {
    db.exec('BEGIN');
    db.prepare('UPDATE participantes SET mp_atual = mp_atual - ? WHERE id = ?').run(custo, participanteId);
    const alvo = alvoId ? db.prepare('SELECT nome FROM participantes WHERE id = ?').get(alvoId) : null;
    const applied = applyMechanics(combateId, participanteId, alvoId, magia.efeitos, { allowHalf: true });
    const details = `${participante.nome} usou ${magia.nome}${alvo ? ` em ${alvo.nome}` : ''}${custo > 0 ? ` (-${custo} MP)` : ''}${applied.length ? `: ${applied.join('; ')}` : ''}`;
    registrarLog(combateId, participanteId, 'magia_instantanea', details, combate.rodada);
    recordCombatHistory(combateId, 'magia_instantanea', antes);
    db.exec('COMMIT');
    res.json({ ok: true, participante_id: participanteId, magia_id: magiaId, custo, mp_atual: participante.mp_atual - custo, applied });
  } catch (error) {
    try { db.exec('ROLLBACK'); } catch {}
    res.status(400).json({ error: error.message || 'Não foi possível usar a magia.' });
  }
});

router.post('/combates/:id/item-instantaneo', (req, res) => {
  const combateId = req.params.id;
  const combate = db.prepare('SELECT * FROM combates WHERE id = ?').get(combateId);
  const participanteId = Number(req.body?.participante_id);
  const itemId = Number(req.body?.item_id);
  const participante = db.prepare('SELECT * FROM participantes WHERE id = ? AND combate_id = ?').get(participanteId, combateId);
  const item = db.prepare('SELECT * FROM itens WHERE id = ?').get(itemId);
  if (!combate) return res.status(404).json({ error: 'Combate não encontrado.' });
  if (!participante || !item) return res.status(400).json({ error: 'Participante ou item inválido.' });

  const alvoId = req.body?.alvo_id ? Number(req.body.alvo_id) : null;
  if (alvoId && !db.prepare('SELECT id FROM participantes WHERE id = ? AND combate_id = ?').get(alvoId, combateId)) {
    return res.status(400).json({ error: 'Alvo inválido.' });
  }

  const antes = captureCombat(combateId);
  try {
    db.exec('BEGIN');
    const alvo = alvoId ? db.prepare('SELECT nome FROM participantes WHERE id = ?').get(alvoId) : null;
    const applied = applyMechanics(combateId, participanteId, alvoId, item.efeitos);
    const details = `${participante.nome} usou ${item.nome}${alvo ? ` em ${alvo.nome}` : ''}${applied.length ? `: ${applied.join('; ')}` : ''}`;
    registrarLog(combateId, participanteId, 'item_usado', details, combate.rodada);
    recordCombatHistory(combateId, 'item_usado', antes);
    db.exec('COMMIT');
    res.json({ ok: true, participante_id: participanteId, item_id: itemId, applied });
  } catch (error) {
    try { db.exec('ROLLBACK'); } catch {}
    res.status(400).json({ error: error.message || 'Não foi possível usar o item.' });
  }
});

router.get('/combates/:id/efeitos', (req, res) => {
  const combate = db.prepare('SELECT id FROM combates WHERE id = ?').get(req.params.id);
  if (!combate) return res.status(404).json({ error: 'Combate não encontrado.' });
  res.json(db.prepare('SELECT * FROM efeitos WHERE combate_id = ? ORDER BY id ASC').all(req.params.id));
});

router.post('/combates/:id/efeitos', (req, res) => {
  const combateId = req.params.id;
  const combate = db.prepare('SELECT * FROM combates WHERE id = ?').get(combateId);
  if (!combate) return res.status(404).json({ error: 'Combate não encontrado.' });
  const nome = typeof req.body?.nome === 'string' ? req.body.nome.trim() : '';
  const tipo = req.body?.tipo === 'evento' ? 'evento' : 'magia';
  const duracao = Number(req.body?.duracao);
  const decaimento = tipo === 'evento' ? 'evento' : (['alvo', 'conjurador'].includes(req.body?.decaimento) ? req.body.decaimento : 'alvo');
  if (!nome) return res.status(400).json({ error: 'Informe o nome da magia ou efeito.' });
  if (!Number.isInteger(duracao) || duracao < 1 || duracao > 999) return res.status(400).json({ error: 'A duração deve estar entre 1 e 999 turnos.' });

  const alvoId = req.body?.alvo_id ? Number(req.body.alvo_id) : null;
  const conjuradorId = req.body?.conjurador_id ? Number(req.body.conjurador_id) : null;
  if (tipo === 'magia' && decaimento === 'alvo' && !alvoId) return res.status(400).json({ error: 'Escolha quem recebeu o efeito.' });
  if (tipo === 'magia' && decaimento === 'conjurador' && !conjuradorId) return res.status(400).json({ error: 'Informe quem conjurou o efeito.' });
  for (const id of [alvoId, conjuradorId].filter(Boolean)) {
    if (!db.prepare('SELECT id FROM participantes WHERE id = ? AND combate_id = ?').get(id, combateId)) {
      return res.status(400).json({ error: 'Esse participante não pertence ao combate.' });
    }
  }

  const antes = captureCombat(combateId);
  const info = db.prepare('INSERT INTO efeitos (combate_id, nome, tipo, descricao, alvo_id, conjurador_id, duracao, decaimento) VALUES (?, ?, ?, ?, ?, ?, ?, ?)').run(combateId, nome, tipo, String(req.body?.descricao || ''), alvoId, conjuradorId, duracao, decaimento);
  const efeitoId = Number(info.lastInsertRowid);
  if (tipo === 'evento') {
    const queue = queueForCombat(combateId);
    const token = effectToken(efeitoId);
    const casterIndex = conjuradorId ? queue.indexOf(participantToken(conjuradorId)) : -1;
    queue.splice(casterIndex >= 0 ? casterIndex + 1 : queue.length, 0, token);
    saveQueue(combateId, queue);
  }
  registrarLog(combateId, conjuradorId, 'efeito_criado', `${nome} aplicado por ${conjuradorId ? 'participante' : 'Mestre'} (${duracao} turno${duracao === 1 ? '' : 's'})`, combate.rodada);
  recordCombatHistory(combateId, 'efeito_criado', antes);
  res.status(201).json(db.prepare('SELECT * FROM efeitos WHERE id = ?').get(efeitoId));
});

router.delete('/efeitos/:id', (req, res) => {
  const efeito = db.prepare('SELECT * FROM efeitos WHERE id = ?').get(req.params.id);
  if (!efeito) return res.status(404).json({ error: 'Efeito não encontrado.' });
  const antes = captureCombat(efeito.combate_id);
  const queue = queueForCombat(efeito.combate_id).filter(token => token !== effectToken(efeito.id));
  db.prepare('DELETE FROM efeitos WHERE id = ?').run(efeito.id);
  saveQueue(efeito.combate_id, queue);
  recordCombatHistory(efeito.combate_id, 'efeito_removido', antes);
  res.json({ ok: true });
});

export default router;
