import { useState } from 'react';
import { api } from '../lib/api.js';
import { Droplet, Heart, Loader2, Package, Pencil, Sparkles, Swords, User, Wand2, X } from 'lucide-react';

export default function ParticipantCard({ p, combateId, participantes = [], personagens = [], magias = [], itens = [], efeitos = [], isCurrent, onDelete, onRefresh, onError }) {
  const [showEditModal, setShowEditModal] = useState(false);
  const [showMagias, setShowMagias] = useState(false);
  const [showItens, setShowItens] = useState(false);
  const [selectedMagia, setSelectedMagia] = useState('');
  const [selectedItem, setSelectedItem] = useState('');
  const [magicMode, setMagicMode] = useState('instantanea');
  const [magicCost, setMagicCost] = useState(0);
  const [effectDuration, setEffectDuration] = useState(1);
  const [effectDecay, setEffectDecay] = useState('alvo');
  const [effectTarget, setEffectTarget] = useState(p.id);
  const [creatingEffect, setCreatingEffect] = useState(false);
  const [usingItem, setUsingItem] = useState(false);
  const [hpValor, setHpValor] = useState('');
  const [mpValor, setMpValor] = useState('');
  const [editHpMax, setEditHpMax] = useState(p.hp_max);
  const [editMpMax, setEditMpMax] = useState(p.mp_max);
  const [editIniciativa, setEditIniciativa] = useState(p.iniciativa);

  const isJogador = p.tipo === 'jogador';
  const personagem = personagens.find(item => item.id === p.personagem_id);
  const nomesDeMagia = new Set(personagem ? parseMagicNames(personagem.magias).map(normalizeMagicName) : []);
  const magiasDoParticipante = personagem ? magias.filter(magia => nomesDeMagia.has(normalizeMagicName(magia.nome))) : [];
  const isDead = p.hp_atual <= 0;
  const hpPct = Math.max(0, Math.min(100, (p.hp_atual / Math.max(1, p.hp_max)) * 100));
  const mpPct = Math.max(0, Math.min(100, (p.mp_atual / Math.max(1, p.mp_max)) * 100));

  async function adjustHp(delta) {
    try {
      await api.updateParticipante(p.id, { hp_atual: Math.max(0, Math.min(p.hp_max, p.hp_atual + delta)) });
      onRefresh();
    } catch (error) { onError?.(error.message, 'error'); }
  }

  async function adjustMp(delta) {
    try {
      await api.updateParticipante(p.id, { mp_atual: Math.max(0, Math.min(p.mp_max, p.mp_atual + delta)) });
      onRefresh();
    } catch (error) { onError?.(error.message, 'error'); }
  }

  async function aplicarHp(positivo) {
    const valor = Number.parseInt(hpValor, 10);
    if (!valor) return;
    await adjustHp(positivo ? Math.abs(valor) : -Math.abs(valor));
    setHpValor('');
  }

  async function aplicarMp(positivo) {
    const valor = Number.parseInt(mpValor, 10);
    if (!valor) return;
    await adjustMp(positivo ? Math.abs(valor) : -Math.abs(valor));
    setMpValor('');
  }

  function abrirEdicao() {
    setEditHpMax(p.hp_max);
    setEditMpMax(p.mp_max);
    setEditIniciativa(p.iniciativa);
    setShowEditModal(true);
  }

  async function salvarEdicao() {
    const hpMax = Math.max(1, Number(editHpMax) || p.hp_max);
    const mpMax = Math.max(0, Number(editMpMax) || p.mp_max);
    try {
      await api.updateParticipante(p.id, {
        hp_max: hpMax,
        hp_atual: Math.min(p.hp_atual, hpMax),
        mp_max: mpMax,
        mp_atual: Math.min(p.mp_atual, mpMax),
        iniciativa: Number(editIniciativa) || 0,
      });
      setShowEditModal(false);
      onRefresh();
    } catch (error) { onError?.(error.message, 'error'); }
  }

  function abrirMagias() {
    setSelectedMagia('');
    setMagicMode('instantanea');
    setMagicCost(0);
    setEffectDuration(1);
    setEffectDecay('alvo');
    setEffectTarget(p.id);
    setShowMagias(true);
  }

  function abrirItens() {
    setSelectedItem('');
    setEffectTarget(p.id);
    setShowItens(true);
  }

  function selecionarMagia(id) {
    setSelectedMagia(id);
    const magia = magiasDoParticipante.find(item => item.id === Number(id));
    if (magia) setMagicCost(Number(magia.custo) || 0);
  }

  async function aplicarMagia() {
    const magia = magiasDoParticipante.find(item => item.id === Number(selectedMagia));
    const custo = Math.max(0, Number.parseInt(magicCost, 10) || 0);
    if (!magia || creatingEffect) return;
    if (custo > p.mp_atual) {
      onError?.('Mana insuficiente.', 'error');
      return;
    }
    setCreatingEffect(true);
    try {
      if (magicMode === 'instantanea') {
        await api.usarMagiaInstantanea(combateId, { magia_id: magia.id, participante_id: p.id, alvo_id: effectTarget || null, custo });
      } else {
        await api.createEfeito(combateId, {
          tipo: 'magia',
          nome: magia.nome,
          descricao: magia.descricao,
          alvo_id: effectDecay === 'alvo' ? effectTarget || null : null,
          conjurador_id: p.id,
          duracao: Number(effectDuration) || 1,
          decaimento: effectDecay,
        });
        if (custo > 0) await api.updateParticipante(p.id, { mp_atual: p.mp_atual - custo });
      }
      setShowMagias(false);
      onRefresh();
    } catch (error) {
      onError?.(error.message, 'error');
    } finally {
      setCreatingEffect(false);
    }
  }

  async function aplicarItem() {
    const item = itens.find(entry => entry.id === Number(selectedItem));
    if (!item || usingItem) return;
    setUsingItem(true);
    try {
      await api.usarItemInstantaneo(combateId, { item_id: item.id, participante_id: p.id, alvo_id: effectTarget || null });
      setShowItens(false);
      onRefresh();
    } catch (error) {
      onError?.(error.message, 'error');
    } finally {
      setUsingItem(false);
    }
  }

  return <>
    <div className={`card transition-all duration-300 ${isCurrent ? 'border-accent/50 shadow-[0_0_30px_rgba(143,216,172,0.1)] chamfered-sm' : ''} ${isDead ? 'opacity-40 grayscale' : ''}`}>
      <div className="mb-2 flex items-center gap-1.5">
        {p.foto ? <img src={p.foto} alt={p.nome} className="h-6 w-6 shrink-0 rounded-full border border-border object-cover" /> : <span className={isJogador ? 'text-muted' : 'text-accent'}>{isJogador ? <User className="h-4 w-4" /> : <Swords className="h-4 w-4" />}</span>}
         <h3 className="min-w-0 flex-1 truncate font-semibold" title={p.nome}>{p.nome}</h3>
         <span className={`hidden shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide sm:inline-flex ${isJogador ? 'bg-blue-400/10 text-blue-300' : 'bg-accent/10 text-accent'}`}>{isJogador ? 'Aliado' : 'Inimigo'}</span>
        <span className="rounded bg-surface2 px-1.5 py-0.5 font-mono text-xs text-muted">I{p.iniciativa}</span>
        <button onClick={abrirEdicao} className="icon-btn" title="Editar participante" aria-label="Editar participante"><Pencil className="h-3.5 w-3.5" /></button>
        {isJogador && <button onClick={abrirMagias} className="icon-btn" title="Usar magia" aria-label="Usar magia"><Wand2 className="h-3.5 w-3.5" /></button>}
        <button onClick={abrirItens} className="icon-btn" title="Usar item" aria-label="Usar item"><Package className="h-3.5 w-3.5" /></button>
        <button onClick={() => onDelete(p.id)} className="icon-btn" title={`Remover ${p.nome}`} aria-label={`Remover ${p.nome}`}><X className="h-4 w-4" /></button>
      </div>
      {efeitos.length > 0 && <div className="mb-2 flex flex-wrap gap-1">{efeitos.map(efeito => <span key={efeito.id} className="flex items-center gap-1 rounded bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent" title={efeito.descricao || efeito.nome}><Sparkles className="h-3 w-3" />{efeito.nome} · {efeito.duracao}</span>)}</div>}

      <Resource icon={Heart} label="HP" value={`${p.hp_atual} / ${p.hp_max}`} percent={hpPct} />
      <div className="mt-2 space-y-1">
        {isJogador && <Resource icon={Droplet} label="MP" value={`${p.mp_atual} / ${p.mp_max}`} percent={mpPct} blue />}
        <div className="flex gap-1">
          <button onClick={() => aplicarMp(false)} className="btn-ghost btn-sm w-8 text-blue-400 chamfered-sm border-r-0 rounded-r-none" disabled={!mpValor}>-</button>
          <input type="number" className="input flex-1 px-2 py-1 text-center text-xs rounded-none border-x-0" placeholder="MP" value={mpValor} onChange={event => setMpValor(event.target.value)} />
          <button onClick={() => aplicarMp(true)} className="btn-ghost btn-sm w-8 text-blue-400 chamfered-sm border-l-0 rounded-l-none" disabled={!mpValor}>+</button>
        </div>
      </div>
      <div className="mt-1 flex gap-1">
        <button onClick={() => aplicarHp(false)} className="btn-ghost btn-sm w-8 text-accent chamfered-sm border-r-0 rounded-r-none" disabled={!hpValor}>-</button>
        <input type="number" className="input flex-1 px-2 py-1 text-center text-xs rounded-none border-x-0" placeholder="HP" value={hpValor} onChange={event => setHpValor(event.target.value)} />
        <button onClick={() => aplicarHp(true)} className="btn-ghost btn-sm w-8 text-green-400 chamfered-sm border-l-0 rounded-l-none" disabled={!hpValor}>+</button>
      </div>
      {isJogador && <p className="mt-1.5 text-center text-xs text-muted">Turnos: {p.turnos_jogados}</p>}
    </div>

    {showEditModal && <Modal title="Editar participante" onClose={() => setShowEditModal(false)}>
      <div className="grid grid-cols-2 gap-2"><Field label="HP máximo" type="number" value={editHpMax} onChange={setEditHpMax} /><Field label="MP máximo" type="number" value={editMpMax} onChange={setEditMpMax} disabled={!isJogador} /><Field label="Iniciativa" type="number" value={editIniciativa} onChange={setEditIniciativa} /></div>
      <ModalActions onCancel={() => setShowEditModal(false)} onConfirm={salvarEdicao} confirmLabel="Salvar" />
    </Modal>}

    {showMagias && <Modal title={`Magias · ${p.nome}`} onClose={() => setShowMagias(false)}>
      {magiasDoParticipante.length === 0 ? <p className="text-sm text-muted">Nenhuma magia cadastrada nesta ficha.</p> : <>
        <select className="input" value={selectedMagia} onChange={event => selecionarMagia(event.target.value)}><option value="">Escolha uma magia</option>{magiasDoParticipante.map(magia => <option key={magia.id} value={magia.id}>{magia.nome}</option>)}</select>
        {selectedMagia && <div className="mt-3 space-y-2"><div className="grid grid-cols-2 gap-2"><label className="text-xs text-muted">Uso<select className="input mt-1" value={magicMode} onChange={event => setMagicMode(event.target.value)}><option value="instantanea">Instantânea</option><option value="efeito">Efeito</option></select></label><label className="text-xs text-muted">Custo MP<input className="input mt-1" type="number" min="0" value={magicCost} onChange={event => setMagicCost(event.target.value)} /></label></div>{magicMode === 'efeito' && <div className="grid grid-cols-2 gap-2"><label className="text-xs text-muted">Duração<input className="input mt-1" type="number" min="1" value={effectDuration} onChange={event => setEffectDuration(event.target.value)} /></label><label className="text-xs text-muted">Decaimento<select className="input mt-1" value={effectDecay} onChange={event => setEffectDecay(event.target.value)}><option value="alvo">Alvo</option><option value="conjurador">Conjurador</option></select></label></div>}{(magicMode === 'instantanea' || effectDecay === 'alvo') && <label className="block text-xs text-muted">Alvo<select className="input mt-1" value={effectTarget || ''} onChange={event => setEffectTarget(Number(event.target.value) || '')}><option value="">Nenhum</option>{participantes.map(participante => <option key={participante.id} value={participante.id}>{participante.nome}</option>)}</select></label>}<button onClick={aplicarMagia} className="btn-accent mt-2 w-full btn-sm" disabled={creatingEffect}>{creatingEffect ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} Usar magia</button></div>}
      </>}
    </Modal>}

    {showItens && <Modal title={`Itens · ${p.nome}`} onClose={() => setShowItens(false)}>
      {itens.length === 0 ? <p className="text-sm text-muted">Nenhum item cadastrado.</p> : <>
        <select autoFocus className="input" value={selectedItem} onChange={event => setSelectedItem(event.target.value)}><option value="">Selecionar item</option>{itens.map(item => <option key={item.id} value={item.id}>{item.nome}</option>)}</select>
        <label className="block text-xs text-muted">Alvo<select className="input mt-1" value={effectTarget || ''} onChange={event => setEffectTarget(Number(event.target.value) || '')}><option value="">Quem usou</option>{participantes.map(participante => <option key={participante.id} value={participante.id}>{participante.nome}</option>)}</select></label>
        <button onClick={aplicarItem} className="btn-accent w-full btn-sm" disabled={usingItem || !selectedItem}>{usingItem ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Package className="h-3.5 w-3.5" />} Usar item</button>
      </>}
    </Modal>}
  </>;
}

function parseMagicNames(value) {
  if (Array.isArray(value)) return value;
  if (typeof value !== 'string' || !value.trim()) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return value.split(',');
  }
}

function normalizeMagicName(value) {
  return String(value || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').trim().toLocaleLowerCase('pt-BR');
}

function Resource({ icon: Icon, label, value, percent, blue = false }) {
  return <div className="space-y-1"><div className="flex items-center justify-between text-sm"><span className="flex items-center gap-1 text-muted"><Icon className="h-3.5 w-3.5" />{label}</span><span className="font-mono text-xs font-semibold">{value}</span></div><div className="h-1.5 w-full bg-bg overflow-hidden flex"><div className={`h-full transition-all duration-300 relative ${blue ? 'bg-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.6)]' : 'bg-accent shadow-[0_0_10px_rgba(143,216,172,0.6)]'}`} style={{ width: `${percent}%` }}><div className="absolute right-0 top-0 bottom-0 w-1 bg-white/70" /></div></div></div>;
}

function Field({ label, type, value, onChange, disabled = false }) {
  return <label className="text-xs text-muted">{label}<input className="input mt-1" type={type} value={value} onChange={event => onChange(event.target.value)} disabled={disabled} /></label>;
}

function Modal({ title, onClose, children }) {
  return <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 px-4" onClick={onClose}><div className="card w-full max-w-md space-y-3 shadow-2xl" onClick={event => event.stopPropagation()}><div className="flex items-center justify-between"><h3 className="font-semibold">{title}</h3><button onClick={onClose} className="icon-btn" title="Fechar" aria-label="Fechar"><X className="h-4 w-4" /></button></div>{children}</div></div>;
}

function ModalActions({ onCancel, onConfirm, confirmLabel }) {
  return <div className="flex gap-2 pt-1"><button onClick={onConfirm} className="btn-accent flex-1 btn-sm">{confirmLabel}</button><button onClick={onCancel} className="btn-ghost flex-1 btn-sm">Cancelar</button></div>;
}
