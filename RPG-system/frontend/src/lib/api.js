const API = '/api';

function requireId(value, label) {
  const id = Number(value);
  if (!Number.isInteger(id) || id < 1) throw new Error(`${label} inválido.`);
  return id;
}

function combatPath(combateId, suffix = '') {
  return `/combates/${requireId(combateId, 'Combate')}${suffix}`;
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      credentials: 'include',
      cache: 'no-store',
    });
  } catch (cause) {
    const error = new Error('Servidor indisponivel.');
    error.cause = cause;
    throw error;
  }
  let data;
  try {
    data = await res.json();
  } catch (cause) {
    if (res.ok) {
      const error = new Error('Resposta inválida do servidor. Reinicie o backend e tente novamente.');
      error.cause = cause;
      throw error;
    }
    data = {};
  }
  if (!res.ok) {
    const error = new Error(data.error || `Erro ${res.status}`);
    error.status = res.status;
    throw error;
  }
  return data;
}

export const api = {
  // Auth
  status: () => request('/status'),
  login: (senha) => request('/login', { method: 'POST', body: JSON.stringify({ senha }) }),
  logout: () => request('/logout', { method: 'POST' }),
  getPlayerState: () => request('/player/state'),
  exportBackup: async () => {
    const response = await fetch(`${API}/backup/export`, { credentials: 'include' });
    if (!response.ok) throw new Error('Falha ao exportar backup.');
    return response.blob();
  },
  importBackup: (backup) => request('/backup/import', { method: 'POST', body: JSON.stringify(backup) }),
  importObsidianPersonagens: (files) => request('/import/obsidian/personagens', { method: 'POST', body: JSON.stringify({ files }) }),
  importObsidianBestiario: (files) => request('/import/obsidian/bestiario', { method: 'POST', body: JSON.stringify({ files }) }),

  // Dados pre-cadastrados
  getRacas: () => request('/racas'),
  getArmas: () => request('/armas'),
  getMagias: () => request('/magias'),
  getItens: () => request('/itens'),
  updateMagia: (id, data) => request(`/magias/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  createMagia: (data) => request('/magias', { method: 'POST', body: JSON.stringify(data) }),
  deleteMagia: (id) => request(`/magias/${id}`, { method: 'DELETE' }),
  updateItem: (id, data) => request(`/itens/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  createItem: (data) => request('/itens', { method: 'POST', body: JSON.stringify(data) }),
  deleteItem: (id) => request(`/itens/${id}`, { method: 'DELETE' }),

  // Personagens (Fichas)
  getPersonagens: () => request('/personagens'),
  createPersonagem: (data) => request('/personagens', { method: 'POST', body: JSON.stringify(data) }),
  updatePersonagem: (id, data) => request(`/personagens/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deletePersonagem: (id) => request(`/personagens/${id}`, { method: 'DELETE' }),
  setPersonagemFoto: (id, foto) => request(`/personagens/${id}/foto`, { method: 'POST', body: JSON.stringify({ foto }) }),
  removePersonagemFoto: (id) => request(`/personagens/${id}/foto`, { method: 'DELETE' }),

  // Bestiario
  getBestiario: () => request('/bestiario'),
  createBestiario: (data) => request('/bestiario', { method: 'POST', body: JSON.stringify(data) }),
  updateBestiario: (id, data) => request(`/bestiario/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteBestiario: (id) => request(`/bestiario/${id}`, { method: 'DELETE' }),
  setBestiarioFoto: (id, foto) => request(`/bestiario/${id}/foto`, { method: 'POST', body: JSON.stringify({ foto }) }),
  removeBestiarioFoto: (id) => request(`/bestiario/${id}/foto`, { method: 'DELETE' }),

  // Roteiros e transmissão
  getRoteiros: () => request('/roteiros'),
  createRoteiro: (data) => request('/roteiros', { method: 'POST', body: JSON.stringify(data) }),
  updateRoteiro: (id, data) => request(`/roteiros/${requireId(id, 'Roteiro')}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteRoteiro: (id) => request(`/roteiros/${requireId(id, 'Roteiro')}`, { method: 'DELETE' }),
  createCena: (id, data) => request(`/roteiros/${requireId(id, 'Roteiro')}/cenas`, { method: 'POST', body: JSON.stringify(data) }),
  updateCena: (id, data) => request(`/roteiro-cenas/${requireId(id, 'Cena')}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteCena: (id) => request(`/roteiro-cenas/${requireId(id, 'Cena')}`, { method: 'DELETE' }),
  getTransmissao: () => request('/transmissao'),
  updateTransmissao: (data) => request('/transmissao', { method: 'PUT', body: JSON.stringify(data) }),
  getPlayerRolls: () => request('/transmissao/rolagens'),
  createRoll: (data) => request('/transmissao/rolagens', { method: 'POST', body: JSON.stringify(data) }),
  clearRolls: () => request('/transmissao/rolagens', { method: 'DELETE' }),

  // Combates
  getCombates: () => request('/combates'),
  getCombate: (id) => request(combatPath(id)),
  createCombate: (nome) => request('/combates', { method: 'POST', body: JSON.stringify({ nome }) }),
  deleteCombate: (id) => request(combatPath(id), { method: 'DELETE' }),
  updateCombate: (id, data) => request(combatPath(id), { method: 'PUT', body: JSON.stringify(data) }),
  updateNotas: (id, notas) => request(combatPath(id, '/notas'), { method: 'PUT', body: JSON.stringify({ notas }) }),
  reorderParticipants: (id, ids) => request(combatPath(id, '/ordem'), { method: 'PUT', body: JSON.stringify({ ids: ids.map(item => requireId(item, 'Participante')) }) }),
  reorderQueue: (id, tokens) => request(combatPath(id, '/fila'), { method: 'PUT', body: JSON.stringify({ tokens }) }),
  getHistory: (id) => request(combatPath(id, '/historico')),
  undo: (id) => request(combatPath(id, '/undo'), { method: 'POST' }),
  redo: (id) => request(combatPath(id, '/redo'), { method: 'POST' }),

  // Participantes
  addParticipante: (combateId, data) => request(combatPath(combateId, '/participantes'), { method: 'POST', body: JSON.stringify(data) }),
  updateParticipante: (id, data) => request(`/participantes/${requireId(id, 'Participante')}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteParticipante: (id) => request(`/participantes/${requireId(id, 'Participante')}`, { method: 'DELETE' }),

  // Turnos
  avancarTurno: (combateId) => request(combatPath(combateId, '/avancar-turno'), { method: 'POST' }),
  turnoExtra: (combateId, participanteId) => request(combatPath(combateId, '/turno-extra'), { method: 'POST', body: JSON.stringify({ participante_id: requireId(participanteId, 'Participante') }) }),
  rolarIniciativa: (combateId, modificadores) => request(combatPath(combateId, '/rolar-iniciativa'), { method: 'POST', body: JSON.stringify({ modificadores }) }),
  usarMagiaInstantanea: (combateId, data) => request(combatPath(combateId, '/magia-instantanea'), { method: 'POST', body: JSON.stringify({ ...data, participante_id: requireId(data?.participante_id, 'Participante'), magia_id: requireId(data?.magia_id, 'Magia'), alvo_id: data?.alvo_id ? requireId(data.alvo_id, 'Alvo') : null }) }),
  usarItemInstantaneo: (combateId, data) => request(combatPath(combateId, '/item-instantaneo'), { method: 'POST', body: JSON.stringify({ ...data, participante_id: requireId(data?.participante_id, 'Participante'), item_id: requireId(data?.item_id, 'Item'), alvo_id: data?.alvo_id ? requireId(data.alvo_id, 'Alvo') : null }) }),
  getEfeitos: (combateId) => request(combatPath(combateId, '/efeitos')),
  createEfeito: (combateId, data) => request(combatPath(combateId, '/efeitos'), { method: 'POST', body: JSON.stringify(data) }),
  deleteEfeito: (id) => request(`/efeitos/${requireId(id, 'Efeito')}`, { method: 'DELETE' }),

  // Log
  getLog: (combateId) => request(combatPath(combateId, '/log')),
};
