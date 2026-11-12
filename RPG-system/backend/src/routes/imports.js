import { Router } from 'express';
import { db } from '../database.js';
import { parseBestiaryMarkdown, parseCharacterMarkdown } from '../obsidian-parser.js';
import { calculateCharacterResources } from '../character-stats.js';
import { fitAttributes } from '../character-attributes.js';

const router = Router();
const MAX_FILES = 100;
const MAX_FILE_LENGTH = 2_000_000;

router.post('/import/obsidian/personagens', (req, res) => {
  const files = readFiles(req.body?.files, res);
  if (!files) return;
  const result = importFiles(files, parseCharacterMarkdown, upsertCharacter);
  res.json({ ok: true, tipo: 'personagens', ...result });
});

router.post('/import/obsidian/bestiario', (req, res) => {
  const files = readFiles(req.body?.files, res);
  if (!files) return;
  const result = importFiles(files, parseBestiaryMarkdown, upsertBestiary, true);
  res.json({ ok: true, tipo: 'bestiario', ...result });
});

function readFiles(value, res) {
  if (!Array.isArray(value) || value.length === 0) {
    res.status(400).json({ error: 'Selecione pelo menos um arquivo Markdown.' });
    return null;
  }
  if (value.length > MAX_FILES) {
    res.status(400).json({ error: `Selecione no máximo ${MAX_FILES} arquivos por importação.` });
    return null;
  }
  const files = value.filter(file => file && typeof file.name === 'string' && typeof file.content === 'string');
  if (files.length !== value.length) {
    res.status(400).json({ error: 'Um ou mais arquivos enviados são inválidos.' });
    return null;
  }
  if (files.some(file => !/\.(md|markdown)$/i.test(file.name))) {
    res.status(400).json({ error: 'A importação aceita apenas arquivos .md ou .markdown.' });
    return null;
  }
  if (files.some(file => file.content.length > MAX_FILE_LENGTH)) {
    res.status(400).json({ error: 'Cada arquivo pode ter no máximo 2 MB.' });
    return null;
  }
  return files;
}

function importFiles(files, parser, save, allowMultiple = false) {
  let importados = 0;
  let ignorados = 0;
  const detalhes = [];
  const seen = new Set();

  for (const file of files) {
    try {
      const parsed = parser(file.name, file.content) || [];
      const rows = Array.isArray(parsed) ? parsed : [parsed];
      let fileImported = 0;
      for (const row of rows) {
        if (!row?.nome?.trim()) continue;
        const key = allowMultiple ? `${row.nome}|${row.categoria || ''}` : row.nome;
        if (seen.has(key)) continue;
        seen.add(key);
        save(row);
        importados += 1;
        fileImported += 1;
      }
      if (fileImported === 0) ignorados += 1;
      detalhes.push({ arquivo: file.name, importados: fileImported });
    } catch (error) {
      ignorados += 1;
      detalhes.push({ arquivo: file.name, importados: 0, erro: error instanceof Error ? error.message : 'Formato não reconhecido.' });
    }
  }
  return { arquivos: files.length, importados, ignorados, detalhes };
}

function upsertCharacter(row) {
  row = { ...row, ...fitAttributes(row, db) };
  row = { ...row, ...calculateCharacterResources(row, db) };
  const values = { ...row };
  delete values.is_preset;
  const existing = db.prepare('SELECT id FROM personagens WHERE nome = ? ORDER BY id DESC LIMIT 1').get(row.nome);
  if (existing) {
    db.prepare(`UPDATE personagens SET nome_jogador=:nome_jogador, raca=:raca, arma=:arma, nivel=:nivel, idade=:idade, aparencia=:aparencia, historia=:historia, aliados=:aliados, status=:status, notas=:notas, hp_max=:hp_max, mp_max=:mp_max, vida=:vida, mana=:mana, inteligencia=:inteligencia, agilidade=:agilidade, vigor=:vigor, magias=:magias, inventario=:inventario, is_preset=0 WHERE id=:id`).run({ ...values, id: existing.id });
    return existing.id;
  }
  const info = db.prepare(`INSERT INTO personagens (nome, nome_jogador, raca, arma, nivel, idade, aparencia, historia, aliados, status, notas, hp_max, mp_max, vida, mana, inteligencia, agilidade, vigor, magias, inventario, is_preset) VALUES (:nome,:nome_jogador,:raca,:arma,:nivel,:idade,:aparencia,:historia,:aliados,:status,:notas,:hp_max,:mp_max,:vida,:mana,:inteligencia,:agilidade,:vigor,:magias,:inventario,0)`).run(values);
  return Number(info.lastInsertRowid);
}

function upsertBestiary(row) {
  const values = { ...row };
  delete values.is_preset;
  const existing = db.prepare('SELECT id FROM bestiario WHERE nome = ? AND categoria = ? ORDER BY id DESC LIMIT 1').get(row.nome, row.categoria);
  if (existing) {
    db.prepare('UPDATE bestiario SET hp_max=:hp_max, dano=:dano, descricao=:descricao, mecanicas=:mecanicas, status=:status, is_preset=0 WHERE id=:id').run({ ...values, id: existing.id });
    return existing.id;
  }
  const info = db.prepare('INSERT INTO bestiario (nome, categoria, hp_max, dano, descricao, mecanicas, status, is_preset) VALUES (:nome,:categoria,:hp_max,:dano,:descricao,:mecanicas,:status,0)').run(values);
  return Number(info.lastInsertRowid);
}

export default router;
