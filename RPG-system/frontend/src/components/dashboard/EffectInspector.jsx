import { Sparkles, Trash2, X } from 'lucide-react';

export default function EffectInspector({ efeito, participantes, onClose, onDelete }) {
  const alvo = participantes.find(participante => participante.id === efeito.alvo_id);
  const conjurador = participantes.find(participante => participante.id === efeito.conjurador_id);
  const decayLabel = { alvo: 'Turno do alvo', conjurador: 'Turno do conjurador', evento: 'Turno do evento' }[efeito.decaimento] || efeito.decaimento;
  const isEvent = efeito.tipo === 'evento';
  return <section className={`card ${isEvent ? 'border-violet-400/40 bg-violet-400/[0.04]' : 'border-accent/30'}`}>
    <div className="mb-5 flex items-start justify-between gap-3"><div><p className={`text-xs uppercase tracking-widest ${isEvent ? 'text-violet-300' : 'text-accent'}`}>{isEvent ? 'Evento' : 'Magia'}</p><h2 className="mt-1 flex items-center gap-2 text-xl font-semibold"><Sparkles className={`h-5 w-5 ${isEvent ? 'text-violet-300' : 'text-accent'}`} />{efeito.nome}</h2></div><button onClick={onClose} className="icon-btn" title="Fechar" aria-label="Fechar"><X className="h-4 w-4" /></button></div>
    <div className="grid grid-cols-2 gap-2 text-sm"><Info label="Duração" value={`${efeito.duracao} turnos`} accent={isEvent} /><Info label="Decaimento" value={decayLabel} /><Info label="Alvo" value={alvo?.nome || 'Não informado'} /><Info label="Conjurador" value={conjurador?.nome || 'Mestre'} /></div>
    {efeito.descricao && <p className="mt-4 rounded-lg border border-border bg-bg/40 p-3 text-sm leading-relaxed text-muted">{efeito.descricao}</p>}
    <div className="mt-5 flex justify-end"><button onClick={() => onDelete(efeito.id)} className="btn-ghost btn-sm text-accent"><Trash2 className="h-3.5 w-3.5" /> Remover {isEvent ? 'evento' : 'efeito'}</button></div>
  </section>;
}

function Info({ label, value, accent = false }) {
  return <div className="rounded-lg bg-bg/50 p-3"><p className="text-xs text-muted">{label}</p><p className={`mt-1 ${accent ? 'font-mono text-lg text-violet-300' : ''}`}>{value}</p></div>;
}
