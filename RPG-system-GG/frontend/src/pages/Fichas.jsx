import { useState, useEffect, useRef } from 'react';
import { api } from '../lib/api.js';
import { fileToResizedDataUrl, MAX_FOTO_LENGTH } from '../lib/photo.js';
import { FileUp, Plus, Pencil, Search, Trash2, X, Save, User, ImagePlus, Loader2 } from 'lucide-react';
import { ConfirmModal, Toast } from '../components/Overlay.jsx';

export default function Fichas() {
  const [personagens, setPersonagens] = useState([]);
  const [racas, setRacas] = useState([]);
  const [armas, setArmas] = useState([]);
  const [editing, setEditing] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [toast, setToast] = useState(null);
  const [confirmModal, setConfirmModal] = useState(null);
  const [importing, setImporting] = useState(false);
  const [dragId, setDragId] = useState(null);
  const [uploadingId, setUploadingId] = useState(null);
  const [search, setSearch] = useState('');
  const fileInputRef = useRef(null);
  const importInputRef = useRef(null);
  const pendingEntryRef = useRef(null);

  function flash(message, type = 'success') {
    setToast({ message, type });
    window.setTimeout(() => setToast(null), 2400);
  }

  async function handlePhoto(personagem, file) {
    if (!file) return;
    if (!file.type.startsWith('image/')) { flash('Use uma imagem JPG ou PNG.', 'error'); return; }
    setUploadingId(personagem.id);
    try {
      const foto = await fileToResizedDataUrl(file);
      if (foto.length > MAX_FOTO_LENGTH) throw new Error('Imagem muito grande. Limite: 600 KB.');
      await api.setPersonagemFoto(personagem.id, foto);
      await carregar();
       flash('Foto salva.');
    } catch (error) {
      flash(error.message, 'error');
    } finally {
      setUploadingId(null);
    }
  }

  async function removePhoto(personagem, event) {
    event.stopPropagation();
    try {
      await api.removePersonagemFoto(personagem.id);
      await carregar();
      flash('Foto removida.');
    } catch (error) { flash(error.message, 'error'); }
  }

  async function carregar() {
    try {
      const [nextPersonagens, nextRacas, nextArmas] = await Promise.all([api.getPersonagens(), api.getRacas(), api.getArmas()]);
      setPersonagens(nextPersonagens);
      setRacas(nextRacas);
      setArmas(nextArmas);
    } catch (error) { flash(error.message, 'error'); }
  }

  useEffect(() => { carregar(); }, []);

  const normalizedSearch = normalize(search);
  const personagensFiltrados = personagens.filter(personagem => normalize([
    personagem.nome,
    personagem.nome_jogador,
    personagem.raca,
    personagem.arma,
    personagem.historia,
    personagem.aliados,
    personagem.status,
    personagem.notas,
  ].filter(Boolean).join(' ')).includes(normalizedSearch));

  async function salvar() {
     if (!editing.nome?.trim()) { flash('Informe o nome.', 'error'); return; }
    try {
      const payload = {
        ...editing,
        magias: JSON.stringify(String(editing.magias || '').split(',').map(magia => magia.trim()).filter(Boolean)),
      };
      if (editing.id) await api.updatePersonagem(editing.id, payload);
      else await api.createPersonagem(payload);
      setEditing(null);
      setShowForm(false);
      await carregar();
       flash('Ficha salva.');
    } catch (error) { flash(error.message, 'error'); }
  }

  async function importarObsidian(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    if (files.length === 0) return;
    setImporting(true);
    try {
      const payload = await Promise.all(files.map(async file => ({ name: file.name, content: await file.text() })));
      const result = await api.importObsidianPersonagens(payload);
      await carregar();
      flash(`${result.importados} ficha${result.importados === 1 ? '' : 's'} importada${result.importados === 1 ? '' : 's'} do Obsidian.`);
    } catch (error) {
      flash(error.message, 'error');
    } finally {
      setImporting(false);
    }
  }

  async function deletar(id) {
    const personagem = personagens.find(item => item.id === id);
    setConfirmModal({
      title: 'Excluir ficha',
      message: `Excluir ${personagem?.nome || 'esta ficha'} permanentemente?`,
      onConfirm: async () => {
        try {
          await api.deletePersonagem(id);
          await carregar();
          flash('Ficha excluída.');
        } catch (error) { flash(error.message, 'error'); }
      },
    });
  }

  function novoPersonagem() {
    setEditing({
      nome: '', nome_jogador: '', raca: '', arma: '', nivel: 0, idade: '',
      aparencia: '', historia: '', aliados: '', status: '', notas: '', hp_max: 100, mp_max: 100, vida: 1, mana: 1, inteligencia: 1, agilidade: 1, vigor: 1,
      magias: '', inventario: '', is_preset: 0,
    });
    setShowForm(true);
  }

  function editar(p) {
    let magias = p.magias || '';
    try { magias = JSON.parse(magias).join(', '); } catch { /* aceita fichas antigas em texto */ }
    const attributes = fitAttributes(p, racas);
    const resources = calculateResources({ ...p, ...attributes }, armas);
    setEditing({ ...p, ...attributes, ...resources, magias });
    setShowForm(true);
  }

  return (
    <>
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold flex items-center gap-2"><User className="w-5 h-5 text-accent" /> Fichas</h2>
        <div className="flex gap-2">
        <button onClick={() => importInputRef.current?.click()} className="icon-btn border border-border" disabled={importing} title="Importar fichas do Obsidian" aria-label="Importar fichas do Obsidian">
          {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileUp className="w-4 h-4" />}
        </button>
        <button onClick={novoPersonagem} className="icon-btn-primary" title="Nova ficha" aria-label="Criar nova ficha">
          <Plus className="w-4 h-4" />
        </button>
        </div>
      </div>
       <input ref={importInputRef} type="file" accept=".md,.markdown,text/markdown" multiple className="hidden" onChange={importarObsidian} />

       {personagens.length > 0 && <label className="relative block"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" /><input className="input rounded-none pl-9" value={search} onChange={event => setSearch(event.target.value)} placeholder="Buscar fichas..." aria-label="Buscar fichas" /></label>}

      {showForm && editing && (
        <FormFicha editing={editing} setEditing={setEditing} racas={racas} armas={armas} salvar={salvar} cancelar={() => { setShowForm(false); setEditing(null); }} />
      )}

      {personagens.length === 0 && !showForm ? (
        <div className="card text-center py-12">
          <User className="w-10 h-10 text-muted mx-auto mb-3 opacity-50" />
           <p className="text-muted">Nenhuma ficha.</p>
        </div>
      ) : personagensFiltrados.length === 0 ? (
        <div className="card border-dashed py-12 text-center text-muted"><Search className="w-7 h-7 mx-auto mb-3" /><p>Nenhuma ficha encontrada.</p></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
          <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={event => { handlePhoto(pendingEntryRef.current, event.target.files[0]); event.target.value = ''; }} />
          {personagensFiltrados.map(p => (
            <div key={p.id} className="card">
              <div className={`relative mb-3 h-24 overflow-hidden rounded-lg border transition-colors ${dragId === p.id ? 'border-accent bg-accent/10' : p.foto ? 'border-border' : 'border-dashed border-border hover:border-accent'}`}
                onDragOver={event => { event.preventDefault(); setDragId(p.id); }}
                onDragLeave={() => setDragId(null)}
                onDrop={event => { event.preventDefault(); setDragId(null); handlePhoto(p, event.dataTransfer.files[0]); }}
                onClick={() => { pendingEntryRef.current = p; fileInputRef.current?.click(); }}
                title="Arraste e solte uma imagem aqui (ou clique para escolher)">
                {uploadingId === p.id ? <div className="flex h-full w-full items-center justify-center gap-2 text-muted text-xs"><Loader2 className="h-4 w-4 animate-spin" /> Salvando...</div>
                  : p.foto ? <>
                    <img src={p.foto} alt={p.nome} className="h-full w-full object-cover" />
                    <button className="absolute right-1.5 top-1.5 icon-btn bg-black/60" onClick={event => removePhoto(p, event)} title="Remover foto" aria-label="Remover foto"><X className="h-3.5 w-3.5" /></button>
                  </> : <div className="flex h-full w-full flex-col items-center justify-center gap-1 text-muted text-xs"><ImagePlus className="h-5 w-5" /><span>Arraste a foto</span></div>}
              </div>
              <div className="flex items-center gap-2 mb-3">
                {p.is_preset && <span className="text-xs px-1.5 py-0.5 rounded bg-accent/20 text-accent">Preset</span>}
                <h3 className="font-semibold flex-1 truncate">{p.nome}</h3>
                <button onClick={() => editar(p)} className="icon-btn" title={`Editar ${p.nome}`} aria-label={`Editar ${p.nome}`}><Pencil className="w-4 h-4" /></button>
                <button onClick={() => deletar(p.id)} className="icon-btn hover:text-accent" title={`Excluir ${p.nome}`} aria-label={`Excluir ${p.nome}`}><Trash2 className="w-4 h-4" /></button>
              </div>
              {p.nome_jogador && <p className="text-muted text-sm">Jogador: {p.nome_jogador}</p>}
              {p.historia && <p className="mt-2 line-clamp-2 text-xs text-muted">{p.historia}</p>}
              {p.aliados && <p className="mt-1 text-xs text-muted"><span className="text-accent">Aliados:</span> {p.aliados}</p>}
              {p.status && <p className="mt-1 text-xs text-muted"><span className="text-accent">Status:</span> {p.status}</p>}
              <div className="flex flex-wrap gap-2 mt-2 text-xs">
                {p.raca && <span className="px-2 py-0.5 rounded bg-surface2 text-muted">{p.raca}</span>}
                {p.arma && <span className="px-2 py-0.5 rounded bg-surface2 text-muted">{p.arma}</span>}
                <span className="px-2 py-0.5 rounded bg-surface2 text-muted">Nível {p.nivel}</span>
              </div>
              <div className="grid grid-cols-2 gap-2 mt-3 text-sm">
                <div className="flex justify-between"><span className="text-muted">HP</span><span className="font-mono">{p.hp_max}</span></div>
                <div className="flex justify-between"><span className="text-muted">MP</span><span className="font-mono">{p.mp_max}</span></div>
                <div className="flex justify-between"><span className="text-muted">INT</span><span className="font-mono">{p.inteligencia}</span></div>
                <div className="flex justify-between"><span className="text-muted">AGI</span><span className="font-mono">{p.agilidade}</span></div>
                <div className="flex justify-between"><span className="text-muted">VIG</span><span className="font-mono">{p.vigor}</span></div>
                <div className="flex justify-between"><span className="text-muted">Vida</span><span className="font-mono">{p.vida}</span></div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
    <Toast toast={toast} onClose={() => setToast(null)} />
    <ConfirmModal modal={confirmModal} onCancel={() => setConfirmModal(null)} onConfirm={async () => { const action = confirmModal?.onConfirm; setConfirmModal(null); if (action) await action(); }} />
    </>
  );
}

function calculateResources(character, armas) {
  const nivel = Number(character.nivel) || 0;
  const vida = Number(character.vida) || 0;
  const mana = Number(character.mana) || 0;
  const arma = armas.find(item => normalize(item.nome) === normalize(character.arma));
  const manaModifier = arma ? -(Number(arma.debuff_mana) || 0) : ['grimorio', 'orbe', 'luvas'].includes(normalize(character.arma)) ? -10 : 0;
  return {
    hp_max: 100 + (nivel * 10) + (vida * 10),
    mp_max: Math.max(0, 100 + (nivel * 10) + (mana * 10) + manaModifier),
  };
}

function normalize(value) {
  const normalized = String(value || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim();
  return { elfa: 'elfo', humana: 'humano' }[normalized] || normalized;
}

const ATTRIBUTE_FIELDS = ['vida', 'mana', 'inteligencia', 'agilidade', 'vigor'];

function getAttributeState(character, racas) {
  const race = racas.find(item => normalize(item.nome) === normalize(character.raca));
  const bases = {
    vida: 1 + (Number(race?.buff_vida) || 0),
    mana: 1 + (Number(race?.buff_mana) || 0),
    inteligencia: 1 + (Number(race?.buff_inteligencia) || 0),
    agilidade: 1 + (Number(race?.buff_agilidade) || 0),
    vigor: 1 + (Number(race?.buff_vigor) || 0),
  };
  const values = Object.fromEntries(ATTRIBUTE_FIELDS.map(field => [field, Number(character[field]) || 0]));
  const spent = ATTRIBUTE_FIELDS.reduce((total, field) => total + Math.max(0, values[field] - bases[field]), 0);
  return { values, bases, spent, remaining: 10 - spent };
}

function fitAttributes(character, racas) {
  const state = getAttributeState(character, racas);
  let remaining = 10;
  const values = {};
  for (const field of ATTRIBUTE_FIELDS) {
    const base = Math.min(5, state.bases[field]);
    const requested = Math.max(base, Math.min(5, state.values[field]));
    const allocated = Math.min(Math.max(0, requested - base), remaining);
    values[field] = base + allocated;
    remaining -= allocated;
  }
  return values;
}

function AttributeBar({ label, value, base, onChange }) {
  return <div>
    <div className="mb-1 flex items-center justify-between text-xs"><span className="text-muted">{label}</span><span className="font-mono">{value} / 5</span></div>
    <div className="grid grid-cols-5 gap-1">
      {Array.from({ length: 5 }, (_, index) => {
        const fixed = index < base;
        const filled = index < value;
        const nextValue = filled ? index : index + 1;
        return <button type="button" key={index} disabled={fixed} onClick={() => onChange(nextValue)} className={`h-3 rounded-sm border transition-colors ${filled ? fixed ? 'border-blue-300/40 bg-blue-300/40' : 'border-accent bg-accent' : 'border-border bg-bg hover:border-accent'} ${fixed ? 'cursor-not-allowed' : ''}`} title={fixed ? 'Base ou bônus da raça' : filled ? `Remover ponto de ${label}` : `Adicionar ponto em ${label}`} aria-label={`${label}: ${index + 1}${fixed ? ' (base)' : ''}`} />;
      })}
    </div>
  </div>;
}

function FormFicha({ editing, setEditing, racas, armas, salvar, cancelar }) {
  const resources = calculateResources(editing, armas);
  const attributes = getAttributeState(editing, racas);
  function set(campo, valor) {
    const next = { ...editing, [campo]: valor };
    if (['nivel', 'arma'].includes(campo)) Object.assign(next, calculateResources(next, armas));
    setEditing(next);
  }

  function setRace(raca) {
    const next = { ...editing, raca, ...fitAttributes({ ...editing, raca }, racas) };
    setEditing({ ...next, ...calculateResources(next, armas) });
  }

  function setAttribute(field, value) {
    const next = { ...editing, [field]: value };
    if (getAttributeState(next, racas).spent > 10) return;
    setEditing({ ...next, ...calculateResources(next, armas) });
  }

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">{editing.id ? 'Editar Ficha' : 'Nova Ficha'}</h3>
        <button onClick={cancelar} className="icon-btn" title="Fechar formulário" aria-label="Fechar formulário"><X className="w-4 h-4" /></button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
           <label className="text-xs text-muted block mb-1">Nome do personagem</label>
          <input className="input" value={editing.nome || ''} onChange={e => set('nome', e.target.value)} />
        </div>
        <div>
           <label className="text-xs text-muted block mb-1">Nome do jogador</label>
          <input className="input" value={editing.nome_jogador || ''} onChange={e => set('nome_jogador', e.target.value)} />
        </div>
        <div>
          <label className="text-xs text-muted block mb-1">Raça</label>
          <select className="input" value={editing.raca || ''} onChange={e => setRace(e.target.value)}>
            <option value="">—</option>
            {racas.map(r => <option key={r.id} value={r.nome}>{r.nome}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted block mb-1">Arma</label>
          <select className="input" value={editing.arma || ''} onChange={e => set('arma', e.target.value)}>
            <option value="">—</option>
            {armas.map(a => <option key={a.id} value={a.nome}>{a.nome}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted block mb-1">Nível</label>
          <input type="number" className="input" value={editing.nivel || 0} onChange={e => set('nivel', parseInt(e.target.value) || 0)} />
        </div>
        <div>
          <label className="text-xs text-muted block mb-1">Idade</label>
          <input className="input" value={editing.idade || ''} onChange={e => set('idade', e.target.value)} />
        </div>
      </div>

      <div>
        <label className="text-xs text-muted block mb-1">Aparência</label>
        <input className="input" value={editing.aparencia || ''} onChange={e => set('aparencia', e.target.value)} />
      </div>

      <div className="grid gap-2 md:grid-cols-2">
        <label className="text-xs text-muted">História<textarea className="input mt-1 min-h-24 resize-y" value={editing.historia || ''} onChange={e => set('historia', e.target.value)} placeholder="Origem, objetivos e acontecimentos importantes" /></label>
        <label className="text-xs text-muted">Aliados e vínculos<textarea className="input mt-1 min-h-24 resize-y" value={editing.aliados || ''} onChange={e => set('aliados', e.target.value)} placeholder="Aliados, facções e relações" /></label>
      </div>
      <label className="text-xs text-muted">Status e observações<textarea className="input mt-1 min-h-20 resize-y" value={editing.status || ''} onChange={e => set('status', e.target.value)} placeholder="Condições, títulos e informações rápidas" /></label>

      <div className="rounded-lg border border-border bg-surface2/40 p-3">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
           <div><p className="text-sm font-semibold">Atributos</p><p className="text-xs text-muted">Cada atributo começa em 1 e recebe bônus da raça. Limite: 5.</p></div>
          <p className={`text-xs font-semibold ${attributes.remaining < 0 ? 'text-accent' : 'text-muted'}`}>Pontos disponíveis: {attributes.remaining} / 10</p>
        </div>
        <div className="space-y-3">
          <AttributeBar label="Vida" value={attributes.values.vida} base={attributes.bases.vida} onChange={value => setAttribute('vida', value)} />
          <AttributeBar label="Mana" value={attributes.values.mana} base={attributes.bases.mana} onChange={value => setAttribute('mana', value)} />
          <AttributeBar label="Inteligência" value={attributes.values.inteligencia} base={attributes.bases.inteligencia} onChange={value => setAttribute('inteligencia', value)} />
          <AttributeBar label="Agilidade" value={attributes.values.agilidade} base={attributes.bases.agilidade} onChange={value => setAttribute('agilidade', value)} />
          <AttributeBar label="Vigor" value={attributes.values.vigor} base={attributes.bases.vigor} onChange={value => setAttribute('vigor', value)} />
        </div>
        {attributes.remaining < 0 && <p className="mt-3 text-xs text-accent">Remova pontos para ficar dentro do limite permitido.</p>}
      </div>

      <div>
         <label className="text-xs text-muted block mb-1">Magias (separadas por vírgula)</label>
         <input className="input" placeholder="Ex.: Esfera de Luz, Telepatia" value={editing.magias || ''} onChange={e => set('magias', e.target.value)} />
      </div>

      <div className="flex gap-2 pt-2">
        <button onClick={salvar} className="btn-accent flex-1 gap-1.5"><Save className="w-4 h-4" /> Salvar</button>
        <button onClick={cancelar} className="btn-ghost flex-1">Cancelar</button>
      </div>
    </div>
  );
}
