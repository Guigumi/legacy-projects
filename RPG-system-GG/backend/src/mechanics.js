import { db } from './database.js';

const ACTIONS = new Set(['cura_hp', 'dano_hp', 'restaura_mp', 'drena_mp', 'modifica_iniciativa']);
const TARGETS = new Set(['alvo', 'conjurador']);

export function parseMechanics(value) {
  if (Array.isArray(value)) return value.filter(isValidMechanic);
  if (typeof value !== 'string' || !value.trim()) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.filter(isValidMechanic) : [];
  } catch {
    return [];
  }
}

function isValidMechanic(effect) {
  const valueIsValid = typeof effect?.valor === 'string' ? effect.valor.trim() : Number.isFinite(effect?.valor);
  return effect && ACTIONS.has(effect.acao) && TARGETS.has(effect.alvo) && valueIsValid;
}

export function rollExpression(expression) {
  const clean = String(expression || '').trim().toLowerCase().replace(/\s+/g, '');
  if (!/^[0-9d+-]+$/.test(clean)) throw new Error('Use valores como 20, d6 ou 2d6+3.');
  const terms = clean.match(/[+-]?[^+-]+/g) || [];
  let total = 0;
  for (const term of terms) {
    const sign = term.startsWith('-') ? -1 : 1;
    const raw = term.replace(/^[+-]/, '');
    const dice = raw.match(/^(\d*)d(\d+)$/);
    if (dice) {
      const quantity = Number(dice[1] || 1);
      const sides = Number(dice[2]);
      if (quantity < 1 || quantity > 20 || sides < 2 || sides > 1000) throw new Error('Use dados de 1d2 a 20d1000.');
      total += sign * Array.from({ length: quantity }, () => Math.floor(Math.random() * sides) + 1).reduce((sum, roll) => sum + roll, 0);
    } else if (/^\d+$/.test(raw)) {
      total += sign * Number(raw);
    } else {
      throw new Error('Valor de efeito inválido.');
    }
  }
  return total;
}

function resolveValue(expression, effect, participant, allowHalf) {
  const normalized = String(expression || '').trim().toLowerCase();
  if (normalized !== '{half}') return rollExpression(expression);
  if (!allowHalf) throw new Error('{half} só pode ser usado em magias.');
  const total = effect.acao.endsWith('_hp') ? participant.hp_max : effect.acao.endsWith('_mp') ? participant.mp_max : null;
  if (total === null) throw new Error('{half} só pode ser usado com HP ou MP.');
  return Math.floor(total / 2);
}

export function applyMechanics(combateId, sourceId, targetId, mechanics, { allowHalf = false } = {}) {
  const source = db.prepare('SELECT * FROM participantes WHERE id = ? AND combate_id = ?').get(sourceId, combateId);
  const target = targetId ? db.prepare('SELECT * FROM participantes WHERE id = ? AND combate_id = ?').get(targetId, combateId) : source;
  if (!source || !target) throw new Error('Participante ou alvo inválido.');
  const applied = [];

  for (const effect of parseMechanics(mechanics)) {
    const participantId = effect.alvo === 'conjurador' ? source.id : target.id;
    const participant = db.prepare('SELECT * FROM participantes WHERE id = ? AND combate_id = ?').get(participantId, combateId);
    const value = resolveValue(effect.valor, effect, participant, allowHalf);
    if (effect.acao === 'cura_hp' || effect.acao === 'dano_hp') {
      const delta = effect.acao === 'cura_hp' ? value : -value;
      const next = Math.max(0, Math.min(participant.hp_max, participant.hp_atual + delta));
      db.prepare('UPDATE participantes SET hp_atual = ? WHERE id = ?').run(next, participant.id);
      applied.push(`${effect.acao === 'cura_hp' ? 'Cura' : 'Dano'} ${Math.abs(next - participant.hp_atual)} HP em ${participant.nome}`);
    } else if (effect.acao === 'restaura_mp' || effect.acao === 'drena_mp') {
      const delta = effect.acao === 'restaura_mp' ? value : -value;
      const next = Math.max(0, Math.min(participant.mp_max, participant.mp_atual + delta));
      db.prepare('UPDATE participantes SET mp_atual = ? WHERE id = ?').run(next, participant.id);
      applied.push(`${effect.acao === 'restaura_mp' ? 'Restauração' : 'Dreno'} ${Math.abs(next - participant.mp_atual)} MP em ${participant.nome}`);
    } else if (effect.acao === 'modifica_iniciativa') {
      const next = participant.iniciativa + value;
      db.prepare('UPDATE participantes SET iniciativa = ? WHERE id = ?').run(next, participant.id);
      applied.push(`Iniciativa ${value >= 0 ? '+' : ''}${value} em ${participant.nome}`);
    }
  }
  return applied;
}
