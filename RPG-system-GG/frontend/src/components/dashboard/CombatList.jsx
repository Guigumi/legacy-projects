import { ChevronRight, Loader2, Plus, Swords, Trash2 } from 'lucide-react';

export default function CombatList({ combates, novoNome, setNovoNome, criar, criando, abrir, deletar }) {
  return <div className="space-y-6">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="text-xs uppercase tracking-[0.24em] text-accent">Sessões</p><h2 className="mt-1 text-2xl font-semibold">Sessões de combate</h2><p className="mt-1 text-sm text-muted">Retome uma sessão ou crie outra.</p></div>
      <form className="flex w-full gap-2 sm:w-auto" onSubmit={event => { event.preventDefault(); criar(); }}>
        <input className="input min-w-0 flex-1 sm:w-64" placeholder="Nome da sessão (opcional)" value={novoNome} onChange={event => setNovoNome(event.target.value)} disabled={criando} aria-label="Nome da nova sessão" />
        <button type="submit" className="btn-chamfered h-10 w-10 shrink-0 p-0" title="Criar combate" aria-label="Criar combate" disabled={criando}>{criando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}</button>
      </form>
    </div>
    {combates.length === 0 ? <section className="card border-dashed border-accent/30 py-16 text-center">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-accent/20 bg-accent/10 text-accent"><Swords className="h-7 w-7" /></div>
       <h3 className="mt-4 font-semibold">Nenhuma sessão criada</h3>
       <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-muted">Crie uma sessão para acompanhar turnos e recursos.</p>
       <button onClick={() => document.querySelector('input[aria-label="Nome da nova sessão"]')?.focus()} className="btn-ghost btn-sm mt-5"><Plus className="h-3.5 w-3.5" /> Criar sessão</button>
    </section> : <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
      {combates.map(combate => <article key={combate.id} className="card group cursor-pointer border-transparent transition-all hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-[0_12px_35px_rgba(0,0,0,0.22)]" onClick={() => abrir(combate.id)}>
        <div className="flex items-start justify-between gap-3"><div className="min-w-0"><h3 className="truncate font-semibold">{combate.nome}</h3><p className="mt-1 text-xs text-muted">{formatDate(combate.criado_em)}</p></div><span className="shrink-0 rounded bg-accent/15 px-2 py-0.5 font-mono text-xs text-accent">R{combate.rodada}</span></div>
        <div className="mt-4 flex gap-2"><button className="icon-btn flex-1 border border-border group-hover:border-accent/40" onClick={event => { event.stopPropagation(); abrir(combate.id); }} title="Abrir combate" aria-label={`Abrir ${combate.nome}`}><ChevronRight className="h-4 w-4" /></button><button className="icon-btn" onClick={event => { event.stopPropagation(); deletar(combate.id); }} title="Excluir combate" aria-label={`Excluir ${combate.nome}`}><Trash2 className="h-3.5 w-3.5" /></button></div>
      </article>)}
    </div>}
  </div>;
}

function formatDate(value) {
  const date = new Date(`${value}Z`);
  return Number.isNaN(date.getTime()) ? 'Data desconhecida' : date.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}
