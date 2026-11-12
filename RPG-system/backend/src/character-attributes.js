export const ATTRIBUTE_FIELDS = ['vida', 'mana', 'inteligencia', 'agilidade', 'vigor'];

export function attributeState(character, db) {
  const race = findRace(character?.raca, db);
  const bases = {
    vida: 1 + number(race?.buff_vida),
    mana: 1 + number(race?.buff_mana),
    inteligencia: 1 + number(race?.buff_inteligencia),
    agilidade: 1 + number(race?.buff_agilidade),
    vigor: 1 + number(race?.buff_vigor),
  };
  const values = Object.fromEntries(ATTRIBUTE_FIELDS.map(field => [field, number(character?.[field], 1)]));
  const spent = ATTRIBUTE_FIELDS.reduce((total, field) => total + Math.max(0, values[field] - bases[field]), 0);
  const invalid = ATTRIBUTE_FIELDS.find(field => values[field] < bases[field] || values[field] > 5 || !Number.isInteger(values[field]));
  return { values, bases, spent, remaining: 10 - spent, invalid, race };
}

export function validateAttributes(character, db) {
  const state = attributeState(character, db);
  if (state.invalid) return `O atributo ${state.invalid} deve ficar entre ${state.bases[state.invalid]} e 5.`;
  if (state.spent > 10) return `A ficha ultrapassa o limite de 10 pontos distribuídos (usou ${state.spent}).`;
  return null;
}

export function fitAttributes(character, db) {
  const state = attributeState(character, db);
  let remaining = 10;
  const values = {};
  for (const field of ATTRIBUTE_FIELDS) {
    const base = Math.min(5, state.bases[field]);
    const requested = Math.max(base, Math.min(5, state.values[field]));
    const allocated = Math.min(Math.max(0, requested - base), remaining);
    values[field] = base + allocated;
    remaining -= allocated;
  }
  return values;
}

function findRace(name, db) {
  if (!name || !db) return null;
  return db.prepare('SELECT * FROM racas').all().find(race => normalize(race.nome) === normalize(name)) || null;
}

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalize(value) {
  const normalized = String(value || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim();
  return { elfa: 'elfo', humana: 'humano' }[normalized] || normalized;
}
