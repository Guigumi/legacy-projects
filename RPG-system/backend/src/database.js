import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';
import { ATTRIBUTE_FIELDS, fitAttributes } from './character-attributes.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dbDir = process.env.RPG_SYSTEM_DATA_DIR || path.join(__dirname, '..', 'db');
if (!fs.existsSync(dbDir)) fs.mkdirSync(dbDir, { recursive: true });

const dbPath = path.join(dbDir, 'rpg_system.sqlite');
export const db = new DatabaseSync(dbPath);

db.exec('PRAGMA journal_mode = WAL;');
db.exec('PRAGMA foreign_keys = ON;');

export function initDatabase() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS racas (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL UNIQUE,
      buff_vida INTEGER DEFAULT 0,
      buff_mana INTEGER DEFAULT 0,
      buff_inteligencia INTEGER DEFAULT 0,
      buff_agilidade INTEGER DEFAULT 0,
      buff_vigor INTEGER DEFAULT 0,
      descricao TEXT
    );

    CREATE TABLE IF NOT EXISTS armas (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL UNIQUE,
      buff_iniciativa INTEGER DEFAULT 0,
      buff_dano INTEGER DEFAULT 0,
      buff_desvio INTEGER DEFAULT 0,
      debuff_dano INTEGER DEFAULT 0,
      debuff_iniciativa INTEGER DEFAULT 0,
      debuff_mana INTEGER DEFAULT 0,
      descricao TEXT
    );

    CREATE TABLE IF NOT EXISTS magias (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL UNIQUE,
      custo INTEGER DEFAULT 0,
      tipo TEXT DEFAULT 'simples',
      descricao TEXT,
      observacao TEXT,
      categoria TEXT DEFAULT 'simples',
      efeitos TEXT DEFAULT '[]'
    );

    CREATE TABLE IF NOT EXISTS itens (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL UNIQUE,
      tipo TEXT,
      efeito TEXT,
      valor TEXT,
      efeitos TEXT DEFAULT '[]'
    );

    CREATE TABLE IF NOT EXISTS combates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL,
      rodada INTEGER DEFAULT 1,
      turno_atual_id INTEGER,
      status TEXT DEFAULT 'ativo',
      notas TEXT DEFAULT '',
      historico_cursor INTEGER DEFAULT 0,
      criado_em TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS participantes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      combate_id INTEGER NOT NULL,
      nome TEXT NOT NULL,
      tipo TEXT NOT NULL DEFAULT 'jogador',
      iniciativa INTEGER DEFAULT 0,
      hp_atual INTEGER DEFAULT 100,
      hp_max INTEGER DEFAULT 100,
      mp_atual INTEGER DEFAULT 100,
      mp_max INTEGER DEFAULT 100,
      turnos_jogados INTEGER DEFAULT 0,
      ordem INTEGER DEFAULT 0,
      personagem_id INTEGER,
      FOREIGN KEY (combate_id) REFERENCES combates(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS efeitos (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      combate_id INTEGER NOT NULL,
      nome TEXT NOT NULL,
      tipo TEXT NOT NULL DEFAULT 'magia',
      descricao TEXT DEFAULT '',
      alvo_id INTEGER,
      conjurador_id INTEGER,
      duracao INTEGER NOT NULL DEFAULT 1,
      decaimento TEXT NOT NULL DEFAULT 'alvo',
      criado_em TEXT DEFAULT (datetime('now')),
      FOREIGN KEY (combate_id) REFERENCES combates(id) ON DELETE CASCADE,
      FOREIGN KEY (alvo_id) REFERENCES participantes(id) ON DELETE CASCADE,
      FOREIGN KEY (conjurador_id) REFERENCES participantes(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS log_eventos (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      combate_id INTEGER NOT NULL,
      participante_id INTEGER,
      evento TEXT NOT NULL,
      detalhes TEXT,
      rodada INTEGER,
      criado_em TEXT DEFAULT (datetime('now')),
      FOREIGN KEY (combate_id) REFERENCES combates(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS personagens (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL,
      nome_jogador TEXT,
      raca TEXT,
      arma TEXT,
      nivel INTEGER DEFAULT 0,
      idade TEXT,
      aparencia TEXT,
      historia TEXT DEFAULT '',
      aliados TEXT DEFAULT '',
      status TEXT DEFAULT '',
      notas TEXT DEFAULT '',
      hp_max INTEGER DEFAULT 100,
      mp_max INTEGER DEFAULT 100,
      vida INTEGER DEFAULT 0,
      mana INTEGER DEFAULT 0,
      inteligencia INTEGER DEFAULT 0,
      agilidade INTEGER DEFAULT 0,
      vigor INTEGER DEFAULT 0,
      magias TEXT,
      inventario TEXT,
      is_preset INTEGER DEFAULT 0,
      criado_em TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS bestiario (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL,
      categoria TEXT DEFAULT 'inimigo',
      hp_max INTEGER DEFAULT 25,
      dano TEXT DEFAULT '',
      descricao TEXT DEFAULT '',
      mecanicas TEXT DEFAULT '',
      status TEXT DEFAULT '',
      is_preset INTEGER DEFAULT 0,
      criado_em TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS historico_combate (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      combate_id INTEGER NOT NULL,
      acao TEXT NOT NULL,
      antes TEXT NOT NULL,
      depois TEXT NOT NULL,
      criado_em TEXT DEFAULT (datetime('now')),
      FOREIGN KEY (combate_id) REFERENCES combates(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS roteiros (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      titulo TEXT NOT NULL,
      descricao TEXT DEFAULT '',
      criado_em TEXT DEFAULT (datetime('now')),
      atualizado_em TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS roteiro_cenas (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      roteiro_id INTEGER NOT NULL,
      titulo TEXT NOT NULL,
      conteudo TEXT DEFAULT '',
      musica_url TEXT DEFAULT '',
      musica_titulo TEXT DEFAULT '',
      ordem INTEGER DEFAULT 0,
      FOREIGN KEY (roteiro_id) REFERENCES roteiros(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS transmissao (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      mostrar_fila INTEGER DEFAULT 1,
      mostrar_logs INTEGER DEFAULT 1,
      imagem_url TEXT DEFAULT '',
      musica_url TEXT DEFAULT '',
      musica_titulo TEXT DEFAULT '',
      volume REAL DEFAULT 0.7,
      atualizado_em TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS rolagens (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      combate_id INTEGER,
      autor TEXT NOT NULL DEFAULT 'Mestre',
      expressao TEXT NOT NULL,
      resultado INTEGER NOT NULL,
      detalhes TEXT DEFAULT '',
      criado_em TEXT DEFAULT (datetime('now')),
      FOREIGN KEY (combate_id) REFERENCES combates(id) ON DELETE CASCADE
    );
  `);
  db.exec(`INSERT OR IGNORE INTO transmissao (id) VALUES (1)`);
  ensureColumn('personagens', 'historia', "TEXT DEFAULT ''");
  ensureColumn('personagens', 'aliados', "TEXT DEFAULT ''");
  ensureColumn('personagens', 'status', "TEXT DEFAULT ''");
  ensureColumn('personagens', 'notas', "TEXT DEFAULT ''");
  ensureColumn('bestiario', 'status', "TEXT DEFAULT ''");
  ensureColumn('magias', 'efeitos', "TEXT DEFAULT '[]'");
  ensureColumn('itens', 'efeitos', "TEXT DEFAULT '[]'");
  migrateCompendiumAccents();
  const updateAttributes = db.prepare(`UPDATE personagens SET ${ATTRIBUTE_FIELDS.map(field => `${field} = :${field}`).join(', ')} WHERE id = :id`);
  for (const character of db.prepare('SELECT * FROM personagens').all()) {
    updateAttributes.run({ ...fitAttributes(character, db), id: character.id });
  }

  ensureColumn('combates', 'notas', "TEXT DEFAULT ''");
  ensureColumn('combates', 'historico_cursor', 'INTEGER DEFAULT 0');
  ensureColumn('combates', 'fila_turnos', "TEXT DEFAULT '[]'");
  ensureColumn('combates', 'turno_atual_tipo', "TEXT DEFAULT 'participante'");
  ensureColumn('combates', 'turno_atual_efeito_id', 'INTEGER');
  ensureColumn('efeitos', 'tipo', "TEXT DEFAULT 'magia'");
  db.prepare("UPDATE efeitos SET tipo = 'evento', decaimento = 'evento' WHERE decaimento = 'magia' AND (tipo IS NULL OR tipo = 'magia')").run();
  db.prepare("UPDATE combates SET turno_atual_tipo = 'evento' WHERE turno_atual_tipo = 'magia'").run();
  ensureColumn('bestiario', 'foto', 'TEXT');
  ensureColumn('participantes', 'foto', 'TEXT');
  ensureColumn('participantes', 'personagem_id', 'INTEGER');
  ensureColumn('personagens', 'foto', 'TEXT');
  db.exec(`
    UPDATE personagens
    SET hp_max = 100 + (COALESCE(nivel, 0) * 10) + (COALESCE(vida, 0) * 10),
        mp_max = MAX(0, 100 + (COALESCE(nivel, 0) * 10) + (COALESCE(mana, 0) * 10) - COALESCE((
          SELECT COALESCE(debuff_mana, 0)
          FROM armas
          WHERE armas.nome = personagens.arma
        ), 0))
  `);
}

function ensureColumn(table, column, definition) {
  const columns = db.prepare(`PRAGMA table_info(${table})`).all();
  if (!columns.some(item => item.name === column)) {
    db.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${definition}`);
  }
}

function migrateCompendiumAccents() {
  const magicNames = [
    ['Transferencia', 'Transferência'],
    ['Resistencia', 'Resistência'],
    ['Regeneracao', 'Regeneração'],
    ['Estilhaco', 'Estilhaço'],
  ];
  const itemNames = [
    ['Pocao de cura pequena', 'Poção de cura pequena'],
    ['Pocao de cura grande', 'Poção de cura grande'],
    ['Pocao pequena de mana', 'Poção pequena de mana'],
  ];

  for (const [oldName, newName] of magicNames) renameCompendiumEntry('magias', oldName, newName);
  renameCompendiumEntry('magias', 'Campo da vida', 'Campo da Vida');
  for (const [oldName, newName] of itemNames) renameCompendiumEntry('itens', oldName, newName);
  renameCompendiumEntry('armas', 'Grimorio', 'Grimório');

  db.prepare("UPDATE magias SET categoria = 'básica', tipo = 'básica' WHERE categoria = 'basica' OR tipo = 'basica'").run();
  db.prepare("UPDATE itens SET tipo = 'poção' WHERE tipo = 'pocao'").run();
  db.prepare("UPDATE personagens SET arma = 'Grimório' WHERE arma = 'Grimorio'").run();
  for (const [oldName, newName] of [...magicNames, ['Grimorio', 'Grimório']]) {
    db.prepare('UPDATE personagens SET magias = REPLACE(COALESCE(magias, \'\'), ?, ?)').run(oldName, newName);
  }

  const defaultEffects = [
    ['Toque Vital (Vida 3)', [{ acao: 'cura_hp', alvo: 'alvo', valor: 25 }]],
    ['Toque Vital (Vida 5)', [{ acao: 'cura_hp', alvo: 'alvo', valor: 45 }]],
    ['Transferência', [{ acao: 'restaura_mp', alvo: 'alvo', valor: 25 }]],
    ['Roubo', [{ acao: 'drena_mp', alvo: 'alvo', valor: 50 }, { acao: 'restaura_mp', alvo: 'conjurador', valor: 50 }]],
  ];
  for (const [name, effects] of defaultEffects) {
    db.prepare("UPDATE magias SET efeitos = ? WHERE nome = ? AND (efeitos IS NULL OR efeitos = '[]')").run(JSON.stringify(effects), name);
  }

  const defaultItemEffects = [
    ['Poção de cura pequena', [{ acao: 'cura_hp', alvo: 'alvo', valor: 25 }]],
    ['Poção de cura grande', [{ acao: 'cura_hp', alvo: 'alvo', valor: 50 }]],
    ['Poção pequena de mana', [{ acao: 'restaura_mp', alvo: 'alvo', valor: 15 }]],
  ];
  for (const [name, effects] of defaultItemEffects) {
    db.prepare("UPDATE itens SET efeitos = ? WHERE nome = ? AND (efeitos IS NULL OR efeitos = '[]')").run(JSON.stringify(effects), name);
  }
}

function renameCompendiumEntry(table, oldName, newName) {
  const oldEntry = db.prepare(`SELECT id FROM ${table} WHERE nome = ?`).get(oldName);
  if (!oldEntry) return;
  const newEntry = db.prepare(`SELECT id FROM ${table} WHERE nome = ?`).get(newName);
  if (newEntry) db.prepare(`DELETE FROM ${table} WHERE id = ?`).run(oldEntry.id);
  else db.prepare(`UPDATE ${table} SET nome = ? WHERE id = ?`).run(newName, oldEntry.id);
}
