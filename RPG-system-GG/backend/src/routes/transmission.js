import { Router } from 'express';
import { db } from '../database.js';
import { getPlayerState } from '../player-state.js';

const router = Router();

router.get('/transmissao', (req, res) => res.json(db.prepare('SELECT * FROM transmissao WHERE id = 1').get()));

router.put('/transmissao', (req, res) => {
  const data = req.body || {};
  for (const field of ['musica_url', 'musica_titulo', 'imagem_url']) {
    if (data[field] !== undefined && typeof data[field] !== 'string') return res.status(400).json({ error: `O campo ${field} é inválido.` });
  }
  for (const field of ['musica_url', 'imagem_url']) {
    if (data[field] && !/^https?:\/\//i.test(data[field])) return res.status(400).json({ error: 'Use URLs iniciadas por http:// ou https://.' });
  }
  const updates = [];
  const values = { id: 1 };
  for (const field of ['mostrar_fila', 'mostrar_logs', 'musica_url', 'musica_titulo', 'imagem_url', 'volume']) {
    if (data[field] !== undefined) {
      updates.push(`${field} = :${field}`);
      values[field] = field === 'volume' ? Math.max(0, Math.min(1, Number(data[field]) || 0)) : field.startsWith('mostrar_') ? (data[field] ? 1 : 0) : String(data[field]);
    }
  }
  if (updates.length > 0) {
    updates.push("atualizado_em = datetime('now')");
    db.prepare(`UPDATE transmissao SET ${updates.join(', ')} WHERE id = :id`).run(values);
  }
  res.json(db.prepare('SELECT * FROM transmissao WHERE id = 1').get());
});

router.get('/transmissao/rolagens', (req, res) => {
  res.json(db.prepare('SELECT * FROM rolagens ORDER BY id DESC LIMIT 50').all().reverse());
});

router.post('/transmissao/rolagens', (req, res) => {
  const { combate_id, autor, expressao, resultado, detalhes } = req.body || {};
  if (!expressao || !Number.isFinite(Number(resultado))) return res.status(400).json({ error: 'Rolagem inválida.' });
  const info = db.prepare('INSERT INTO rolagens (combate_id, autor, expressao, resultado, detalhes) VALUES (?, ?, ?, ?, ?)').run(combate_id || null, String(autor || 'Mestre'), String(expressao), Number(resultado), String(detalhes || ''));
  res.status(201).json({ id: Number(info.lastInsertRowid) });
});

router.delete('/transmissao/rolagens', (req, res) => {
  db.prepare('DELETE FROM rolagens').run();
  res.json({ ok: true });
});

export default router;
