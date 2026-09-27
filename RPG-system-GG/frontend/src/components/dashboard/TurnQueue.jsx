import { useState } from 'react';
import { CalendarClock, ChevronDown, ChevronRight, ChevronUp, CircleDot, Droplet, GripVertical, Heart, Sparkles, Zap } from 'lucide-react';

export default function TurnQueue({ fila = [], participantes = [], efeitos = [], currentToken, onSelectParticipant, onSelectEffect, onReorder, onCreateEvent, onNextTurn, onExtraTurn }) {
  const [draggingToken, setDraggingToken] = useState(null);
  const [dragOverToken, setDragOverToken] = useState(null);
  const [expanded, setExpanded] = useState(false);
  if (fila.length === 0) return <section className="card border-dashed border-accent/30 py-10 text-center">
    <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-accent/10 text-accent"><CalendarClock className="h-5 w-5" /></div>
    <h3 className="mt-3 text-sm font-semibold">Fila vazia</h3><p className="mx-auto mt-1 max-w-xs text-xs leading-relaxed text-muted">Adicione participantes ou crie um evento para começar.</p>
    <div className="mt-5 flex justify-center gap-2"><button onClick={onCreateEvent} className="btn-ghost btn-sm"><CalendarClock className="h-3.5 w-3.5" /> Criar evento</button></div>
  </section>;
  const effectsByParticipant = new Map(participantes.map(participante => [participante.id, efeitos.filter(efeito => efeito.alvo_id === participante.id || efeito.conjurador_id === participante.id)]));
  const visibleItems = expanded ? fila : fila.slice(0, 8);
  function dropEntry(targetToken) {
    if (!draggingToken || draggingToken === targetToken) return;
    const next = [...fila];
    const from = next.findIndex(item => item.token === draggingToken);
    const to = next.findIndex(item => item.token === targetToken);
    if (from < 0 || to < 0) return;
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    setDraggingToken(null);
    setDragOverToken(null);
    onReorder(next.map(item => item.token));
  }
  return <section className="card overflow-hidden border-accent/30 p-0">
    <div className="flex items-center justify-between border-b border-border bg-surface2/60 px-4 py-3"><div><div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted"><CircleDot className="h-3.5 w-3.5 text-accent" /> Fila de ação</div><p className="mt-1 pl-5 text-[10px] text-muted">Arraste para reordenar</p></div><div className="flex gap-1"><button onClick={onExtraTurn} className="icon-btn border border-border text-accent hover:border-accent/40 hover:bg-accent/10" title="Turno extra"><Zap className="h-4 w-4" /></button><button onClick={onCreateEvent} className="icon-btn border border-border" title="Criar evento na fila"><CalendarClock className="h-4 w-4" /></button></div></div>
    <div className="space-y-1 p-2">
      {visibleItems.map((item, index) => {
        const current = item.token === currentToken;
        const isEvent = item.tipo === 'evento';
        const participant = item.participante;
        const effect = item.efeito;
        const label = isEvent ? effect?.nome : participant?.nome;
        const hp = participant ? Math.max(0, Math.min(100, (participant.hp_atual / Math.max(1, participant.hp_max)) * 100)) : 0;
        const mp = participant?.tipo === 'jogador' ? Math.max(0, Math.min(100, (participant.mp_atual / Math.max(1, participant.mp_max)) * 100)) : 0;
        const status = participant ? effectsByParticipant.get(participant.id) || [] : [];
        const isDropTarget = dragOverToken === item.token && draggingToken !== item.token;
        return <button type="button" draggable key={`${item.token}-${index}`} onDragStart={() => setDraggingToken(item.token)} onDragEnd={() => { setDraggingToken(null); setDragOverToken(null); }} onDragEnter={() => setDragOverToken(item.token)} onDragOver={event => event.preventDefault()} onDrop={() => dropEntry(item.token)} onClick={() => isEvent ? onSelectEffect(item.efeito.id) : onSelectParticipant(participant.id)} className={`group relative flex w-full items-center gap-3 border px-3 py-2 text-left transition-all ${current ? 'border-accent/80 bg-accent/20 text-gray-100 shadow-[0_0_24px_rgba(143,216,172,0.16)] chamfered translate-x-2' : 'rounded-lg border-transparent bg-bg/40 text-muted hover:border-border hover:bg-surface2'} ${isDropTarget ? 'border-accent/70 bg-accent/5 ring-1 ring-accent/30 rounded-lg' : ''} ${draggingToken === item.token ? 'scale-[0.98] opacity-45' : ''}`} title={isEvent ? `${label} · ${effect?.duracao} turnos restantes` : `Inspecionar ${label}`}>
          {isDropTarget && <span className="pointer-events-none absolute -top-1 left-3 right-3 h-0.5 rounded-full bg-accent shadow-[0_0_8px_rgba(49,235,49,0.7)]" aria-hidden="true" />}
          <span className={`w-7 shrink-0 text-center font-mono text-[10px] ${current ? 'text-accent font-bold tracking-wider' : 'text-muted/60'}`}>{current ? 'ATU' : String(index + 1).padStart(2, '0')}</span><GripVertical className="h-4 w-4 shrink-0 text-muted/50" />
          {isEvent ? <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-violet-400/40 bg-violet-400/10 text-violet-300"><Sparkles className="h-4 w-4" /></span> : participant?.foto ? <img src={participant.foto} alt="" className={`h-9 w-9 shrink-0 rounded-full border object-cover ${participant.tipo === 'jogador' ? 'border-blue-400/50' : 'border-accent/50'}`} /> : <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border text-xs font-bold ${participant?.tipo === 'jogador' ? 'border-blue-400/50 bg-blue-400/10 text-blue-300' : 'border-accent/50 bg-accent/10 text-accent'}`}>{label?.slice(0, 1).toUpperCase()}</span>}
          <span className="min-w-0 flex-1"><span className="flex items-center gap-2"><span className="truncate text-sm font-medium">{label}</span>{isEvent ? <span className="shrink-0 rounded bg-violet-400/10 px-1.5 py-0.5 text-[10px] text-violet-300">{effect?.duracao}t</span> : <span className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold ${participant?.tipo === 'jogador' ? 'bg-blue-400/10 text-blue-300' : 'bg-accent/10 text-accent'}`}>{participant?.tipo === 'jogador' ? 'Aliado' : 'Inimigo'}</span>}</span>{participant ? <><span className="mt-1 flex gap-1"><MiniBar icon={Heart} value={hp} color="bg-rose-400" /><MiniBar icon={Droplet} value={mp} color="bg-blue-400" /></span>{status.length > 0 && <span className="mt-1 flex gap-1 overflow-hidden">{status.slice(0, 3).map(statusItem => <span key={statusItem.id} className="truncate rounded bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent">{statusItem.nome} · {statusItem.duracao}</span>)}{status.length > 3 && <span className="text-[10px] text-muted">+{status.length - 3}</span>}</span>}</> : null}</span>
        </button>;
      })}
      {fila.length > 8 && <button onClick={() => setExpanded(previous => !previous)} className="flex w-full items-center justify-center gap-1 py-2 text-xs text-muted hover:text-accent">{expanded ? <><ChevronUp className="h-3.5 w-3.5" /> Mostrar menos</> : <><ChevronDown className="h-3.5 w-3.5" /> Mostrar mais {fila.length - 8} entradas</>}</button>}
    </div>
    <div className="mt-3">
      <button onClick={onNextTurn} className="btn-chamfered w-full py-2.5 font-bold tracking-widest uppercase text-xs" title="Avançar turno (N)">Próximo turno <ChevronRight className="h-4 w-4" /></button>
    </div>
</section>;
}

function MiniBar({ icon: Icon, value, color }) {
  return <span className="flex h-1.5 flex-1 overflow-hidden rounded-full bg-border" title={`${Math.round(value)}%`}><span className={`h-full ${color}`} style={{ width: `${value}%` }} /><Icon className="hidden" /></span>;
}
