import { db } from './database.js';

const TABLES = ['racas', 'armas', 'magias', 'itens', 'combates', 'participantes', 'efeitos', 'log_eventos', 'personagens', 'bestiario', 'historico_combate', 'transmissao', 'roteiros', 'roteiro_cenas', 'rolagens'];
const CLEAR_ORDER = ['rolagens', 'roteiro_cenas', 'roteiros', 'transmissao', 'log_eventos', 'efeitos', 'historico_combate', 'participantes', 'combates', 'personagens', 'bestiario', 'magias', 'itens', 'armas', 'racas'];

export function exportBackup() {
  const tables = {};
  for (const table of TABLES) tables[table] = db.prepare(`SELECT * FROM ${table}`).all();
  return { format: 'rpg-system-gg-backup', version: 2, exportedAt: new Date().toISOString(), tables };
}

export function importBackup(backup) {
  if (!backup || backup.format !== 'rpg-system-gg-backup' || !backup.tables || typeof backup.tables !== 'object') {
    throw new Error('Arquivo de backup inválido.');
  }

  const schemas = new Map(TABLES.map(table => [table, new Set(db.prepare(`PRAGMA table_info(${table})`).all().map(column => column.name))]));
  db.exec('PRAGMA foreign_keys = OFF;');
  db.exec('BEGIN');
  try {
    for (const table of CLEAR_ORDER) db.exec(`DELETE FROM ${table}`);
    for (const table of TABLES) {
      const rows = Array.isArray(backup.tables[table]) ? backup.tables[table] : [];
      for (const row of rows) {
        if (!row || typeof row !== 'object') throw new Error(`Dados inválidos na tabela ${table}.`);
        const columns = Object.keys(row).filter(column => schemas.get(table).has(column));
        if (columns.length === 0) continue;
        const quoted = columns.map(column => `"${column}"`).join(', ');
        const placeholders = columns.map(() => '?').join(', ');
        db.prepare(`INSERT INTO ${table} (${quoted}) VALUES (${placeholders})`).run(...columns.map(column => row[column]));
      }
    }
    db.exec('INSERT OR IGNORE INTO transmissao (id) VALUES (1)');
    db.exec('COMMIT');
  } catch (error) {
    db.exec('ROLLBACK');
    throw error;
  } finally {
    db.exec('PRAGMA foreign_keys = ON;');
  }
}
