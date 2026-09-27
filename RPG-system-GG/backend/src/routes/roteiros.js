import { Router } from 'express';
import { db } from '../database.js';
import { validateIdParam } from './validate-id.js';

const router = validateIdParam(Router());

router.get('/roteiros', (req, res) => {
  const roteiros = db.prepare('SELECT * FROM roteiros ORDER BY atualizado_em DESC, id DESC').all();
  const cenas = db.prepare('SELECT * FROM roteiro_cenas ORDER BY ordem ASC, id ASC').all();
  res.json(roteiros.map(roteiro => ({ ...roteiro, cenas: cenas.filter(cena => cena.roteiro_id === roteiro.id) })));
});

router.post('/roteiros', (req, res) => {
  const titulo = typeof req.body?.titulo === 'string' ? req.body.titulo.trim() : '';
  if (!titulo) return res.status(400).json({ error: 'Informe o título do roteiro.' });
  const info = db.prepare('INSERT INTO roteiros (titulo, descricao) VALUES (?, ?)').run(titulo, String(req.body.descricao || ''));
  res.status(201).json({ id: Number(info.lastInsertRowid) });
});

router.put('/roteiros/:id', (req, res) => {
  const roteiro = db.prepare('SELECT id FROM roteiros WHERE id = ?').get(req.params.id);
  if (!roteiro) return res.status(404).json({ error: 'Roteiro não encontrado.' });
  const fields = [];
  const values = { id: req.params.id };
  for (const field of ['titulo', 'descricao']) {
    if (req.body[field] !== undefined) {
      fields.push(`${field} = :${field}`);
      values[field] = String(req.body[field]);
    }
  }
  if (fields.length > 0) fields.push("atualizado_em = datetime('now')");
  if (fields.length > 0) db.prepare(`UPDATE roteiros SET ${fields.join(', ')} WHERE id = :id`).run(values);
  res.json({ ok: true });
});

router.delete('/roteiros/:id', (req, res) => {
  db.prepare('DELETE FROM roteiros WHERE id = ?').run(req.params.id);
  res.json({ ok: true });
});

router.post('/roteiros/:id/cenas', (req, res) => {
  const roteiro = db.prepare('SELECT id FROM roteiros WHERE id = ?').get(req.params.id);
  const titulo = typeof req.body?.titulo === 'string' ? req.body.titulo.trim() : '';
  if (!roteiro) return res.status(404).json({ error: 'Roteiro não encontrado.' });
  if (!titulo) return res.status(400).json({ error: 'Informe o título da cena.' });
  const ordem = db.prepare('SELECT COALESCE(MAX(ordem), -1) + 1 AS ordem FROM roteiro_cenas WHERE roteiro_id = ?').get(req.params.id).ordem;
  const info = db.prepare('INSERT INTO roteiro_cenas (roteiro_id, titulo, conteudo, musica_url, musica_titulo, ordem) VALUES (?, ?, ?, ?, ?, ?)').run(req.params.id, titulo, String(req.body.conteudo || ''), String(req.body.musica_url || ''), String(req.body.musica_titulo || ''), ordem);
  db.prepare("UPDATE roteiros SET atualizado_em = datetime('now') WHERE id = ?").run(req.params.id);
  res.status(201).json({ id: Number(info.lastInsertRowid) });
});

router.put('/roteiro-cenas/:id', (req, res) => {
  const fields = [];
  const values = { id: req.params.id };
  for (const field of ['titulo', 'conteudo', 'musica_url', 'musica_titulo', 'ordem']) {
    if (req.body[field] !== undefined) {
      fields.push(`${field} = :${field}`);
      values[field] = field === 'ordem' ? Number(req.body[field]) || 0 : String(req.body[field]);
    }
  }
  if (fields.length > 0) db.prepare(`UPDATE roteiro_cenas SET ${fields.join(', ')} WHERE id = :id`).run(values);
  res.json({ ok: true });
});

router.delete('/roteiro-cenas/:id', (req, res) => {
  db.prepare('DELETE FROM roteiro_cenas WHERE id = ?').run(req.params.id);
  res.json({ ok: true });
});

export default router;
