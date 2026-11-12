import { useEffect, useState } from 'react';
import { BookOpen, FileText, Music2, Plus, Radio, Trash2 } from 'lucide-react';
import { api } from '../lib/api.js';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { musicEmbed } from '../lib/music.js';


const blankScene = { titulo: '', conteudo: '', musica_url: '', musica_titulo: '' };

export default function Roteiros() {
  const [roteiros, setRoteiros] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [newTitle, setNewTitle] = useState('');
  const [scene, setScene] = useState({ ...blankScene });
  const [message, setMessage] = useState(null);

  async function load() {
    try {
      const next = await api.getRoteiros();
       if (!Array.isArray(next)) throw new Error('Não foi possível carregar os roteiros. Reinicie o backend e tente novamente.');
      setRoteiros(next);
      setSelectedId(previous => next.some(item => item.id === previous) ? previous : next[0]?.id || null);
    } catch (error) { setMessage({ text: error.message, type: 'error' }); }
  }
  useEffect(() => { load(); }, []);

  const selected = roteiros.find(item => item.id === selectedId);
  function flash(text, type = 'success') {
    setMessage({ text, type });
    window.setTimeout(() => setMessage(null), 2500);
  }

  async function createRoteiro() {
    if (!newTitle.trim()) return;
    try {
      const created = await api.createRoteiro({ titulo: newTitle.trim() });
      setNewTitle('');
      await load();
      setSelectedId(created.id);
      flash('Roteiro criado.');
    } catch (error) { flash(error.message, 'error'); }
  }

  async function addScene() {
    if (!selected || !scene.titulo.trim()) return;
    try {
      await api.createCena(selected.id, scene);
      setScene({ ...blankScene });
      await load();
      flash('Cena adicionada.');
    } catch (error) { flash(error.message, 'error'); }
  }

  async function removeScene(id) {
    try { await api.deleteCena(id); await load(); flash('Cena removida.'); } catch (error) { flash(error.message, 'error'); }
  }

  async function transmitScene(cena) {
    try {
      await api.updateTransmissao({ musica_url: cena.musica_url, musica_titulo: cena.musica_titulo });
      flash('Música enviada.');
    } catch (error) { flash(error.message, 'error'); }
  }

  return <div className="space-y-6">
    <header className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="flex items-center gap-2 text-lg font-semibold"><BookOpen className="h-5 w-5 text-accent" /> Roteiros</h2><p className="mt-1 text-sm text-muted">Escreva cenas e associe trilhas.</p></div></header>
    {message && <p className={`rounded-lg border px-3 py-2 text-sm ${message.type === 'error' ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-surface text-muted'}`}>{message.text}</p>}
    <div className="grid gap-4 lg:grid-cols-[minmax(220px,17rem)_minmax(0,1fr)]">
      <section className="card space-y-3"><h3 className="text-sm font-semibold text-muted">Roteiros</h3><div className="flex gap-2"><input className="input min-w-0 flex-1" placeholder="Novo roteiro" value={newTitle} onChange={event => setNewTitle(event.target.value)} onKeyDown={event => event.key === 'Enter' && createRoteiro()} /><button className="icon-btn-primary shrink-0" onClick={createRoteiro} title="Criar roteiro" aria-label="Criar roteiro"><Plus className="h-4 w-4" /></button></div>{roteiros.length === 0 ? <p className="py-6 text-center text-sm text-muted">Nenhum roteiro criado.</p> : <div className="space-y-1">{roteiros.map(roteiro => <button key={roteiro.id} onClick={() => setSelectedId(roteiro.id)} className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm ${selectedId === roteiro.id ? 'bg-accent/10 text-accent' : 'text-muted hover:bg-surface2'}`}><FileText className="h-4 w-4 shrink-0" /><span className="truncate">{roteiro.titulo}</span></button>)}</div>}</section>
      <section className="space-y-4">{!selected ? <div className="card border-dashed py-16 text-center text-muted">Crie ou selecione um roteiro.</div> : <><div className="card"><h3 className="text-xl font-semibold">{selected.titulo}</h3><p className="mt-1 text-sm text-muted">{selected.descricao || 'Adicione cenas para organizar a sessão.'}</p></div><div className="card space-y-3"><h3 className="flex items-center gap-2 text-sm font-semibold text-muted"><Plus className="h-4 w-4" /> Nova cena</h3><input className="input" placeholder="Título da cena" value={scene.titulo} onChange={event => setScene({ ...scene, titulo: event.target.value })} /><textarea className="input min-h-28" placeholder="Texto do roteiro, descrição e instruções do Mestre" value={scene.conteudo} onChange={event => setScene({ ...scene, conteudo: event.target.value })} /><div className="grid gap-2 sm:grid-cols-2"><input className="input" placeholder="URL da música (áudio ou embed)" value={scene.musica_url} onChange={event => setScene({ ...scene, musica_url: event.target.value })} /><input className="input" placeholder="Nome da música" value={scene.musica_titulo} onChange={event => setScene({ ...scene, musica_titulo: event.target.value })} /></div><button className="btn-accent btn-sm" onClick={addScene} disabled={!scene.titulo.trim()}><Plus className="h-3.5 w-3.5" /> Adicionar cena</button></div><div className="space-y-3">{selected.cenas?.map((cena, index) => <article key={cena.id} className="card"><div className="flex items-start gap-3"><span className="font-mono text-xs text-accent">{String(index + 1).padStart(2, '0')}</span><div className="min-w-0 flex-1"><h3 className="font-semibold">{cena.titulo}</h3>{cena.conteudo && <ReactMarkdown remarkPlugins={[remarkGfm]} className="mt-4 prose prose-sm prose-invert max-w-none text-muted">{cena.conteudo}</ReactMarkdown>}{cena.musica_url && (
  <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface2/30 p-2">
    <div className="flex min-w-0 flex-1 items-center gap-2 text-sm font-medium">
      <Music2 className="h-4 w-4 shrink-0 text-accent" />
      <span className="truncate">{cena.musica_titulo || 'Trilha Sonora'}</span>
    </div>
    <div className="flex items-center gap-2">
      {musicEmbed(cena.musica_url, false) ? (
        <iframe title="Mini Player" src={musicEmbed(cena.musica_url, false)} className="h-9 w-64 rounded" allow="encrypted-media" />
      ) : (
        <audio src={cena.musica_url} controls preload="none" className="h-9 w-64" />
      )}
      <button className="btn-accent btn-sm shrink-0" onClick={() => transmitScene(cena)} title="Transmitir música">
        <Radio className="h-3.5 w-3.5" /> Transmitir
      </button>
    </div>
  </div>
)}</div><button className="icon-btn text-accent" onClick={() => removeScene(cena.id)} title="Remover cena" aria-label="Remover cena"><Trash2 className="h-3.5 w-3.5" /></button></div></article>)}</div></>}</section>
    </div>
  </div>;
}
