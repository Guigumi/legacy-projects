import { useEffect, useRef } from 'react';
import { CalendarClock, X, Zap } from 'lucide-react';

export function AddParticipantModal({ open, onClose, participant, setParticipant, personagens, bestiario, onSelectPersonagem, onSelectInimigo, onAdd }) {
  if (!open) return null;
  return <Modal title="Novo participante" onClose={onClose}>
    {participant.tipo === 'jogador' && personagens.length > 0 && <select autoFocus={!!participant.personagem_id} className="input" value={participant.personagem_id || ''} onChange={event => onSelectPersonagem(event.target.value)}><option value="">Selecionar ficha</option>{personagens.map(personagem => <option key={personagem.id} value={personagem.id}>{personagem.nome}{personagem.is_preset ? ' (preset)' : ''}</option>)}</select>}
    {participant.tipo === 'inimigo' && bestiario.length > 0 && <select autoFocus={!!participant.bestiario_id} className="input" value={participant.bestiario_id || ''} onChange={event => onSelectInimigo(event.target.value)}><option value="">Selecionar inimigo</option>{bestiario.map(inimigo => <option key={inimigo.id} value={inimigo.id}>{inimigo.nome} - {inimigo.categoria}</option>)}</select>}
    <input autoFocus={!participant.personagem_id && !participant.bestiario_id} className="input" placeholder="Nome" value={participant.nome} onChange={event => setParticipant({ ...participant, nome: event.target.value })} disabled={!!participant.personagem_id || !!participant.bestiario_id} />
    <select className="input" value={participant.tipo} onChange={event => setParticipant({ ...participant, tipo: event.target.value, personagem_id: null, bestiario_id: null, nome: '' })}><option value="jogador">Jogador</option><option value="inimigo">Inimigo</option></select>
    <div className="grid grid-cols-3 gap-2"><input className="input" type="number" placeholder="Iniciativa" value={participant.iniciativa} onChange={event => setParticipant({ ...participant, iniciativa: Number(event.target.value) || 0 })} /><input className="input" type="number" placeholder="HP máximo" value={participant.hp_max} onChange={event => setParticipant({ ...participant, hp_max: Number(event.target.value) || 100, hp_atual: Number(event.target.value) || 100 })} disabled={!!participant.personagem_id || !!participant.bestiario_id} />{participant.tipo === 'jogador' && <input className="input" type="number" placeholder="MP máximo" value={participant.mp_max} onChange={event => setParticipant({ ...participant, mp_max: Number(event.target.value) || 100, mp_atual: Number(event.target.value) || 100 })} disabled={!!participant.personagem_id} />}</div>
    <ModalActions onCancel={onClose} onConfirm={onAdd} confirmLabel="Adicionar" />
  </Modal>;
}

export function ExtraTurnModal({ open, onClose, participantId, setParticipantId, participantes, onConfirm }) {
  if (!open) return null;
  return <Modal title="Turno extra" onClose={onClose}>
    <select autoFocus className="input" value={participantId} onChange={event => setParticipantId(event.target.value)}><option value="">Selecionar participante</option>{participantes.map(participante => <option key={participante.id} value={participante.id}>{participante.nome}</option>)}</select>
    <ModalActions onCancel={onClose} onConfirm={onConfirm} confirmLabel="Adicionar ao topo" icon={Zap} disabled={!participantId} />
  </Modal>;
}

export function EventModal({ open, event, setEvent, onClose, onConfirm }) {
  if (!open) return null;
  return <Modal title="Novo evento" onClose={onClose}>
    <input className="input" placeholder="Nome do evento" value={event.nome} onChange={value => setEvent({ ...event, nome: value.target.value })} autoFocus />
    <textarea className="input min-h-20 resize-y" placeholder="Descrição opcional" value={event.descricao} onChange={value => setEvent({ ...event, descricao: value.target.value })} />
    <input className="input" type="number" min="1" max="999" placeholder="Duração em turnos" value={event.duracao} onChange={value => setEvent({ ...event, duracao: value.target.value })} />
    <ModalActions onCancel={onClose} onConfirm={onConfirm} confirmLabel="Adicionar evento" icon={CalendarClock} disabled={!event.nome.trim()} />
  </Modal>;
}

function Modal({ title, onClose, children }) {
  const dialogRef = useRef(null);
  useEffect(() => {
    const activeElement = document.activeElement;
    if (!dialogRef.current?.contains(activeElement)) {
      const focusable = dialogRef.current?.querySelector('input:not([disabled]), select:not([disabled]), textarea, button');
      focusable?.focus();
    }
    function handleKeyDown(event) {
      if (event.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);
  return <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 px-4 backdrop-blur-[2px]" onClick={onClose}><div ref={dialogRef} role="dialog" aria-modal="true" aria-label={title} className="card max-h-[90vh] w-full max-w-md space-y-3 overflow-y-auto shadow-2xl" onClick={event => event.stopPropagation()}><div className="flex items-center justify-between"><h3 className="font-semibold">{title}</h3><button onClick={onClose} className="icon-btn" title="Fechar" aria-label="Fechar"><X className="h-4 w-4" /></button></div>{children}</div></div>;
}

function ModalActions({ onCancel, onConfirm, confirmLabel, icon: Icon, disabled = false }) {
  return <div className="flex gap-2 pt-1"><button type="button" onClick={onConfirm} className="btn-accent flex-1 btn-sm" disabled={disabled}>{Icon && <Icon className="h-3.5 w-3.5" />}{confirmLabel}</button><button type="button" onClick={onCancel} className="btn-ghost flex-1 btn-sm">Cancelar</button></div>;
}
