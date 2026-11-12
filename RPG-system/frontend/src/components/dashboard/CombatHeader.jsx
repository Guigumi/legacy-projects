import { ArrowLeft, BookOpen, Database, ExternalLink, LogOut, Package, Radio, ScrollText, Swords, Trash2, User, Wand2 } from 'lucide-react';

export default function CombatHeader({ view, tab, combate, onBack, onTabChange, onOpenPlayerView, onDelete, onLogout }) {
  const items = [
    { key: 'sessao', label: 'Sessão', icon: Swords },
    { key: 'roteiros', label: 'Roteiros', icon: ScrollText },
    { key: 'transmitir', label: 'Transmitir', icon: Radio },
    { key: 'fichas', label: 'Fichas', icon: User },
    { key: 'inimigos', label: 'Inimigos', icon: BookOpen },
    { key: 'magias', label: 'Magias', icon: Wand2 },
    { key: 'itens', label: 'Itens', icon: Package },
    { key: 'dados', label: 'Dados', icon: Database },
  ];

  return <>
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-52 flex-col border-r border-border/80 bg-surface/80 px-3 py-4 backdrop-blur-xl lg:flex">
      <div className="flex items-center gap-3 border-b border-border/70 px-2 pb-5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center bg-accent text-bg chamfered"><Swords className="h-5 w-5" /></div>
        <div className="min-w-0"><p className="text-sm font-semibold tracking-tight">RPG System GG</p><p className="text-[9px] uppercase tracking-widest text-muted">Mestre</p></div>
      </div>

      {view === 'combate' && combate ? <div className="mt-4 border-l-2 border-accent/60 bg-accent/5 px-3 py-2.5">
        <p className="text-[10px] uppercase tracking-[0.2em] text-accent">Sessão ativa</p>
        <p className="mt-1 truncate text-sm font-semibold">{combate.nome}</p>
        <p className="mt-0.5 font-mono text-xs text-muted">Rodada {combate.rodada}</p>
      </div> : <div className="mt-5 px-2 text-xs leading-relaxed text-muted">Aventura e combate.</div>}

      <nav className="mt-5 space-y-1" aria-label="Seções principais">
        <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.22em] text-muted">Navegação</p>
        {items.map(({ key, label, icon: Icon }) => <NavButton key={key} active={tab === key} onClick={() => onTabChange(key)} title={label} ariaLabel={label}><Icon className="h-4 w-4" /><span>{label}</span></NavButton>)}
      </nav>

      <div className="mt-auto space-y-1 border-t border-border/70 pt-3">
        {view === 'combate' && combate && <button onClick={onBack} className="sidebar-action"><ArrowLeft className="h-4 w-4" /> Sessões</button>}
        <button onClick={onOpenPlayerView} className="sidebar-action"><ExternalLink className="h-4 w-4" /> Tela dos jogadores</button>
        {view === 'combate' && combate && <button onClick={() => onDelete(combate.id)} className="sidebar-action text-accent hover:bg-accent/10"><Trash2 className="h-4 w-4" /> Encerrar combate</button>}
        <button onClick={onLogout} className="sidebar-action"><LogOut className="h-4 w-4" /> Sair</button>
      </div>
    </aside>

    <header className="sticky top-0 z-20 border-b border-border/80 bg-surface/90 px-4 py-3 backdrop-blur-xl lg:hidden">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center bg-accent text-bg chamfered"><Swords className="h-4 w-4" /></div>
        <div className="min-w-0 flex-1"><h1 className="truncate text-sm font-semibold">{view === 'combate' && combate ? combate.nome : 'RPG System GG'}</h1><p className="text-[10px] uppercase tracking-widest text-muted">{view === 'combate' && combate ? `Rodada ${combate.rodada}` : 'Mestre'}</p></div>
        <button onClick={onOpenPlayerView} className="icon-btn" title="Abrir tela dos jogadores" aria-label="Abrir tela dos jogadores"><ExternalLink className="h-4 w-4" /></button>
        <button onClick={onLogout} className="icon-btn" title="Sair" aria-label="Sair"><LogOut className="h-4 w-4" /></button>
      </div>
      <nav className="mt-3 flex gap-1 overflow-x-auto pb-0.5" aria-label="Seções principais">
        {items.map(({ key, label, icon: Icon }) => <NavButton key={key} active={tab === key} onClick={() => onTabChange(key)} title={label} ariaLabel={label}><Icon className="h-4 w-4" /><span>{label}</span></NavButton>)}
      </nav>
    </header>
  </>;
}

function NavButton({ active, onClick, title, ariaLabel, children }) {
  return <button onClick={onClick} className={`flex shrink-0 items-center gap-2.5 px-3 py-1.5 text-xs transition-colors ${active ? 'bg-accent text-bg shadow-[0_0_24px_rgba(91,190,139,0.16)]' : 'text-muted hover:bg-surface2 hover:text-gray-100'}`} title={title} aria-label={ariaLabel} aria-current={active ? 'page' : undefined}>{children}</button>;
}
