import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api.js';
import { fileToResizedDataUrl, MAX_FOTO_LENGTH } from '../lib/photo.js';
import { BookOpen, FileUp, ImagePlus, Loader2, Pencil, Plus, Save, Search, Trash2, X } from 'lucide-react';

const empty = { nome: '', categoria: 'inimigo', hp_max: 25, dano: '', descricao: '', mecanicas: '', status: '' };

export default function Bestiario() {
  const [entries, setEntries] = useState([]);
  const [editing, setEditing] = useState(null);
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState(null);
  const [dragId, setDragId] = useState(null);
  const [uploadingId, setUploadingId] = useState(null);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const fileInputRef = useRef(null);
  const importInputRef = useRef(null);
  const pendingEntryRef = useRef(null);

  async function load() {
    try { setEntries(await api.getBestiario()); } catch (error) { flash(error.message, 'error'); }
  }
  useEffect(() => { load(); }, []);

  const categories = [...new Set(entries.map(entry => entry.categoria).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'pt-BR'));
  const normalizedSearch = normalize(search);
  const filteredEntries = entries.filter(entry => normalize([entry.nome, entry.categoria, entry.dano, entry.descricao, entry.mecanicas, entry.status].filter(Boolean).join(' ')).includes(normalizedSearch) && (!category || entry.categoria === category));

  function flash(text, type = 'success') {
    setMessage({ text, type });
    window.setTimeout(() => setMessage(null), 2600);
  }

  async function handlePhoto(entry, file) {
    if (!file) return;
    if (!file.type.startsWith('image/')) { flash('Use uma imagem JPG ou PNG.', 'error'); return; }
    setUploadingId(entry.id);
    try {
      const foto = await fileToResizedDataUrl(file);
      if (foto.length > MAX_FOTO_LENGTH) throw new Error('Imagem muito grande. Limite: 600 KB.');
      await api.setBestiarioFoto(entry.id, foto);
      await load();
      flash('Foto salva.');
    } catch (error) {
      flash(error.message, 'error');
    } finally {
      setUploadingId(null);
    }
  }

  async function removePhoto(entry, event) {
    event.stopPropagation();
    try {
      await api.removeBestiarioFoto(entry.id);
      await load();
      flash('Foto removida.');
    } catch (error) { flash(error.message, 'error'); }
  }

  async function save() {
    if (!editing?.nome?.trim()) return;
    try {
      if (editing.id) await api.updateBestiario(editing.id, editing);
      else await api.createBestiario(editing);
      setEditing(null);
      await load();
      flash('Inimigo salvo.');
    } catch (error) { flash(error.message, 'error'); }
  }

  async function importarObsidian(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    if (files.length === 0) return;
    setImporting(true);
    try {
      const payload = await Promise.all(files.map(async file => ({ name: file.name, content: await file.text() })));
      const result = await api.importObsidianBestiario(payload);
      await load();
       flash(`${result.importados} entrada${result.importados === 1 ? '' : 's'} importada${result.importados === 1 ? '' : 's'}.`);
    } catch (error) {
      flash(error.message, 'error');
    } finally {
      setImporting(false);
    }
  }

  async function remove(entry) {
    if (entry.is_preset) return;
    try {
      await api.deleteBestiario(entry.id);
      await load();
      flash('Entrada removida.');
    } catch (error) { flash(error.message, 'error'); }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
         <h2 className="flex items-center gap-2 text-lg font-semibold"><BookOpen className="h-5 w-5 text-accent" /> Bestiário</h2>
        <div className="flex gap-2"><button className="icon-btn border border-border" onClick={() => importInputRef.current?.click()} disabled={importing} title="Importar inimigos do Obsidian" aria-label="Importar inimigos do Obsidian">{importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}</button><button className="icon-btn-primary" onClick={() => setEditing({ ...empty })} title="Novo inimigo" aria-label="Criar novo inimigo"><Plus className="h-4 w-4" /></button></div>
      </div>
       <input ref={importInputRef} type="file" accept=".md,.markdown,text/markdown" multiple className="hidden" onChange={importarObsidian} />
       {message && <p className={`rounded-lg border px-3 py-2 text-sm ${message.type === 'error' ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-surface text-muted'}`}>{message.text}</p>}
       {entries.length > 0 && <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_12rem]"><label className="relative block"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" /><input className="input rounded-none pl-9" value={search} onChange={event => setSearch(event.target.value)} placeholder="Buscar inimigos..." aria-label="Buscar inimigos" /></label><select className="input rounded-none" value={category} onChange={event => setCategory(event.target.value)} aria-label="Filtrar por categoria"><option value="">Todas as categorias</option>{categories.map(value => <option key={value} value={value}>{value}</option>)}</select></div>}
       <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={event => { handlePhoto(pendingEntryRef.current, event.target.files[0]); event.target.value = ''; }} />
       {editing && <BestiaryForm value={editing} setValue={setEditing} save={save} cancel={() => setEditing(null)} />}
       {entries.length === 0 ? <div className="card border-dashed py-12 text-center text-muted"><BookOpen className="mx-auto mb-3 h-8 w-8" /><p>Nenhuma entrada.</p></div> : filteredEntries.length === 0 ? <div className="card border-dashed py-12 text-center text-muted"><Search className="mx-auto mb-3 h-7 w-7" /><p>Nenhum resultado encontrado.</p></div> : <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
         {filteredEntries.map(entry => (
          <div className="card" key={entry.id}>
            <div className={`relative mb-3 h-28 overflow-hidden rounded-lg border transition-colors ${dragId === entry.id ? 'border-accent bg-accent/10' : entry.foto ? 'border-border' : 'border-dashed border-border hover:border-accent'}`}
              onDragOver={event => { event.preventDefault(); setDragId(entry.id); }}
              onDragLeave={() => setDragId(null)}
              onDrop={event => { event.preventDefault(); setDragId(null); handlePhoto(entry, event.dataTransfer.files[0]); }}
              onClick={() => { pendingEntryRef.current = entry; fileInputRef.current?.click(); }}
              title="Arraste e solte uma imagem aqui (ou clique para escolher)">
              {uploadingId === entry.id ? <div className="flex h-full w-full items-center justify-center gap-2 text-muted text-xs"><Loader2 className="h-4 w-4 animate-spin" /> Salvando...</div>
                : entry.foto ? <>
                  <img src={entry.foto} alt={entry.nome} className="h-full w-full object-cover" />
                  <button className="absolute right-1.5 top-1.5 icon-btn bg-black/60" onClick={event => removePhoto(entry, event)} title="Remover foto" aria-label="Remover foto"><X className="h-3.5 w-3.5" /></button>
                </> : <div className="flex h-full w-full flex-col items-center justify-center gap-1 text-muted text-xs"><ImagePlus className="h-5 w-5" /><span>Arraste a foto</span></div>}
        </div>
            <div className="mb-2 flex items-start gap-2">
              <div className="flex-1"><h3 className="font-semibold">{entry.nome}</h3><p className="text-xs text-muted">{entry.categoria}</p></div>
               {entry.is_preset ? <span className="rounded bg-accent/20 px-2 py-0.5 text-xs text-accent">Preset</span> : <><button className="icon-btn" onClick={() => setEditing({ ...entry })} title="Editar inimigo" aria-label="Editar inimigo"><Pencil className="h-4 w-4" /></button><button className="icon-btn hover:text-accent" onClick={() => remove(entry)} title="Excluir inimigo" aria-label="Excluir inimigo"><Trash2 className="h-4 w-4" /></button></>}
             </div>
            <div className="grid grid-cols-2 gap-2 text-sm"><span className="text-muted">HP</span><span className="font-mono">{entry.hp_max}</span><span className="text-muted">Dano</span><span>{entry.dano || '-'}</span></div>
             <p className="mt-3 text-sm text-gray-300">{entry.descricao}</p>
             {entry.status && <p className="mt-2 text-xs text-accent">Status: {entry.status}</p>}
             <p className="mt-2 whitespace-pre-line text-xs text-muted">{entry.mecanicas}</p>
           </div>
        ))}
       </div>}
    </div>
  );
}

function normalize(value) {
  return String(value || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase('pt-BR');
}

function BestiaryForm({ value, setValue, save, cancel }) {
  const set = (field, next) => setValue({ ...value, [field]: next });
  return <div className="card space-y-3"><div className="flex items-center justify-between"><h3 className="font-semibold">{value.id ? 'Editar inimigo' : 'Novo inimigo'}</h3><button className="icon-btn" onClick={cancel} title="Fechar" aria-label="Fechar"><X className="h-4 w-4" /></button></div><div className="grid grid-cols-2 gap-2"><input className="input" placeholder="Nome" value={value.nome} onChange={e => set('nome', e.target.value)} /><input className="input" placeholder="Categoria" value={value.categoria} onChange={e => set('categoria', e.target.value)} /><input className="input" type="number" placeholder="HP" value={value.hp_max} onChange={e => set('hp_max', Number(e.target.value) || 0)} /><input className="input" placeholder="Dano" value={value.dano} onChange={e => set('dano', e.target.value)} /></div><input className="input" placeholder="Descrição" value={value.descricao} onChange={e => set('descricao', e.target.value)} /><input className="input" placeholder="Status inicial" value={value.status || ''} onChange={e => set('status', e.target.value)} /><textarea className="input min-h-24" placeholder="Habilidades e mecânicas" value={value.mecanicas} onChange={e => set('mecanicas', e.target.value)} /><div className="flex gap-2"><button className="btn-accent flex-1 gap-1.5" onClick={save}><Save className="h-4 w-4" /> Salvar</button><button className="btn-ghost flex-1" onClick={cancel}>Cancelar</button></div></div>;
}
