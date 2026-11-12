import { Router } from 'express';
import { db } from '../database.js';
import { validateIdParam } from './validate-id.js';

const router = validateIdParam(Router());

router.get('/racas', (req, res) => {
  res.json(db.prepare('SELECT * FROM racas ORDER BY nome ASC').all());
});

router.put('/racas/:id', (req, res) => {
  db.prepare(`UPDATE racas SET nome=:nome, buff_vida=:buff_vida, buff_mana=:buff_mana, buff_inteligencia=:buff_inteligencia, buff_agilidade=:buff_agilidade, buff_vigor=:buff_vigor, descricao=:descricao WHERE id=:id`).run({ ...req.body, id: req.params.id });
  res.json({ ok: true });
});

router.get('/armas', (req, res) => {
  res.json(db.prepare('SELECT * FROM armas ORDER BY nome ASC').all());
});

router.put('/armas/:id', (req, res) => {
  db.prepare(`UPDATE armas SET nome=:nome, buff_iniciativa=:buff_iniciativa, buff_dano=:buff_dano, buff_desvio=:buff_desvio, debuff_dano=:debuff_dano, debuff_iniciativa=:debuff_iniciativa, debuff_mana=:debuff_mana, descricao=:descricao WHERE id=:id`).run({ ...req.body, id: req.params.id });
  res.json({ ok: true });
});

router.get('/magias', (req, res) => {
  res.json(db.prepare('SELECT * FROM magias ORDER BY categoria ASC, nome ASC').all());
});

router.put('/magias/:id', (req, res) => {
  const current = db.prepare('SELECT * FROM magias WHERE id = ?').get(req.params.id);
  if (!current) return res.status(404).json({ error: 'Magia não encontrada.' });
  const next = { ...current, ...req.body };
  const efeitos = JSON.stringify(Array.isArray(req.body?.efeitos) ? req.body.efeitos : parseEffects(current.efeitos));
  db.prepare(`UPDATE magias SET nome=:nome, custo=:custo, tipo=:tipo, descricao=:descricao, observacao=:observacao, categoria=:categoria, efeitos=:efeitos WHERE id=:id`).run({ nome: next.nome, custo: next.custo, tipo: next.tipo, descricao: next.descricao, observacao: next.observacao, categoria: next.categoria, efeitos, id: req.params.id });
  res.json({ ok: true });
});

router.post('/magias', (req, res) => {
  if (typeof req.body?.nome !== 'string' || !req.body.nome.trim()) {
    return res.status(400).json({ error: 'Informe o nome da magia.' });
  }
  const info = db.prepare(`INSERT INTO magias (nome, custo, tipo, descricao, observacao, categoria, efeitos) VALUES (:nome,:custo,:tipo,:descricao,:observacao,:categoria,:efeitos)`).run({ ...req.body, efeitos: JSON.stringify(Array.isArray(req.body?.efeitos) ? req.body.efeitos : []) });
  res.json({ id: info.lastInsertRowid });
});

router.delete('/magias/:id', (req, res) => {
  db.prepare('DELETE FROM magias WHERE id = ?').run(req.params.id);
  res.json({ ok: true });
});

router.get('/itens', (req, res) => {
  res.json(db.prepare('SELECT * FROM itens ORDER BY nome ASC').all());
});

router.put('/itens/:id', (req, res) => {
  const current = db.prepare('SELECT * FROM itens WHERE id = ?').get(req.params.id);
  if (!current) return res.status(404).json({ error: 'Item não encontrado.' });
  const next = { ...current, ...req.body };
  const nextEffects = Array.isArray(req.body?.efeitos) ? req.body.efeitos : parseEffects(current.efeitos);
  if (containsHalf(nextEffects)) return res.status(400).json({ error: '{half} só pode ser usado em magias.' });
  const efeitos = JSON.stringify(nextEffects);
  db.prepare(`UPDATE itens SET nome=:nome, tipo=:tipo, efeito=:efeito, valor=:valor, efeitos=:efeitos WHERE id=:id`).run({ nome: next.nome, tipo: next.tipo, efeito: next.efeito, valor: next.valor, efeitos, id: req.params.id });
  res.json({ ok: true });
});

router.post('/itens', (req, res) => {
  if (typeof req.body?.nome !== 'string' || !req.body.nome.trim()) {
    return res.status(400).json({ error: 'Informe o nome do item.' });
  }
  const nextEffects = Array.isArray(req.body?.efeitos) ? req.body.efeitos : [];
  if (containsHalf(nextEffects)) return res.status(400).json({ error: '{half} só pode ser usado em magias.' });
  const info = db.prepare(`INSERT INTO itens (nome, tipo, efeito, valor, efeitos) VALUES (:nome,:tipo,:efeito,:valor,:efeitos)`).run({ ...req.body, efeitos: JSON.stringify(nextEffects) });
  res.json({ id: info.lastInsertRowid });
});

router.delete('/itens/:id', (req, res) => {
  db.prepare('DELETE FROM itens WHERE id = ?').run(req.params.id);
  res.json({ ok: true });
});

export default router;

function parseEffects(value) {
  try {
    const parsed = JSON.parse(value || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function containsHalf(effects) {
  return effects.some(effect => String(effect?.valor || '').trim().toLowerCase() === '{half}');
}
