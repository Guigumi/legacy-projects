import { GripVertical, Plus, Users2 } from 'lucide-react';
import { useState } from 'react';

export default function BaseOrder({ participantes = [], selectedId, draggingId, onSelect, onDragStart, onDragEnd, onDrop, onAddParticipant }) {
  const [dragOverId, setDragOverId] = useState(null);
  return <section className="card p-0">
    <div className="flex items-center justify-between border-b border-border px-4 py-3"><div><p className="text-xs font-semibold uppercase tracking-widest text-muted">Ordem de iniciativa</p><p className="mt-1 text-[10px] text-muted">Arraste para reordenar</p></div><button onClick={onAddParticipant} className="icon-btn border border-border" title="Adicionar participante" aria-label="Adicionar participante"><Plus className="h-4 w-4" /></button></div>
    {participantes.length === 0 ? <p className="px-4 py-5 text-center text-xs text-muted">Nenhum participante.</p> : <div className="space-y-1 p-2">{participantes.map((participante, index) => {
      const isDropTarget = dragOverId === participante.id && draggingId !== participante.id;
      return <button type="button" key={participante.id} draggable onDragStart={() => onDragStart(participante.id)} onDragEnd={() => { setDragOverId(null); onDragEnd(); }} onDragEnter={() => setDragOverId(participante.id)} onDragOver={event => event.preventDefault()} onDrop={() => { setDragOverId(null); onDrop(participante.id); }} onClick={() => onSelect(participante.id)} className={`relative flex w-full cursor-grab items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-all ${selectedId === participante.id ? 'bg-accent/10 text-accent' : 'text-muted hover:bg-surface2'} ${draggingId === participante.id ? 'opacity-40' : ''} ${isDropTarget ? 'ring-1 ring-accent/60' : ''}`}>
        {isDropTarget && <span className="pointer-events-none absolute -top-1 left-2 right-2 h-0.5 rounded-full bg-accent" aria-hidden="true" />}<span className="w-5 text-center font-mono text-[10px] text-muted/60">{index + 1}</span><GripVertical className="h-3.5 w-3.5 text-muted/50" /><span className={`h-2 w-2 rounded-full ${participante.tipo === 'jogador' ? 'bg-blue-400' : 'bg-accent'}`} /><span className="flex-1 truncate">{participante.nome}</span><span className="font-mono text-[10px]">{participante.iniciativa}</span>
      </button>;
    })}</div>}
  </section>;
}
