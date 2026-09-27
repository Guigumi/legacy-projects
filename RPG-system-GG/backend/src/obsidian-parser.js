import path from 'node:path';

const FIELD_ALIASES = {
  characterName: ['nome_personagem', 'personagem', 'character', 'nome'],
  playerName: ['nome_jogador', 'jogador', 'player', 'nome_do_jogador'],
  race: ['raca', 'race'],
  weapon: ['arma', 'weapon'],
  level: ['nivel', 'level'],
  age: ['idade', 'age'],
  appearance: ['aparencia', 'appearance'],
  history: ['historia', 'background', 'history', 'origem'],
  allies: ['aliados', 'aliado', 'allies', 'vinculos', 'vinculos'],
  status: ['status', 'condicoes', 'conditions'],
  notes: ['notas', 'notes', 'observacoes'],
  hp: ['vida', 'hp', 'pontos_de_vida', 'health'],
  hpCurrent: ['vida_atual', 'hp_atual', 'current_hp'],
  hpMax: ['vida_max', 'hp_max', 'max_hp', 'health_max'],
  mp: ['mana', 'mp', 'pontos_de_mana', 'magic_points'],
  mpCurrent: ['mana_atual', 'mp_atual', 'current_mp'],
  mpMax: ['mana_max', 'mp_max', 'max_mp'],
  intelligence: ['inteligencia', 'int', 'intelligence'],
  agility: ['agilidade', 'agi', 'agility'],
  vigor: ['vigor', 'vig'],
  spells: ['magias', 'magia', 'habilidades', 'spells', 'abilities'],
  inventory: ['inventario', 'inventory'],
  category: ['categoria', 'category', 'tipo', 'type'],
  damage: ['dano', 'damage', 'ataque', 'attack'],
  description: ['descricao', 'description', 'resumo', 'summary'],
  mechanics: ['mecanicas', 'mecanica', 'mechanics', 'habilidades_especiais'],
};

export function parseCharacterMarkdown(fileName, text) {
  const fields = extractFields(text);
  const baseName = baseFileName(fileName).replace(/^ficha\s*[-–:]\s*/i, '').trim();
  const characterName = firstField(fields, FIELD_ALIASES.characterName) || baseName;
  const playerName = firstField(fields, FIELD_ALIASES.playerName);
  const hp = readResource(fields, FIELD_ALIASES.hp, FIELD_ALIASES.hpCurrent, FIELD_ALIASES.hpMax, 100);
  const mp = readResource(fields, FIELD_ALIASES.mp, FIELD_ALIASES.mpCurrent, FIELD_ALIASES.mpMax, 100);
  const spells = parseSpells(text, fields);
  const hasData = Boolean(playerName || characterName || hp.current > 0 || mp.current > 0 || spells.length);
  if (!hasData) return null;

  return {
    nome: characterName,
    nome_jogador: playerName,
    raca: firstField(fields, FIELD_ALIASES.race),
    arma: firstField(fields, FIELD_ALIASES.weapon),
    nivel: readNumber(firstField(fields, FIELD_ALIASES.level), 0),
    idade: firstField(fields, FIELD_ALIASES.age),
    aparencia: firstField(fields, FIELD_ALIASES.appearance),
    historia: firstField(fields, FIELD_ALIASES.history) || firstSection(text, /hist[oó]ria|background|origem/i),
    aliados: firstField(fields, FIELD_ALIASES.allies),
    status: firstField(fields, FIELD_ALIASES.status),
    notas: firstField(fields, FIELD_ALIASES.notes),
    hp_max: hp.max,
    mp_max: mp.max,
    vida: Math.max(1, hp.current),
    mana: Math.max(1, mp.current),
    inteligencia: Math.max(1, readNumber(firstField(fields, FIELD_ALIASES.intelligence), 1)),
    agilidade: Math.max(1, readNumber(firstField(fields, FIELD_ALIASES.agility), 1)),
    vigor: Math.max(1, readNumber(firstField(fields, FIELD_ALIASES.vigor), 1)),
    magias: JSON.stringify(spells),
    inventario: section(text, /invent[aá]rio|inventory/i) || firstField(fields, FIELD_ALIASES.inventory),
    is_preset: 0,
  };
}

export function parseBestiaryMarkdown(fileName, text) {
  const fields = extractFields(text);
  const baseName = baseFileName(fileName).replace(/\s*[-–]\s*(boss|inimigo|enemy).*$/i, '').trim();
  const entries = [];
  const damage = firstField(fields, FIELD_ALIASES.damage) || findDamage(text);
  const description = firstField(fields, FIELD_ALIASES.description) || firstSection(text, /descri[cç][aã]o|description|resumo|summary/i);
  const mechanics = firstField(fields, FIELD_ALIASES.mechanics) || section(text, /mec[aâ]nicas?|mechanics|habilidades especiais|special abilities/i) || text.trim();
  const status = firstField(fields, FIELD_ALIASES.status);
  const bossRows = tableRows(text, /jogadores/i, /vida\s+do\s+chefe|boss\s+hp/i);
  const shadowRows = tableRows(text, /jogadores/i, /vida(?:\s+da)?\s+sombra|shadow\s+hp/i);

  if (bossRows.length > 0) {
    for (const row of bossRows) entries.push({
      nome: baseName,
      categoria: `boss - ${row.players} jogador${row.players === 1 ? '' : 'es'}`,
      hp_max: row.hp,
      dano: damage,
      descricao: description,
      mecanicas: mechanics,
      status,
      is_preset: 0,
    });
  }
  if (shadowRows.length > 0) {
    for (const row of shadowRows) entries.push({
      nome: 'Sombra',
      categoria: `inimigo - ${row.players} jogador${row.players === 1 ? '' : 'es'}`,
      hp_max: row.hp,
      dano: damage || 'ataque base manual',
      descricao: description,
      mecanicas: mechanics,
      status,
      is_preset: 0,
    });
  }
  if (entries.length > 0) return entries;

  const hp = readResource(fields, ['hp', 'vida', 'health'], ['hp_atual', 'vida_atual'], ['hp_max', 'vida_max', 'health_max'], 25);
  const name = firstField(fields, ['nome', 'inimigo', 'enemy', 'criatura', 'creature']) || baseName;
  if (!name) return [];
  return [{
    nome: name,
    categoria: firstField(fields, FIELD_ALIASES.category) || 'inimigo',
    hp_max: hp.max,
    dano: damage,
    descricao: description,
    mecanicas: mechanics,
    status,
    is_preset: 0,
  }];
}

function extractFields(text) {
  const fields = new Map();
  const add = (key, value) => {
    const normalizedKey = normalizeKey(key);
    const normalizedValue = cleanValue(value);
    if (normalizedKey && normalizedValue && !fields.has(normalizedKey)) fields.set(normalizedKey, normalizedValue);
  };

  const frontmatter = text.match(/^---\s*\n([\s\S]*?)\n---\s*(?:\n|$)/);
  if (frontmatter) {
    for (const line of frontmatter[1].split(/\r?\n/)) {
      const match = line.match(/^\s*([^:#]+?)\s*:\s*(.*?)\s*$/);
      if (match) add(match[1], match[2]);
    }
  }

  for (const line of text.split(/\r?\n/)) {
    const inline = line.match(/^\s*(?:[-*+]\s*)?(?:\*\*)?([^:|]+?)(?:\*\*)?\s*::\s*(.*?)\s*$/);
    const colon = line.match(/^\s*(?:[-*+]\s*)?(?:\*\*)?([^:|]+?)(?:\*\*)?\s*:\s*(.*?)\s*$/);
    const match = inline || colon;
    if (match) add(match[1], match[2]);

    const cells = tableCells(line);
    if (cells.length >= 2 && !cells.every(cell => /^[-\s:]+$/.test(cell))) add(cells[0], cells[1]);
  }
  return fields;
}

function parseSpells(text, fields) {
  const names = [];
  const add = value => {
    const clean = cleanValue(value).replace(/^[-*+]\s+/, '').replace(/^\*\*(.*?)\*\*$/, '$1');
    if (!clean || /^(nome|magia|spell|habilidade|ability|descri[cç][aã]o)$/i.test(clean) || /^[-|\s]+$/.test(clean)) return;
    if (!names.some(name => normalizeKey(name) === normalizeKey(clean))) names.push(clean);
  };

  const configured = firstField(fields, FIELD_ALIASES.spells);
  for (const value of parseList(configured)) add(value);
  const spellSection = section(text, /magias?|habilidades?|spells?|abilities?/i);
  for (const line of spellSection.split(/\r?\n/)) {
    const cells = tableCells(line);
    if (cells.length >= 2) add(cells[0]);
    const bullet = line.match(/^\s*[-*+]\s+(?:\*\*)?([^|:]+?)(?:\*\*)?(?:\s*:.*)?\s*$/);
    if (bullet) add(bullet[1]);
  }
  return names;
}

function readResource(fields, valueAliases, currentAliases, maxAliases, fallback) {
  const value = firstField(fields, valueAliases);
  const currentValue = firstField(fields, currentAliases);
  const maxValue = firstField(fields, maxAliases);
  const status = parseStatus(value || currentValue);
  const current = status?.current ?? readNumber(currentValue || value, 0);
  const max = readNumber(maxValue, status?.max || readNumber(value, 0) || fallback);
  return { current, max: Math.max(0, max) };
}

function tableRows(text, firstHeader, secondHeader) {
  const headerPattern = new RegExp(`\\|\\s*${firstHeader.source}\\s*\\|\\s*${secondHeader.source}\\s*\\|`, 'i');
  const start = text.search(headerPattern);
  if (start < 0) return [];
  const remainder = text.slice(start);
  const nextHeading = remainder.search(/\n#{1,6}\s/);
  const scope = nextHeading > 0 ? remainder.slice(0, nextHeading) : remainder;
  return [...scope.matchAll(/\|\s*(\d+)\s*\|\s*(\d+)\s*HP\s*\|/gi)].map(match => ({ players: Number(match[1]), hp: Number(match[2]) }));
}

function findDamage(text) {
  return [...text.matchAll(/\|\s*[^|]+\s*\|\s*(\d+\s*[–-]\s*\d+)\s*\|/g)].map(match => match[1].replace('–', '-')).join(' / ');
}

function section(text, headingPattern) {
  const match = text.match(new RegExp(`^#{1,6}[^\\n]*(?:${headingPattern.source})[^\\n]*\\n([\\s\\S]*?)(?=^#{1,6}\\s|(?![\\s\\S]))`, 'im'));
  return match?.[1]?.trim() || '';
}

function firstSection(text, headingPattern) {
  return section(text, headingPattern).split(/\r?\n/).map(line => line.trim()).filter(Boolean)[0] || '';
}

function firstField(fields, aliases) {
  for (const alias of aliases) {
    const value = fields.get(normalizeKey(alias));
    if (value) return value;
  }
  return '';
}

function parseList(value) {
  if (!value) return [];
  const text = String(value).trim();
  try {
    const parsed = JSON.parse(text.replace(/'/g, '"'));
    if (Array.isArray(parsed)) return parsed;
  } catch { /* aceita listas simples do Obsidian */ }
  return text.replace(/^\[|\]$/g, '').split(/[,;\n]/).map(item => item.trim()).filter(Boolean);
}

function parseStatus(value) {
  const match = String(value || '').match(/(-?\d+(?:[.,]\d+)?)\s*\/\s*(-?\d+(?:[.,]\d+)?)/);
  return match ? { current: readNumber(match[1], 0), max: readNumber(match[2], 0) } : null;
}

function readNumber(value, fallback) {
  const match = String(value ?? '').replace(',', '.').match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : fallback;
}

function tableCells(line) {
  if (!/^\s*\|/.test(line)) return [];
  return line.split('|').slice(1, -1).map(cell => cleanValue(cell));
}

function cleanValue(value) {
  return String(value ?? '').trim().replace(/^['"]|['"]$/g, '').replace(/\s+$/, '');
}

function normalizeKey(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .replace(/[\*`]/g, '')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

function baseFileName(fileName) {
  return path.basename(String(fileName || 'arquivo.md')).replace(/\.(md|markdown)$/i, '').trim();
}
