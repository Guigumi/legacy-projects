import { api } from '../lib/api.js';

export function useCombatActions({ combateAtivo, carregarCombate, setCombateAtivo, setSelectedParticipantId, setInspectedEffectId, setHistory, history, notify, notas, notasSalvasRef, draggingId, setDraggingId }) {
  async function avancarTurno() {
    try {
      const resultado = await api.avancarTurno(combateAtivo.id);
      await carregarCombate(combateAtivo.id);
      if (resultado.proximo?.startsWith('p:')) {
        setSelectedParticipantId(Number(resultado.proximo.slice(2)));
        setInspectedEffectId(null);
      } else if (resultado.proximo?.startsWith('e:')) {
        setInspectedEffectId(Number(resultado.proximo.slice(2)));
        setSelectedParticipantId(null);
      }
      notify('Turno avançado.');
    } catch (error) { notify(error.message, 'error'); }
  }

  async function turnoExtra(participanteId) {
    if (!participanteId) return false;
    try {
      await api.turnoExtra(combateAtivo.id, participanteId);
      await carregarCombate(combateAtivo.id);
      notify('Turno extra concedido.');
      return true;
    } catch (error) {
      notify(error.message, 'error');
      return false;
    }
  }

  async function criarEvento(evento) {
    const nome = evento.nome.trim();
    if (!nome) return false;
    try {
      await api.createEfeito(combateAtivo.id, { tipo: 'evento', nome, descricao: evento.descricao, duracao: Number(evento.duracao) || 1 });
      await carregarCombate(combateAtivo.id);
      notify('Evento adicionado à fila.');
      return true;
    } catch (error) {
      notify(error.message, 'error');
      return false;
    }
  }

  async function reordenarFila(tokens) {
    try {
      await api.reorderQueue(combateAtivo.id, tokens);
      await carregarCombate(combateAtivo.id);
      notify('Fila reordenada.');
    } catch (error) {
      await carregarCombate(combateAtivo.id);
      notify(error.message, 'error');
    }
  }

  async function rolarIniciativa() {
    try {
      await api.rolarIniciativa(combateAtivo.id, {});
      await carregarCombate(combateAtivo.id);
      notify('Iniciativa rolada e ordenada.');
    } catch (error) { notify(error.message, 'error'); }
  }

  async function salvarNotas() {
    if (notas === notasSalvasRef.current) return;
    try {
      await api.updateNotas(combateAtivo.id, notas);
      notasSalvasRef.current = notas;
      setHistory(await api.getHistory(combateAtivo.id));
    } catch (error) { notify(error.message, 'error'); }
  }

  async function desfazer() {
    if (!history.canUndo) return;
    try {
      await api.undo(combateAtivo.id);
      await carregarCombate(combateAtivo.id);
      notify('Ação desfeita.');
    } catch (error) { notify(error.message, 'error'); }
  }

  async function refazer() {
    if (!history.canRedo) return;
    try {
      await api.redo(combateAtivo.id);
      await carregarCombate(combateAtivo.id);
      notify('Ação refeita.');
    } catch (error) { notify(error.message, 'error'); }
  }

  async function reordenarParticipantes(targetId) {
    if (!draggingId || draggingId === targetId) return;
    const current = [...(combateAtivo?.participantes || [])];
    const from = current.findIndex(item => item.id === draggingId);
    const to = current.findIndex(item => item.id === targetId);
    if (from < 0 || to < 0) return;
    const [moved] = current.splice(from, 1);
    current.splice(to, 0, moved);
    setCombateAtivo({ ...combateAtivo, participantes: current });
    setDraggingId(null);
    try {
      await api.reorderParticipants(combateAtivo.id, current.map(item => item.id));
      setHistory(await api.getHistory(combateAtivo.id));
      notify('Ordem de iniciativa atualizada.');
    } catch (error) {
      await carregarCombate(combateAtivo.id);
      notify(error.message, 'error');
    }
  }

  return { avancarTurno, turnoExtra, criarEvento, reordenarFila, rolarIniciativa, salvarNotas, desfazer, refazer, reordenarParticipantes };
}
