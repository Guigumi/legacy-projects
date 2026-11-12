import { Dices, Redo2, Undo2 } from 'lucide-react';

export default function CombatStatus({ combate, turnoAtual, efeitoAtual, history, onRollInitiative, onUndo, onRedo }) {
  const currentName = efeitoAtual?.nome || turnoAtual?.nome;
  const currentType = efeitoAtual ? 'Evento' : turnoAtual ? (turnoAtual.tipo === 'jogador' ? 'Aliado' : 'Inimigo') : 'Aguardando iniciativa';
  return <section className={`card flex flex-wrap items-center gap-3 border-l-4 ${efeitoAtual ? 'border-l-violet-400' : turnoAtual?.tipo === 'jogador' ? 'border-l-blue-400' : 'border-l-accent'}`}>
    <div className="min-w-[180px] flex-1">
       <p className="text-xs uppercase tracking-widest text-muted">Turno · Rodada {combate.rodada}</p>
       <p className="mt-1 truncate text-xl font-bold">{currentName || <span className="text-muted">Sem turno</span>}</p>
      <p className={`mt-1 text-xs ${efeitoAtual ? 'text-violet-300' : turnoAtual?.tipo === 'jogador' ? 'text-blue-300' : 'text-muted'}`}>{currentType}</p>
    </div>
    <div className="flex items-center gap-1">
      <button onClick={onRollInitiative} className="icon-btn border border-border" title="Rolar iniciativa (D20 para todos)" aria-label="Rolar iniciativa"><Dices className="h-4 w-4" /></button>
      <div className="flex gap-1 border-l border-border pl-2">
        <button onClick={onUndo} disabled={!history.canUndo} className="icon-btn disabled:cursor-not-allowed disabled:opacity-30" title="Desfazer (Ctrl+Z)" aria-label="Desfazer"><Undo2 className="h-4 w-4" /></button>
        <button onClick={onRedo} disabled={!history.canRedo} className="icon-btn disabled:cursor-not-allowed disabled:opacity-30" title="Refazer (Ctrl+Y ou Ctrl+Shift+Z)" aria-label="Refazer"><Redo2 className="h-4 w-4" /></button>
      </div>
    </div>
  </section>;
}
