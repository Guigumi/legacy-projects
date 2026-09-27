import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronRight, ChevronUp, Plus, ScrollText, Zap } from 'lucide-react';
import ParticipantCard from '../components/ParticipantCard.jsx';
import { ConfirmModal, Toast } from '../components/Overlay.jsx';
import DiceRoller from '../components/DiceRoller.jsx';
import Bestiario from './Bestiario.jsx';
import Fichas from './Fichas.jsx';
import { api } from '../lib/api.js';
import { useCombatActions } from '../hooks/useCombatActions.js';
import { AddParticipantModal, EventModal, ExtraTurnModal } from '../components/CombatModals.jsx';
import CombatHeader from '../components/dashboard/CombatHeader.jsx';
import CombatStatus from '../components/dashboard/CombatStatus.jsx';
import CombatList from '../components/dashboard/CombatList.jsx';
import TurnQueue from '../components/dashboard/TurnQueue.jsx';
import BaseOrder from '../components/dashboard/BaseOrder.jsx';
import EffectInspector from '../components/dashboard/EffectInspector.jsx';
import Roteiros from './Roteiros.jsx';
import Transmitir from './Transmitir.jsx';
import GerenciarDados from './GerenciarDados.jsx';
import Compendium from './Compendium.jsx';

const blankParticipant = { nome: '', tipo: 'jogador', iniciativa: 0, hp_atual: 100, hp_max: 100, mp_atual: 100, mp_max: 100, personagem_id: null, bestiario_id: null };
const blankEvent = { nome: '', descricao: '', duracao: 1 };

export default function Dashboard({ onLogout }) {
  const [tab, setTab] = useState('sessao');
  const [combates, setCombates] = useState([]);
  const [combateAtivo, setCombateAtivo] = useState(null);
  const [view, setView] = useState('lista');
  const [logs, setLogs] = useState([]);
  const [history, setHistory] = useState({ canUndo: false, canRedo: false });
  const [efeitos, setEfeitos] = useState([]);
  const [notas, setNotas] = useState('');
  const notasSalvasRef = useRef('');
  const [notasColapsado, setNotasColapsado] = useState(false);
  const [novoCombateNome, setNovoCombateNome] = useState('');
  const [criandoCombate, setCriandoCombate] = useState(false);
  const [showAddPart, setShowAddPart] = useState(false);
  const [personagens, setPersonagens] = useState([]);
  const [bestiario, setBestiario] = useState([]);
  const [magias, setMagias] = useState([]);
  const [itens, setItens] = useState([]);
  const [novoPart, setNovoPart] = useState({ ...blankParticipant });
  const [draggingId, setDraggingId] = useState(null);
  const [toast, setToast] = useState(null);
  const [confirmModal, setConfirmModal] = useState(null);
  const [selectedParticipantId, setSelectedParticipantId] = useState(null);
  const [inspectedEffectId, setInspectedEffectId] = useState(null);
  const [showExtraTurnModal, setShowExtraTurnModal] = useState(false);
  const [extraTurnParticipantId, setExtraTurnParticipantId] = useState('');
  const [showEventModal, setShowEventModal] = useState(false);
  const [newEvent, setNewEvent] = useState({ ...blankEvent });

  const notify = useCallback((message, type = 'success') => {
    setToast({ message, type });
    window.setTimeout(() => setToast(null), 2600);
  }, []);

  const carregarCombates = useCallback(async () => {
    try { setCombates(await api.getCombates()); } catch (error) { notify(error.message, 'error'); }
  }, [notify]);

  const carregarCombate = useCallback(async (id) => {
    try {
      const combate = await api.getCombate(id);
      setCombateAtivo(combate);
      setNotas(combate.notas || '');
      notasSalvasRef.current = combate.notas || '';
      setLogs(await api.getLog(id));
      setHistory(await api.getHistory(id));
      setEfeitos(combate.efeitos || []);
      setSelectedParticipantId(previous => previous && combate.participantes?.some(item => item.id === previous)
        ? previous
        : combate.turno_atual_id || combate.participantes?.[0]?.id || null);
      setInspectedEffectId(previous => previous && combate.efeitos?.some(item => item.id === previous) ? previous : null);
      return true;
    } catch (error) {
      notify(error.message, 'error');
      return false;
    }
  }, [notify]);

  const { avancarTurno, turnoExtra, criarEvento, reordenarFila, rolarIniciativa, salvarNotas, desfazer, refazer, reordenarParticipantes } = useCombatActions({
    combateAtivo,
    carregarCombate,
    setCombateAtivo,
    setSelectedParticipantId,
    setInspectedEffectId,
    setHistory,
    history,
    notify,
    notas,
    notasSalvasRef,
    draggingId,
    setDraggingId,
  });

  const carregarPersonagens = useCallback(async () => {
    try { setPersonagens(await api.getPersonagens()); } catch (error) { notify(error.message, 'error'); }
  }, [notify]);

  const carregarBestiario = useCallback(async () => {
    try { setBestiario(await api.getBestiario()); } catch (error) { notify(error.message, 'error'); }
  }, [notify]);

  const carregarMagias = useCallback(async () => {
    try { setMagias(await api.getMagias()); } catch (error) { notify(error.message, 'error'); }
  }, [notify]);

  const carregarItens = useCallback(async () => {
    try { setItens(await api.getItens()); } catch (error) { notify(error.message, 'error'); }
  }, [notify]);

  useEffect(() => {
    carregarCombates();
    carregarPersonagens();
    carregarBestiario();
    carregarMagias();
    carregarItens();
    api.status().then(status => { if (!status.autenticado) onLogout(); }).catch(() => onLogout());
  }, [carregarBestiario, carregarCombates, carregarItens, carregarMagias, carregarPersonagens, onLogout]);

  useEffect(() => {
    function handleHistoryKey(event) {
      if (view !== 'combate' || !combateAtivo) return;
      const target = event.target;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable)) return;
      if (event.key.toLowerCase() === 'n') {
        event.preventDefault();
        avancarTurno();
        return;
      }
      const modifier = event.ctrlKey || event.metaKey;
      if (!modifier) return;
      if (event.key.toLowerCase() === 'z') {
        event.preventDefault();
        if (event.shiftKey) refazer();
        else desfazer();
      } else if (event.key.toLowerCase() === 'y') {
        event.preventDefault();
        refazer();
      }
    }
    window.addEventListener('keydown', handleHistoryKey);
    return () => window.removeEventListener('keydown', handleHistoryKey);
  }, [view, combateAtivo, avancarTurno, desfazer, refazer]);

  async function criarCombate() {
    if (criandoCombate) return;
    setCriandoCombate(true);
    try {
      const combate = await api.createCombate(novoCombateNome.trim());
      setNovoCombateNome('');
      await carregarCombates();
      if (await abrirCombate(combate.id)) notify('Sessão criada.');
    } catch (error) { notify(error.message, 'error'); }
    finally { setCriandoCombate(false); }
  }

  async function abrirCombate(id) {
    const carregado = await carregarCombate(id);
    if (!carregado) return false;
    setView('combate');
    return true;
  }

  function deletarCombate(id) {
    setConfirmModal({
      title: 'Excluir combate',
      message: 'Excluir este combate e seu histórico?',
      onConfirm: async () => {
        try {
          await api.deleteCombate(id);
          if (combateAtivo?.id === id) { setCombateAtivo(null); setView('lista'); }
          await carregarCombates();
          notify('Combate encerrado.');
        } catch (error) { notify(error.message, 'error'); }
      },
    });
  }

  async function adicionarParticipante() {
    if (!novoPart.nome?.trim() && !novoPart.personagem_id && !novoPart.bestiario_id) return;
    try {
      await api.addParticipante(combateAtivo.id, novoPart);
      setNovoPart({ ...blankParticipant });
      setShowAddPart(false);
      await carregarCombate(combateAtivo.id);
      notify('Participante adicionado.');
    } catch (error) { notify(error.message, 'error'); }
  }

  function deleteParticipante(id) {
    const participante = combateAtivo?.participantes?.find(item => item.id === id);
    setConfirmModal({
      title: 'Remover participante',
      message: `Remover ${participante?.nome || 'este participante'}?`,
      onConfirm: async () => {
        try {
          await api.deleteParticipante(id);
          await carregarCombate(combateAtivo.id);
          notify('Participante removido.');
        } catch (error) { notify(error.message, 'error'); }
      },
    });
  }

  async function deleteEfeito(id) {
    try {
      await api.deleteEfeito(id);
      setInspectedEffectId(null);
      await carregarCombate(combateAtivo.id);
      notify('Efeito removido.');
    } catch (error) { notify(error.message, 'error'); }
  }

  function abrirTurnoExtra() {
    setExtraTurnParticipantId(combateAtivo?.turno_atual_id || combateAtivo?.participantes?.[0]?.id || '');
    setShowExtraTurnModal(true);
  }

  async function confirmarTurnoExtra() {
    if (!extraTurnParticipantId) return;
    if (await turnoExtra(Number(extraTurnParticipantId))) setShowExtraTurnModal(false);
  }

  async function confirmarNovoEvento() {
    const created = await criarEvento(newEvent);
    if (created) {
      setNewEvent({ ...blankEvent });
      setShowEventModal(false);
    }
  }

  function selecionarPersonagem(id) {
    if (!id) { setNovoPart({ ...novoPart, personagem_id: null }); return; }
    const personagem = personagens.find(item => item.id === Number(id));
    if (personagem) setNovoPart({ ...novoPart, personagem_id: personagem.id, bestiario_id: null, nome: personagem.nome, tipo: 'jogador', hp_max: personagem.hp_max, hp_atual: personagem.hp_max, mp_max: personagem.mp_max, mp_atual: personagem.mp_max });
  }

  function selecionarInimigo(id) {
    if (!id) { setNovoPart({ ...novoPart, bestiario_id: null }); return; }
    const inimigo = bestiario.find(item => item.id === Number(id));
    if (inimigo) setNovoPart({ ...novoPart, bestiario_id: inimigo.id, personagem_id: null, nome: inimigo.nome, tipo: 'inimigo', hp_max: inimigo.hp_max, hp_atual: inimigo.hp_max, mp_max: 0, mp_atual: 0 });
  }

  const turnoAtual = combateAtivo?.participantes?.find(item => item.id === combateAtivo.turno_atual_id);
  const efeitoAtual = combateAtivo?.efeitos?.find(item => item.id === combateAtivo.turno_atual_efeito_id);
  const participantes = combateAtivo?.participantes || [];
  const participanteSelecionado = participantes.find(item => item.id === selectedParticipantId);
  const efeitoInspecionado = combateAtivo?.efeitos?.find(item => item.id === inspectedEffectId);

  function confirmarLogout() {
    setConfirmModal({ title: 'Sair', message: 'Sair da sessão?', onConfirm: onLogout });
  }

  function fecharNovoParticipante() {
    setShowAddPart(false);
    setNovoPart({ ...blankParticipant });
  }

  function fecharEvento() {
    setShowEventModal(false);
    setNewEvent({ ...blankEvent });
  }

  async function handleTabChange(nextTab) {
    setTab(nextTab);
    if (nextTab === 'sessao') await Promise.all([carregarPersonagens(), carregarBestiario(), carregarMagias(), carregarItens()]);
  }

  async function abrirNovoParticipante() {
    await Promise.all([carregarPersonagens(), carregarBestiario()]);
    setNovoPart({ ...blankParticipant });
    setShowAddPart(true);
  }

  async function compartilharRolagem(result) {
    try {
      await api.createRoll({ combate_id: combateAtivo?.id, autor: result.autor, expressao: result.expression, resultado: result.total, detalhes: result.details });
    } catch (error) { notify(error.message, 'error'); }
  }

  return <div className="min-h-screen">
    <CombatHeader view={view} tab={tab} combate={combateAtivo} onBack={() => { setView('lista'); setCombateAtivo(null); }} onTabChange={handleTabChange} onOpenPlayerView={() => window.open('/jogadores', '_blank', 'noopener,noreferrer')} onDelete={deletarCombate} onLogout={confirmarLogout} />
    <main className="w-full px-4 py-6 lg:pl-56 lg:pr-6">
      {tab === 'roteiros' ? <Roteiros /> : tab === 'transmitir' ? <Transmitir /> : tab === 'fichas' ? <Fichas /> : tab === 'inimigos' ? <Bestiario /> : tab === 'magias' ? <Compendium kind="magias" /> : tab === 'itens' ? <Compendium kind="itens" /> : tab === 'dados' ? <GerenciarDados /> : view === 'combate' && combateAtivo ? <div className="space-y-4">
        <CombatStatus combate={combateAtivo} turnoAtual={turnoAtual} efeitoAtual={efeitoAtual} history={history} onRollInitiative={rolarIniciativa} onUndo={desfazer} onRedo={refazer} />
        <div className="grid gap-4 lg:grid-cols-[minmax(280px,23rem)_minmax(0,1fr)] lg:items-start">
          <div className="space-y-4 lg:sticky lg:top-20"><TurnQueue fila={combateAtivo.fila || []} participantes={participantes} efeitos={efeitos} currentToken={combateAtivo.turno_atual_tipo === 'evento' ? `e:${combateAtivo.turno_atual_efeito_id}` : `p:${combateAtivo.turno_atual_id}`} onSelectParticipant={id => { setSelectedParticipantId(id); setInspectedEffectId(null); }} onSelectEffect={id => { setInspectedEffectId(id); setSelectedParticipantId(null); }} onReorder={reordenarFila} onCreateEvent={() => setShowEventModal(true)} onNextTurn={avancarTurno} onExtraTurn={abrirTurnoExtra} /><BaseOrder participantes={participantes} selectedId={selectedParticipantId} draggingId={draggingId} onSelect={id => { setSelectedParticipantId(id); setInspectedEffectId(null); }} onDragStart={setDraggingId} onDragEnd={() => setDraggingId(null)} onDrop={reordenarParticipantes} onAddParticipant={abrirNovoParticipante} /></div>
          <div className="space-y-4">
              {efeitoInspecionado ? <EffectInspector efeito={efeitoInspecionado} participantes={participantes} onClose={() => setInspectedEffectId(null)} onDelete={deleteEfeito} /> : participanteSelecionado ? <section className="space-y-2"><p className="px-1 text-xs uppercase tracking-widest text-muted">Inspeção</p><ParticipantCard p={participanteSelecionado} combateId={combateAtivo.id} participantes={participantes} personagens={personagens} magias={magias} itens={itens} efeitos={efeitos.filter(efeito => efeito.alvo_id === participanteSelecionado.id || efeito.conjurador_id === participanteSelecionado.id)} isCurrent={combateAtivo.turno_atual_tipo !== 'evento' && participanteSelecionado.id === combateAtivo.turno_atual_id} onDelete={deleteParticipante} onRefresh={() => carregarCombate(combateAtivo.id)} onError={notify} /></section> : <section className="card border-dashed py-16 text-center text-muted"><p className="font-medium">Selecione uma entrada</p><p className="mt-1 text-sm">Escolha um participante ou evento para ver os detalhes.</p></section>}
            <div className="card"><button onClick={() => setNotasColapsado(previous => !previous)} className="mb-2 flex w-full items-center justify-between gap-2" title={notasColapsado ? 'Expandir notas' : 'Recolher notas'}><h2 className="flex items-center gap-2 text-sm font-semibold text-muted"><ScrollText className="h-4 w-4" /> Notas rápidas</h2>{notasColapsado ? <ChevronUp className="h-3.5 w-3.5 text-muted" /> : <ChevronDown className="h-3.5 w-3.5 text-muted" />}</button>{!notasColapsado && <textarea className="input min-h-16 resize-y" placeholder="Contadores, efeitos de cena e lembretes..." value={notas} onChange={event => setNotas(event.target.value)} onBlur={salvarNotas} />}</div>
            <div className="card"><h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-muted"><ScrollText className="h-4 w-4" /> Log de eventos</h3>{logs.length === 0 ? <p className="py-4 text-center text-sm text-muted">Nenhum evento ainda.</p> : <div className="max-h-48 space-y-1 overflow-y-auto text-sm">{logs.map(log => <div key={log.id} className="animate-enter-up flex gap-2 border-b border-border/50 py-1 text-muted"><span className="font-mono text-xs text-accent/60">R{log.rodada}</span><span className="text-xs">{log.detalhes}</span></div>)}</div>}</div>
          </div>
        </div>
      </div> : <CombatList combates={combates} novoNome={novoCombateNome} setNovoNome={setNovoCombateNome} criar={criarCombate} criando={criandoCombate} abrir={abrirCombate} deletar={deletarCombate} />}
    </main>

    <AddParticipantModal open={showAddPart} onClose={fecharNovoParticipante} participant={novoPart} setParticipant={setNovoPart} personagens={personagens} bestiario={bestiario} onSelectPersonagem={selecionarPersonagem} onSelectInimigo={selecionarInimigo} onAdd={adicionarParticipante} />
    <ExtraTurnModal open={showExtraTurnModal} onClose={() => setShowExtraTurnModal(false)} participantId={extraTurnParticipantId} setParticipantId={setExtraTurnParticipantId} participantes={participantes} onConfirm={confirmarTurnoExtra} />
    <EventModal open={showEventModal} event={newEvent} setEvent={setNewEvent} onClose={fecharEvento} onConfirm={confirmarNovoEvento} />
    <DiceRoller onRoll={compartilharRolagem} autor={turnoAtual?.tipo === 'jogador' ? turnoAtual.nome : 'Mestre'} /><Toast toast={toast} onClose={() => setToast(null)} /><ConfirmModal modal={confirmModal} onCancel={() => setConfirmModal(null)} onConfirm={async () => { const action = confirmModal?.onConfirm; setConfirmModal(null); if (action) await action(); }} />
  </div>;
}
