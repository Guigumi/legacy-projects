import { useEffect, useRef, useState } from 'react';
import { Eye, ExternalLink, Image, Radio, Trash2, Volume2 } from 'lucide-react';
import { api } from '../lib/api.js';

export default function Transmitir() {
  const [state, setState] = useState({ transmissao: {}, fila: [], rolagens: [], combate: null });
  const [form, setForm] = useState({ musica_url: '', musica_titulo: '', imagem_url: '', volume: 0.7, mostrar_fila: true, mostrar_logs: true });
  const formReadyRef = useRef(false);
  const [message, setMessage] = useState(null);

  async function load() {
    try {
      const next = await api.getPlayerState();
      setState(next);
      if (next.transmissao && !formReadyRef.current) {
        setForm(previous => ({ ...previous, ...next.transmissao, mostrar_fila: Boolean(next.transmissao.mostrar_fila), mostrar_logs: Boolean(next.transmissao.mostrar_logs) }));
        formReadyRef.current = true;
      }
    } catch (error) { setMessage({ text: error.message, type: 'error' }); }
  }
  useEffect(() => { load(); const timer = window.setInterval(load, 1500); return () => window.clearInterval(timer); }, []);

  function flash(text, type = 'success') {
    setMessage({ text, type });
    window.setTimeout(() => setMessage(null), 2400);
  }

  async function save() {
    try { await api.updateTransmissao(form); await load(); flash('Transmissão atualizada.'); } catch (error) { flash(error.message, 'error'); }
  }

  async function clearRolls() {
    try { await api.clearRolls(); await load(); flash('Rolagens limpas.'); } catch (error) { flash(error.message, 'error'); }
  }

  return <div className="space-y-6">
     <header className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="flex items-center gap-2 text-lg font-semibold"><Radio className="h-5 w-5 text-accent" /> Transmitir</h2><p className="mt-1 text-sm text-muted">Escolha o que aparece na tela dos jogadores.</p></div><button className="btn-ghost btn-sm" onClick={() => window.open('/jogadores', '_blank', 'noopener,noreferrer')}><ExternalLink className="h-3.5 w-3.5" /> Abrir tela dos jogadores</button></header>
    {message && <p className={`rounded-lg border px-3 py-2 text-sm ${message.type === 'error' ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-surface text-muted'}`}>{message.text}</p>}
    <div className="grid gap-4 lg:grid-cols-[minmax(260px,22rem)_minmax(0,1fr)]">
      <section className="card space-y-4"><h3 className="font-semibold">Cena pública</h3><label className="block text-xs text-muted">URL da música<input className="input mt-1" placeholder="https://.../trilha.mp3" value={form.musica_url || ''} onChange={event => setForm({ ...form, musica_url: event.target.value })} /></label><label className="block text-xs text-muted">Nome da música<input className="input mt-1" placeholder="Clima da cena" value={form.musica_titulo || ''} onChange={event => setForm({ ...form, musica_titulo: event.target.value })} /></label><label className="block text-xs text-muted">Imagem ou mapa por URL<input className="input mt-1" placeholder="https://.../mapa.jpg" value={form.imagem_url || ''} onChange={event => setForm({ ...form, imagem_url: event.target.value })} /></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(form.mostrar_fila)} onChange={event => setForm({ ...form, mostrar_fila: event.target.checked })} /> Mostrar ordem de iniciativa</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(form.mostrar_logs)} onChange={event => setForm({ ...form, mostrar_logs: event.target.checked })} /> Mostrar rolagens e eventos</label><label className="block text-xs text-muted"><span className="flex items-center gap-2"><Volume2 className="h-3.5 w-3.5" /> Volume inicial: {Math.round((Number(form.volume) || 0) * 100)}%</span><input className="mt-2 w-full accent-accent" type="range" min="0" max="1" step="0.05" value={form.volume ?? 0.7} onChange={event => setForm({ ...form, volume: Number(event.target.value) })} /></label><button className="btn-accent w-full" onClick={save}><Radio className="h-4 w-4" /> Atualizar transmissão</button></section>
      <section className="space-y-4"><div className="card"><h3 className="mb-3 flex items-center gap-2 font-semibold"><Eye className="h-4 w-4 text-accent" /> Rolagens dos aliados</h3>{state.rolagens?.length ? <div className="max-h-64 space-y-2 overflow-y-auto">{state.rolagens.slice().reverse().map(roll => <div key={roll.id} className="flex items-center gap-3 border-b border-border/60 pb-2"><span className="text-2xl font-bold text-accent">{roll.resultado}</span><div className="min-w-0 flex-1"><p className="text-sm font-medium">{roll.autor} <span className="font-mono text-xs text-muted">({roll.expressao})</span></p><p className="truncate text-xs text-muted">{roll.detalhes}</p></div></div>)}</div> : <p className="text-sm text-muted">Nenhuma rolagem compartilhada.</p>}<button className="btn-ghost btn-sm mt-3" onClick={clearRolls} disabled={!state.rolagens?.length}><Trash2 className="h-3.5 w-3.5" /> Limpar rolagens</button></div><div className="card"><h3 className="mb-3 font-semibold">Ordem transmitida</h3>{!form.mostrar_fila ? <p className="text-sm text-muted">A fila está oculta para os jogadores.</p> : state.fila?.length ? <div className="space-y-1">{state.fila.map((item, index) => <div key={item.token} className={`flex items-center gap-2 rounded px-2 py-1.5 text-sm ${index === 0 ? 'bg-accent/10 text-accent' : 'text-muted'}`}><span className="w-5 font-mono text-xs">{index + 1}</span><span className="truncate">{item.participante?.nome || item.efeito?.nome}</span></div>)}</div> : <p className="text-sm text-muted">Nenhuma sessão ativa.</p>}</div></section>
    </div>
    {form.imagem_url && <div className="card overflow-hidden"><div className="mb-2 flex items-center gap-2 text-sm font-semibold"><Image className="h-4 w-4 text-accent" /> Prévia pública</div><img src={form.imagem_url} alt="Prévia da transmissão" className="max-h-72 w-full rounded-lg object-cover" /></div>}
  </div>;
}
