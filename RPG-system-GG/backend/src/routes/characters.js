import { Router } from 'express';
import { db } from '../database.js';
import { calculateCharacterResources } from '../character-stats.js';
import { ATTRIBUTE_FIELDS, validateAttributes } from '../character-attributes.js';
import { validateIdParam } from './validate-id.js';

const router = validateIdParam(Router());

router.get('/personagens', (req, res) => {
  res.json(db.prepare('SELECT * FROM personagens ORDER BY is_preset DESC, nome ASC').all());
});

router.post('/personagens', (req, res) => {
  if (typeof req.body?.nome !== 'string' || !req.body.nome.trim()) {
    return res.status(400).json({ error: 'Informe o nome da ficha.' });
  }
  const campos = ['nome', 'nome_jogador', 'raca', 'arma', 'nivel', 'idade', 'aparencia', 'historia', 'aliados', 'status', 'notas', 'hp_max', 'mp_max', 'vida', 'mana', 'inteligencia', 'agilidade', 'vigor', 'magias', 'inventario', 'is_preset'];
  const keys = campos.filter(c => req.body[c] !== undefined);
  const vals = {};
  for (const c of keys) vals[c] = req.body[c];
  for (const field of ATTRIBUTE_FIELDS) {
    if (vals[field] === undefined) vals[field] = 1;
    if (!keys.includes(field)) keys.push(field);
  }
  const attributeError = validateAttributes(vals, db);
  if (attributeError) return res.status(400).json({ error: attributeError });
  Object.assign(vals, calculateCharacterResources(vals, db));
  if (!keys.includes('hp_max')) keys.push('hp_max');
  if (!keys.includes('mp_max')) keys.push('mp_max');
  if (vals.is_preset !== undefined) vals.is_preset = vals.is_preset ? 1 : 0;
  const placeholders = keys.map(c => `:${c}`).join(', ');
  const colNames = keys.join(', ');
  const info = db.prepare(`INSERT INTO personagens (${colNames}) VALUES (${placeholders})`).run(vals);
  res.json({ id: Number(info.lastInsertRowid) });
});

router.put('/personagens/:id', (req, res) => {
  const current = db.prepare('SELECT * FROM personagens WHERE id = ?').get(req.params.id);
  if (!current) return res.status(404).json({ error: 'Ficha não encontrada.' });
  const campos = ['nome', 'nome_jogador', 'raca', 'arma', 'nivel', 'idade', 'aparencia', 'historia', 'aliados', 'status', 'notas', 'magias', 'inventario', 'is_preset'];
  const sets = [];
  const vals = { id: req.params.id };
  for (const c of campos) {
    if (req.body[c] !== undefined) {
      sets.push(`${c} = :${c}`);
      vals[c] = c === 'is_preset' ? (req.body[c] ? 1 : 0) : req.body[c];
    }
  }
  const nextCharacter = { ...current, ...req.body };
  const attributeError = validateAttributes(nextCharacter, db);
  if (attributeError) return res.status(400).json({ error: attributeError });
  for (const field of ATTRIBUTE_FIELDS) {
    sets.push(`${field} = :${field}`);
    vals[field] = nextCharacter[field];
  }
  Object.assign(vals, calculateCharacterResources(nextCharacter, db));
  sets.push('hp_max = :hp_max', 'mp_max = :mp_max');
  if (sets.length === 0) return res.json({ ok: true });
  db.prepare(`UPDATE personagens SET ${sets.join(', ')} WHERE id = :id`).run(vals);
  res.json({ ok: true });
});

router.delete('/personagens/:id', (req, res) => {
  db.prepare('DELETE FROM personagens WHERE id = ?').run(req.params.id);
  res.json({ ok: true });
});

router.post('/personagens/:id/foto', (req, res) => {
  const foto = String(req.body?.foto || '');
  if (!foto.startsWith('data:image/')) return res.status(400).json({ error: 'Imagem inválida.' });
  if (foto.length > 900000) return res.status(400).json({ error: 'Imagem muito grande (máximo de aproximadamente 600 KB).' });
  db.prepare('UPDATE personagens SET foto = ? WHERE id = ?').run(foto, req.params.id);
  res.json({ ok: true });
});

router.delete('/personagens/:id/foto', (req, res) => {
  db.prepare('UPDATE personagens SET foto = NULL WHERE id = ?').run(req.params.id);
  res.json({ ok: true });
});

export default router;
