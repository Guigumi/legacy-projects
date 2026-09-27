import { db, initDatabase } from './database.js';

function seedRacas() {
  const racas = [
    { nome: 'Humano', buff_vida: 1, buff_mana: 0, buff_inteligencia: 0, buff_agilidade: 0, buff_vigor: 1, descricao: '+1 Vida e +1 Vigor' },
    { nome: 'Elfo',   buff_vida: 0, buff_mana: 1, buff_inteligencia: 1, buff_agilidade: 0, buff_vigor: 0, descricao: '+1 Mana e +1 Inteligência' },
  ];
  const stmt = db.prepare(`INSERT OR IGNORE INTO racas (nome, buff_vida, buff_mana, buff_inteligencia, buff_agilidade, buff_vigor, descricao) VALUES (:nome,:buff_vida,:buff_mana,:buff_inteligencia,:buff_agilidade,:buff_vigor,:descricao)`);
  for (const r of racas) stmt.run(r);
  console.log(`Raças: ${racas.length} cadastradas.`);
}

function seedArmas() {
  const armas = [
    { nome: 'Cajado',  buff_iniciativa: 0, buff_dano: 0, buff_desvio: 0, debuff_dano: 0, debuff_iniciativa: 0, debuff_mana: 0,  descricao: 'Equilibrado, sem bônus nem ônus.' },
    { nome: 'Varinha', buff_iniciativa: 2, buff_dano: 0, buff_desvio: 0, debuff_dano: 1, debuff_iniciativa: 0, debuff_mana: 0,  descricao: '+2 Iniciativa, -1 de dano.' },
    { nome: 'Grimório',buff_iniciativa: 0, buff_dano: 1, buff_desvio: 0, debuff_dano: 0, debuff_iniciativa: 0, debuff_mana: 10, descricao: '+1 dano, -10 de Mana.' },
    { nome: 'Orbe',    buff_iniciativa: 0, buff_dano: 2, buff_desvio: 0, debuff_dano: 0, debuff_iniciativa: 1, debuff_mana: 10, descricao: '+2 dano, -1 Iniciativa, -10 Mana.' },
    { nome: 'Luvas',   buff_iniciativa: 2, buff_dano: 0, buff_desvio: 2, debuff_dano: 1, debuff_iniciativa: 0, debuff_mana: 10, descricao: '+2 Iniciativa e +2 Desvio, -1 dano, -10 Mana.' },
  ];
  const stmt = db.prepare(`INSERT OR IGNORE INTO armas (nome, buff_iniciativa, buff_dano, buff_desvio, debuff_dano, debuff_iniciativa, debuff_mana, descricao) VALUES (:nome,:buff_iniciativa,:buff_dano,:buff_desvio,:debuff_dano,:debuff_iniciativa,:debuff_mana,:descricao)`);
  for (const a of armas) stmt.run(a);
  console.log(`Armas: ${armas.length} cadastradas.`);
}

function seedMagias() {
  const minhas = [
    { nome: 'Esfera de Luz',   custo: 5,  tipo: 'básica', descricao: 'Ilumina o cenário, um pouco mais fraco que uma vela.', observacao: 'Não pode controlar, somente na arma', categoria: 'básica' },
    { nome: 'Telepatia',       custo: 5,  tipo: 'básica', descricao: 'Fala com alguém a distâncias médias.', observacao: '', categoria: 'básica' },
    { nome: 'Rastros de mana', custo: 5,  tipo: 'básica', descricao: 'Sente rastros de mana no cenário.', observacao: 'Somente fora de combate', categoria: 'básica' },
    { nome: 'Toque Vital (Vida 3)',    custo: 15, tipo: 'atributo', descricao: 'Cura aliados em 25 HP.', observacao: 'Vida 3', categoria: 'atributo', efeitos: [{ acao: 'cura_hp', alvo: 'alvo', valor: 25 }] },
    { nome: 'Toque Vital (Vida 5)',    custo: 25, tipo: 'atributo', descricao: 'Cura aliados em 45 HP.', observacao: 'Vida 5', categoria: 'atributo', efeitos: [{ acao: 'cura_hp', alvo: 'alvo', valor: 45 }] },
    { nome: 'Transferência',           custo: 0,  tipo: 'atributo', descricao: 'Passa até 25 MP a um aliado.', observacao: 'Mana 3', categoria: 'atributo', efeitos: [{ acao: 'restaura_mp', alvo: 'alvo', valor: 25 }] },
    { nome: 'Roubo',                   custo: 0,  tipo: 'atributo', descricao: 'Ao toque rouba até 50 MP de inimigos e aliados.', observacao: 'Mana 5', categoria: 'atributo', efeitos: [{ acao: 'drena_mp', alvo: 'alvo', valor: 50 }, { acao: 'restaura_mp', alvo: 'conjurador', valor: 50 }] },
    { nome: 'Puxar (Int 3)',            custo: 10, tipo: 'atributo', descricao: 'Puxa objetos próximos a 1 metro.', observacao: 'Inteligência 3', categoria: 'atributo' },
    { nome: 'Puxar (Int 5)',            custo: 10, tipo: 'atributo', descricao: 'Puxa objetos em até 5 metros.', observacao: 'Inteligência 5', categoria: 'atributo' },
    { nome: 'Voar (Agi 3)',             custo: 0,  tipo: 'atributo', descricao: 'Levanta até 2 metros do chão, por 3 turnos no ar.', observacao: 'Agilidade 3', categoria: 'atributo' },
    { nome: 'Voar (Agi 5)',             custo: 0,  tipo: 'atributo', descricao: 'Levanta até 10 metros do chão, por 5 turnos no ar.', observacao: 'Agilidade 5', categoria: 'atributo' },
    { nome: 'Resistência',             custo: 0,  tipo: 'atributo', descricao: 'Quedas médias não terão efeitos.', observacao: 'Vigor 3', categoria: 'atributo' },
    { nome: 'Regeneração',              custo: 0,  tipo: 'atributo', descricao: 'Quando perto da morte, regenera metade do total de mana.', observacao: 'Vigor 5', categoria: 'atributo' },
    { nome: 'Incendiar',    custo: 10, tipo: 'simples', descricao: 'Lança uma bola de fogo na direção do alvo.', observacao: '', categoria: 'simples', efeitos: [{ acao: 'dano_hp', alvo: 'alvo', valor: '2d6' }] },
    { nome: 'Iluminar',     custo: 25, tipo: 'simples', descricao: 'Esfera de luz que segue você e ilumina uma sala inteira por (inteligência).', observacao: 'Pode controlar livremente', categoria: 'simples' },
    { nome: 'Ondas',        custo: 9,  tipo: 'simples', descricao: 'Cria uma onda que empurra o que atingir.', observacao: '', categoria: 'simples' },
    { nome: 'Bolha',        custo: 6,  tipo: 'simples', descricao: 'Reduz o próximo dano recebido em 3.', observacao: '', categoria: 'simples' },
    { nome: 'Limpar',       custo: 6,  tipo: 'simples', descricao: 'Limpa qualquer objeto sem danificar.', observacao: '', categoria: 'simples' },
    { nome: 'Corte',        custo: 6,  tipo: 'simples', descricao: 'Lança um corte de ar.', observacao: '', categoria: 'simples' },
    { nome: 'Estilhaço',    custo: 12, tipo: 'simples', descricao: 'Lança pedaços de gelo no inimigo.', observacao: 'Livro do Gelo', categoria: 'simples' },
    { nome: 'Congelar',     custo: 8,  tipo: 'simples', descricao: 'Congela inimigos pequenos.', observacao: 'D20 + Vigor para sair, se cair abaixo de 15 leva mais dano no próximo ataque', categoria: 'simples' },
    { nome: 'Raio',         custo: 12, tipo: 'simples', descricao: 'Lança um raio no inimigo.', observacao: '', categoria: 'simples' },
    { nome: 'Campo da Vida',custo: 8,  tipo: 'simples', descricao: 'Cura todos os aliados em 3.', observacao: 'Cura 5 + Inteligência', categoria: 'simples' },
    { nome: 'Muralha',      custo: 12, tipo: 'simples', descricao: 'Cria uma barreira de terra.', observacao: '', categoria: 'simples' },
    { nome: 'Vinhas',       custo: 10, tipo: 'simples', descricao: 'Vinhas com espinhos prendem o alvo.', observacao: 'D20 + Vigor para sair, se cair abaixo de 15 leva dano', categoria: 'simples' },
    { nome: 'Sombra',       custo: 12, tipo: 'simples', descricao: 'Fica invisível e se movimenta pelo turno.', observacao: '15+ para ser detectado, mas ao atacar 5+ para detectar', categoria: 'simples' },
    { nome: 'Tempo Lento',  custo: 20, tipo: 'simples', descricao: 'Você pode atacar no mesmo turno (turno extra).', observacao: 'Pode usar depois de atacar, mas se o D20 cair abaixo de 8, perde 10 de mana e não ataca', categoria: 'simples' },
    { nome: 'Estrelas',      custo: 25, tipo: 'complexa', descricao: 'Lança duas pequenas estrelas que implodem ao contato.', observacao: 'Pode controlar', categoria: 'complexa' },
    { nome: 'Ponta estelar', custo: 25, tipo: 'complexa', descricao: 'Cria uma estrela pontiaguda que perfura qualquer material.', observacao: 'Pode controlar', categoria: 'complexa' },
  ];
  const stmt = db.prepare(`INSERT OR IGNORE INTO magias (nome, custo, tipo, descricao, observacao, categoria, efeitos) VALUES (:nome,:custo,:tipo,:descricao,:observacao,:categoria,:efeitos)`);
  for (const m of minhas) stmt.run({ ...m, efeitos: JSON.stringify(m.efeitos || []) });
  console.log(`Magias: ${minhas.length} cadastradas.`);
}

function seedItens() {
  const itens = [
    { nome: 'Poção de cura pequena',  tipo: 'poção', efeito: 'cura',    valor: '+25 HP', efeitos: [{ acao: 'cura_hp', alvo: 'alvo', valor: 25 }] },
    { nome: 'Poção de cura grande',   tipo: 'poção', efeito: 'cura',    valor: '+50 HP', efeitos: [{ acao: 'cura_hp', alvo: 'alvo', valor: 50 }] },
    { nome: 'Poção pequena de mana',  tipo: 'poção', efeito: 'mana',    valor: '+15 MP', efeitos: [{ acao: 'restaura_mp', alvo: 'alvo', valor: 15 }] },
  ];
  const stmt = db.prepare(`INSERT OR IGNORE INTO itens (nome, tipo, efeito, valor, efeitos) VALUES (:nome,:tipo,:efeito,:valor,:efeitos)`);
  for (const i of itens) stmt.run({ ...i, efeitos: JSON.stringify(i.efeitos || []) });
  console.log(`Itens: ${itens.length} cadastrados.`);
}

function seedPersonagens() {
  const personagem = {
    nome: 'Lyra', nome_jogador: 'Exemplo', raca: 'Elfa', arma: 'Grimório',
    nivel: 1, idade: '67', aparencia: 'Cabelo prateado e olhos cinza',
    hp_max: 140, mp_max: 140, vida: 3, mana: 4, inteligencia: 5, agilidade: 2, vigor: 3,
    magias: JSON.stringify(['Esfera de Luz', 'Telepatia', 'Toque Vital', 'Puxar']),
    inventario: '', is_preset: 1,
  };
  const existing = db.prepare('SELECT id FROM personagens WHERE is_preset = 1 ORDER BY id LIMIT 1').get();
  let personagemId = existing?.id;
  if (personagemId) {
    db.prepare(`UPDATE personagens SET nome=:nome, nome_jogador=:nome_jogador, raca=:raca, arma=:arma, nivel=:nivel, idade=:idade, aparencia=:aparencia, hp_max=:hp_max, mp_max=:mp_max, vida=:vida, mana=:mana, inteligencia=:inteligencia, agilidade=:agilidade, vigor=:vigor, magias=:magias, inventario=:inventario, is_preset=:is_preset WHERE id=:id`).run({ ...personagem, id: personagemId });
  } else {
    const info = db.prepare(`INSERT INTO personagens (nome, nome_jogador, raca, arma, nivel, idade, aparencia, hp_max, mp_max, vida, mana, inteligencia, agilidade, vigor, magias, inventario, is_preset) VALUES (:nome,:nome_jogador,:raca,:arma,:nivel,:idade,:aparencia,:hp_max,:mp_max,:vida,:mana,:inteligencia,:agilidade,:vigor,:magias,:inventario,:is_preset)`).run(personagem);
    personagemId = Number(info.lastInsertRowid);
  }
  db.prepare('DELETE FROM personagens WHERE is_preset = 1 AND id != ?').run(personagemId);
  console.log('Personagens: 1 preset de exemplo.');
  return personagemId;
}

function seedBestiario() {
  const inimigo = { nome: 'Sombra', categoria: 'inimigo', hp_max: 50, dano: 'Ataque base', descricao: 'Inimigo usado como exemplo.', mecanicas: 'Use esta entrada como base para criar outros inimigos.', is_preset: 1 };
  const existing = db.prepare('SELECT id FROM bestiario WHERE is_preset = 1 ORDER BY id LIMIT 1').get();
  let inimigoId = existing?.id;
  if (inimigoId) {
    db.prepare(`UPDATE bestiario SET nome=:nome, categoria=:categoria, hp_max=:hp_max, dano=:dano, descricao=:descricao, mecanicas=:mecanicas, is_preset=:is_preset WHERE id=:id`).run({ ...inimigo, id: inimigoId });
  } else {
    const info = db.prepare(`INSERT INTO bestiario (nome, categoria, hp_max, dano, descricao, mecanicas, is_preset) VALUES (:nome,:categoria,:hp_max,:dano,:descricao,:mecanicas,:is_preset)`).run(inimigo);
    inimigoId = Number(info.lastInsertRowid);
  }
  db.prepare('DELETE FROM bestiario WHERE is_preset = 1 AND id != ?').run(inimigoId);
  console.log('Bestiário: 1 preset de exemplo.');
  return inimigoId;
}

function seedCombate(personagemId, inimigoId) {
  const existing = db.prepare("SELECT id FROM combates WHERE status = 'ativo' ORDER BY id LIMIT 1").get();
  if (existing) return;
  const combateInfo = db.prepare("INSERT INTO combates (nome, rodada, status, fila_turnos, turno_atual_tipo) VALUES ('Sessão de exemplo', 1, 'ativo', '[]', 'participante')").run();
  const combateId = Number(combateInfo.lastInsertRowid);
  const ally = db.prepare(`SELECT * FROM personagens WHERE id = ?`).get(personagemId);
  const enemy = db.prepare(`SELECT * FROM bestiario WHERE id = ?`).get(inimigoId);
  const addParticipant = db.prepare(`INSERT INTO participantes (combate_id, nome, tipo, iniciativa, hp_atual, hp_max, mp_atual, mp_max, ordem, foto, personagem_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`);
  const allyInfo = addParticipant.run(combateId, ally.nome, 'jogador', 15, ally.hp_max, ally.hp_max, ally.mp_max, ally.mp_max, 0, ally.foto || null, ally.id);
  const enemyInfo = addParticipant.run(combateId, enemy.nome, 'inimigo', 10, enemy.hp_max, enemy.hp_max, 0, 0, 1, enemy.foto || null, null);
  const queue = JSON.stringify([`p:${Number(allyInfo.lastInsertRowid)}`, `p:${Number(enemyInfo.lastInsertRowid)}`]);
  db.prepare("UPDATE combates SET fila_turnos = ?, turno_atual_id = ?, turno_atual_tipo = 'participante' WHERE id = ?").run(queue, Number(allyInfo.lastInsertRowid), combateId);
  console.log('Combate: sessão de exemplo criada.');
}

initDatabase();
seedRacas();
seedArmas();
seedMagias();
seedItens();
const personagemId = seedPersonagens();
const inimigoId = seedBestiario();
seedCombate(personagemId, inimigoId);
console.log('Seed concluido com sucesso!');
