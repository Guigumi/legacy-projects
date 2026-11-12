import { Router } from 'express';
import { db } from '../database.js';
import { validateIdParam } from './validate-id.js';

const router = validateIdParam(Router());

router.get('/bestiario', (req, res) => {
  res.json(db.prepare('SELECT * FROM bestiario ORDER BY is_preset DESC, categoria ASC, nome ASC').all());
});

router.post('/bestiario', (req, res) => {
  const { nome, categoria, hp_max, dano, descricao, mecanicas, status } = req.body || {};
  if (typeof nome !== 'string' || !nome.trim()) {
    return res.status(400).json({ error: 'Informe o nome do inimigo.' });
  }
  const info = db.prepare(`INSERT INTO bestiario (nome, categoria, hp_max, dano, descricao, mecanicas, status, is_preset) VALUES (:nome,:categoria,:hp_max,:dano,:descricao,:mecanicas,:status,0)`).run({ nome, categoria: categoria || 'inimigo', hp_max: hp_max || 25, dano: dano || '', descricao: descricao || '', mecanicas: mecanicas || '', status: status || '' });
  res.json({ id: Number(info.lastInsertRowid) });
});

router.put('/bestiario/:id', (req, res) => {
  const campos = ['nome', 'categoria', 'hp_max', 'dano', 'descricao', 'mecanicas', 'status'];
  const sets = [];
  const vals = { id: req.params.id };
  for (const campo of campos) {
    if (req.body[campo] !== undefined) {
      sets.push(`${campo} = :${campo}`);
      vals[campo] = req.body[campo];
    }
  }
  if (sets.length > 0) db.prepare(`UPDATE bestiario SET ${sets.join(', ')} WHERE id = :id`).run(vals);
  res.json({ ok: true });
});

router.delete('/bestiario/:id', (req, res) => {
  db.prepare('DELETE FROM bestiario WHERE id = ? AND is_preset = 0').run(req.params.id);
  res.json({ ok: true });
});

router.post('/bestiario/:id/foto', (req, res) => {
  const foto = String(req.body?.foto || '');
  if (!foto.startsWith('data:image/')) return res.status(400).json({ error: 'Imagem inválida.' });
  if (foto.length > 900000) return res.status(400).json({ error: 'Imagem muito grande (máximo de aproximadamente 600 KB).' });
  db.prepare('UPDATE bestiario SET foto = ? WHERE id = ?').run(foto, req.params.id);
  res.json({ ok: true });
});

router.delete('/bestiario/:id/foto', (req, res) => {
  db.prepare('UPDATE bestiario SET foto = NULL WHERE id = ?').run(req.params.id);
  res.json({ ok: true });
});

export default router;
