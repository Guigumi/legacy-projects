export function calculateCharacterResources(character, db) {
  const nivel = number(character?.nivel);
  const vida = number(character?.vida);
  const mana = number(character?.mana);
  const arma = db && character?.arma
    ? db.prepare('SELECT nome, debuff_mana FROM armas').all().find(item => normalize(item.nome) === normalize(character.arma))
    : null;
  const manaModifier = arma ? -number(arma.debuff_mana) : fallbackWeaponManaModifier(character?.arma);

  return {
    hp_max: 100 + (nivel * 10) + (vida * 10),
    mp_max: Math.max(0, 100 + (nivel * 10) + (mana * 10) + manaModifier),
  };
}

function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function normalize(value) {
  return String(value || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim();
}

function fallbackWeaponManaModifier(weapon) {
  return ['grimorio', 'orbe', 'luvas'].includes(normalize(weapon)) ? -10 : 0;
}
