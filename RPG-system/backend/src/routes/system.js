import { Router } from 'express';
import { exportBackup, importBackup } from '../backup.js';

const router = Router();

router.get('/backup/export', (req, res) => {
  const filename = `rpg-system-gg-backup-${new Date().toISOString().slice(0, 10)}.json`;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
  res.json(exportBackup());
});

router.post('/backup/import', (req, res) => {
  try {
    importBackup(req.body);
    res.json({ ok: true });
  } catch (error) {
    res.status(400).json({ error: error instanceof Error ? error.message : 'Falha ao importar backup.' });
  }
});

export default router;
