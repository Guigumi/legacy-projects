import { useEffect, useState } from 'react';
import { BookOpen, Package, Pencil, Plus, Save, Search, Trash2, UserPlus, Wand2, X } from 'lucide-react';
import { api } from '../lib/api.js';

const ACTIONS = [
  { value: 'cura_hp', label: 'Cura HP' },
  { value: 'dano_hp', label: 'Dano HP' },
  { value: 'restaura_mp', label: 'Restaura MP' },
  { value: 'drena_mp', label: 'Drena MP' },
  { value: 'modifica_iniciativa', label: 'Modifica iniciativa' },
];

const TARGETS = [
  { value: 'alvo', label: 'Alvo selecionado' },
  { value: 'conjurador', label: 'Quem usou' },
];

const MAGIC_CATEGORIES = [
  { value: 'básica', label: 'Básica' },
  { value: 'atributo', label: 'Atributo' },
  { value: 'simples', label: 'Simples' },
  { value: 'complexa', label: 'Complexa' },
];

const MAGIC_TYPES = [
  { value: 'básica', label: 'Básica' },
  { value: 'atributo', label: 'Atributo' },
  { value: 'simples', label: 'Simples' },
  { value: 'complexa', label: 'Complexa' },
];

const ITEM_TYPES = [
  { value: 'poção', label: 'Poção' },
  { value: 'arma', label: 'Arma' },
  { value: 'equipamento', label: 'Equipamento' },
  { value: 'consumível', label: 'Consumível' },
  { value: 'outro', label: 'Outro' },
];

const blankEffect = () => ({ acao: 'cura_hp', alvo: 'alvo', valor: '10' });

export default function Compendium({ kind }) {
  const isMagic = kind === 'magias';
  const [entries, setEntries] = useState([]);
  const [characters, setCharacters] = useState([]);
  const [editing, setEditing] = useState(null);
  const [modal, setModal] = useState(null);
  const [selectedCharacterId, setSelectedCharacterId] = useState('');
  const [quantity, setQuantity] = useState(1);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState(null);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');

  async function load() {
    try {
      setEntries(isMagic ? await api.getMagias() : await api.getItens());
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  }

  useEffect(() => { load(); }, [kind]);

  function startNew() {
    setEditing(isMagic
      ? { nome: '', custo: 0, tipo: 'simples', categoria: 'simples', descricao: '', observacao: '', efeitos: [] }
      : { nome: '', tipo: 'poção', efeito: '', valor: '', efeitos: [] });
  }

  function edit(entry) {
    setEditing({ ...entry, efeitos: parseEffects(entry.efeitos) });
  }

  async function save() {
    if (!editing?.nome?.trim()) {
      setMessage({ type: 'error', text: `Informe o nome da ${isMagic ? 'magia' : 'item'}.` });
      return;
    }
    try {
      const payload = { ...editing, nome: editing.nome.trim(), efeitos: editing.efeitos || [] };
      if (editing.id) await (isMagic ? api.updateMagia(editing.id, payload) : api.updateItem(editing.id, payload));
      else await (isMagic ? api.createMagia(payload) : api.createItem(payload));
      setEditing(null);
      await load();
      setMessage({ type: 'success', text: `${isMagic ? 'Magia' : 'Item'} salvo.` });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  }

  function askDelete(entry) {
    setModal({ type: 'delete', entry });
  }

  async function remove() {
    if (!modal?.entry || working) return;
    setWorking(true);
    try {
      const entry = modal.entry;
      await (isMagic ? api.deleteMagia(entry.id) : api.deleteItem(entry.id));
      setModal(null);
      await load();
      setMessage({ type: 'success', text: `${isMagic ? 'Magia' : 'Item'} excluído.` });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setWorking(false);
    }
  }

  async function openCharacterAction(type, entry) {
    try {
      setCharacters(await api.getPersonagens());
      setSelectedCharacterId('');
      setQuantity(1);
      setModal({ type, entry });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  }

  async function linkMagic() {
    const character = characters.find(item => item.id === Number(selectedCharacterId));
    if (!character || !modal?.entry || working) return;
    const names = parseMagicNames(character.magias);
    if (names.some(name => normalizeName(name) === normalizeName(modal.entry.nome))) {
      setMessage({ type: 'error', text: `${character.nome} já possui essa magia vinculada.` });
      return;
    }
    setWorking(true);
    try {
      await api.updatePersonagem(character.id, { magias: JSON.stringify([...names, modal.entry.nome]) });
      setModal(null);
      setMessage({ type: 'success', text: `${modal.entry.nome} vinculada a ${character.nome}.` });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setWorking(false);
    }
  }

  async function giveItem() {
    const character = characters.find(item => item.id === Number(selectedCharacterId));
    const amount = Math.max(1, Number.parseInt(quantity, 10) || 0);
    if (!character || !modal?.entry || !amount || working) return;
    setWorking(true);
    try {
      await api.updatePersonagem(character.id, { inventario: addInventory(character.inventario, modal.entry.nome, amount) });
      setModal(null);
      setMessage({ type: 'success', text: `${amount} ${modal.entry.nome} dado${amount === 1 ? '' : 's'} a ${character.nome}.` });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setWorking(false);
    }
  }

  const Icon = isMagic ? Wand2 : Package;
  const title = isMagic ? 'Magias' : 'Itens';
  const categories = [...new Set(entries.map(entry => isMagic ? entry.categoria || entry.tipo : entry.tipo).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, 'pt-BR'));
  const normalizedSearch = normalizeName(search);
  const filteredEntries = entries.filter(entry => {
    const effects = parseEffects(entry.efeitos).map(effect => `${effect.acao} ${effect.valor}`).join(' ');
    const content = normalizeName([
      entry.nome,
      entry.descricao,
      entry.observacao,
      entry.categoria,
      entry.tipo,
      entry.efeito,
      entry.valor,
      effects,
    ].filter(Boolean).join(' '));
    const entryCategory = isMagic ? entry.categoria || entry.tipo : entry.tipo;
    return (!normalizedSearch || content.includes(normalizedSearch)) && (!category || entryCategory === category);
  });

  return <div className="space-y-6">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold"><Icon className="h-5 w-5 text-accent" /> {title}</h2>
        <p className="mt-1 text-sm text-muted">Cadastre, organize e prepare entradas para uso durante o combate.</p>
      </div>
      <button className="icon-btn-primary rounded-none" onClick={startNew} title={`Nova ${isMagic ? 'magia' : 'item'}`} aria-label={`Criar ${isMagic ? 'magia' : 'item'}`}><Plus className="h-4 w-4" /></button>
    </header>

    {message && <p className={`rounded-none border px-3 py-2 text-sm ${message.type === 'error' ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-surface text-muted'}`}>{message.text}</p>}
    {editing && <EntryForm value={editing} setValue={setEditing} isMagic={isMagic} onSave={save} onCancel={() => setEditing(null)} />}

    {entries.length > 0 && <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_12rem]">
      <label className="relative block"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" /><input className="input rounded-none pl-9" value={search} onChange={event => setSearch(event.target.value)} placeholder={`Buscar ${isMagic ? 'magias' : 'itens'}...`} aria-label={`Buscar ${isMagic ? 'magias' : 'itens'}`} /></label>
      <select className="input rounded-none" value={category} onChange={event => setCategory(event.target.value)} aria-label="Filtrar por categoria"><option value="">Todas as categorias</option>{categories.map(value => <option key={value} value={value}>{displayValue(value)}</option>)}</select>
    </div>}

    {entries.length === 0 ? <section className="card rounded-none border-dashed py-16 text-center text-muted"><BookOpen className="mx-auto mb-3 h-8 w-8" /><p>Nenhum {isMagic ? 'magia' : 'item'} cadastrado.</p></section>
      : filteredEntries.length === 0 ? <section className="card rounded-none border-dashed py-12 text-center text-muted"><Search className="mx-auto mb-3 h-7 w-7" /><p>Nenhum resultado encontrado.</p></section>
        : <div className="overflow-hidden border border-border bg-surface/75">{filteredEntries.map(entry => <EntryRow key={entry.id} entry={entry} isMagic={isMagic} onEdit={() => edit(entry)} onDelete={() => askDelete(entry)} onLink={() => openCharacterAction('link', entry)} onGive={() => openCharacterAction('give', entry)} />)}</div>}

    {modal?.type === 'delete' && <ActionModal title={`Excluir ${isMagic ? 'magia' : 'item'}`} onClose={() => setModal(null)}>
      <p className="text-sm text-muted">Excluir <strong className="text-foreground">{modal.entry.nome}</strong> permanentemente?</p>
      <p className="text-xs text-muted">Essa ação não pode ser desfeita.</p>
      <ModalActions onCancel={() => setModal(null)} onConfirm={remove} confirmLabel={working ? 'Excluindo...' : 'Continuar'} disabled={working} />
    </ActionModal>}
    {modal?.type === 'link' && <ActionModal title={`Vincular ${modal.entry.nome}`} onClose={() => setModal(null)}>
      <p className="text-sm text-muted">Escolha o personagem que receberá esta magia.</p>
      <CharacterSelect characters={characters} value={selectedCharacterId} onChange={setSelectedCharacterId} />
      <ModalActions onCancel={() => setModal(null)} onConfirm={linkMagic} confirmLabel={working ? 'Vinculando...' : 'Vincular'} disabled={!selectedCharacterId || working} />
    </ActionModal>}
    {modal?.type === 'give' && <ActionModal title={`Dar ${modal.entry.nome}`} onClose={() => setModal(null)}>
      <p className="text-sm text-muted">Escolha o personagem e a quantidade.</p>
      <CharacterSelect characters={characters} value={selectedCharacterId} onChange={setSelectedCharacterId} />
      <label className="block text-xs text-muted">Quantidade<input className="input mt-1 rounded-none" type="number" min="1" step="1" value={quantity} onChange={event => setQuantity(event.target.value)} /></label>
      <ModalActions onCancel={() => setModal(null)} onConfirm={giveItem} confirmLabel={working ? 'Entregando...' : 'Dar item'} disabled={!selectedCharacterId || working} />
    </ActionModal>}
  </div>;
}

function EntryRow({ entry, isMagic, onEdit, onDelete, onLink, onGive }) {
  const effects = parseEffects(entry.efeitos);
  const category = isMagic ? entry.categoria || entry.tipo : entry.tipo || 'item';
  return <article className="group flex flex-col gap-3 border-b border-border bg-surface/75 px-3 py-3 transition-colors last:border-b-0 hover:bg-surface2 sm:flex-row sm:items-center sm:gap-4">
    <div className="min-w-0 flex-1">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1"><h3 className="font-semibold">{entry.nome}</h3><span className="text-xs text-muted">{displayValue(category)}{isMagic && ` · ${entry.custo || 0} MP`}</span></div>
      <p className="mt-1 truncate text-sm text-muted">{isMagic ? entry.descricao || 'Sem descrição.' : entry.efeito || entry.valor || 'Sem descrição.'}</p>
      {effects.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{effects.map((effect, index) => <span key={`${entry.id}-${index}`} className="rounded-none bg-accent/10 px-2 py-1 text-[10px] text-accent">{actionLabel(effect.acao)} · {effect.valor}</span>)}</div>}
    </div>
    <div className="flex shrink-0 flex-wrap gap-1 border-t border-border pt-2 sm:border-t-0 sm:pt-0"><button className="btn-ghost btn-sm rounded-none" onClick={onEdit} title="Editar"><Pencil className="h-3.5 w-3.5" /> Editar</button>{isMagic ? <button className="btn-ghost btn-sm rounded-none" onClick={onLink} title="Vincular a personagem"><UserPlus className="h-3.5 w-3.5" /> Vincular</button> : <button className="btn-ghost btn-sm rounded-none" onClick={onGive} title="Dar item a personagem"><Package className="h-3.5 w-3.5" /> Dar</button>}<button className="btn-ghost btn-sm rounded-none text-accent" onClick={onDelete} title="Excluir"><Trash2 className="h-3.5 w-3.5" /> Excluir</button></div>
  </article>;
}

function EntryForm({ value, setValue, isMagic, onSave, onCancel }) {
  const set = (field, next) => setValue({ ...value, [field]: next });
  const options = withCurrentOption(isMagic ? MAGIC_TYPES : ITEM_TYPES, value.tipo);
  const categoryOptions = withCurrentOption(MAGIC_CATEGORIES, value.categoria);
  const effects = value.efeitos || [];

  function updateEffect(index, field, next) {
    set('efeitos', effects.map((effect, effectIndex) => effectIndex === index ? { ...effect, [field]: next } : effect));
  }

  return <section className="card rounded-none space-y-5 border-accent/30">
    <div className="flex items-start justify-between gap-3 border-b border-border pb-3"><div><p className="text-[10px] uppercase tracking-[0.2em] text-accent">Configuração</p><h3 className="mt-1 font-semibold">{value.id ? 'Editar' : 'Nova'} {isMagic ? 'magia' : 'item'}</h3></div><button className="icon-btn rounded-none" onClick={onCancel} title="Fechar" aria-label="Fechar"><X className="h-4 w-4" /></button></div>

    <section className="space-y-3"><SectionTitle title="Identificação" description="Dados usados para encontrar e organizar a entrada." /><div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_12rem_12rem]">
      <Field label="Nome" value={value.nome} placeholder={isMagic ? 'Ex.: Toque Vital' : 'Ex.: Poção de cura'} onChange={next => set('nome', next)} />
      {isMagic ? <><Field label="Custo de MP" type="number" min="0" value={value.custo} onChange={next => set('custo', Number(next) || 0)} /><SelectField label="Categoria" value={value.categoria} options={categoryOptions} onChange={next => set('categoria', next)} /></> : <SelectField label="Tipo" value={value.tipo} options={options} onChange={next => set('tipo', next)} />}
    </div>{isMagic && <div className="grid gap-3 sm:grid-cols-2"><SelectField label="Tipo de magia" value={value.tipo} options={options} onChange={next => set('tipo', next)} /><Field label="Observação curta" value={value.observacao} placeholder="Requisito, alcance ou nota" onChange={next => set('observacao', next)} /></div>}{!isMagic && <div className="grid gap-3 sm:grid-cols-2"><Field label="Efeito narrativo" value={value.efeito} placeholder="Ex.: Cura" onChange={next => set('efeito', next)} /><Field label="Valor exibido" value={value.valor} placeholder="Ex.: +25 HP" onChange={next => set('valor', next)} /></div>}</section>

    {isMagic && <section className="space-y-3"><SectionTitle title="Descrição" description="Texto que aparece no compêndio e ajuda o Mestre a identificar o uso." /><textarea className="input min-h-24 resize-y rounded-none" placeholder="Descreva o que esta magia faz." value={value.descricao || ''} onChange={event => set('descricao', event.target.value)} /></section>}

    <EffectEditor isMagic={isMagic} effects={effects} onAdd={() => set('efeitos', [...effects, blankEffect()])} onUpdate={updateEffect} onRemove={index => set('efeitos', effects.filter((_, effectIndex) => effectIndex !== index))} />
    <div className="flex gap-2 border-t border-border pt-3"><button className="btn-accent flex-1 rounded-none" onClick={onSave}><Save className="h-4 w-4" /> Salvar {isMagic ? 'magia' : 'item'}</button><button className="btn-ghost flex-1 rounded-none" onClick={onCancel}>Cancelar</button></div>
  </section>;
}

function EffectEditor({ isMagic, effects, onAdd, onUpdate, onRemove }) {
  return <section className="space-y-3 border border-border bg-surface2/40 p-3"><div className="flex flex-wrap items-start justify-between gap-3"><SectionTitle title="Efeitos automáticos" description={isMagic ? 'Opcional. Use {half} para metade do HP ou MP máximo.' : 'Opcional. Itens aceitam valores fixos ou dados.'} /><button className="btn-ghost btn-sm rounded-none" onClick={onAdd}><Plus className="h-3.5 w-3.5" /> Adicionar efeito</button></div>{effects.length === 0 ? <p className="border border-dashed border-border px-3 py-4 text-xs text-muted">Nenhum efeito mecânico configurado. A entrada continuará apenas narrativa.</p> : <div className="space-y-2">{effects.map((effect, index) => <div className="grid gap-2 border border-border bg-surface/60 p-2 sm:grid-cols-[1.2fr_1.1fr_minmax(8rem,1fr)_auto]" key={index}><SelectField label="Ação" compact value={effect.acao} options={ACTIONS} onChange={next => onUpdate(index, 'acao', next)} /><SelectField label="Alvo" compact value={effect.alvo} options={TARGETS} onChange={next => onUpdate(index, 'alvo', next)} /><Field label="Valor" compact value={effect.valor} placeholder={isMagic ? '20, 2d6+3 ou {half}' : '20 ou 2d6+3'} onChange={next => onUpdate(index, 'valor', next)} /><button className="icon-btn rounded-none self-end text-accent" onClick={() => onRemove(index)} title="Remover efeito" aria-label="Remover efeito"><Trash2 className="h-4 w-4" /></button></div>)}</div>}</section>;
}

function SectionTitle({ title, description }) {
  return <div><h4 className="text-sm font-semibold">{title}</h4>{description && <p className="mt-1 text-xs text-muted">{description}</p>}</div>;
}

function Field({ label, value, onChange, placeholder = '', type = 'text', min, compact = false }) {
  return <label className={`block text-xs text-muted ${compact ? 'min-w-0' : ''}`}>{label}<input className={`input mt-1 rounded-none ${compact ? 'px-2 py-1.5' : ''}`} type={type} min={min} value={value ?? ''} placeholder={placeholder} onChange={event => onChange(event.target.value)} /></label>;
}

function SelectField({ label, value, options, onChange, compact = false }) {
  return <label className="block text-xs text-muted">{label}<select className={`input mt-1 rounded-none ${compact ? 'px-2 py-1.5' : ''}`} value={value ?? ''} onChange={event => onChange(event.target.value)}>{options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>;
}

function CharacterSelect({ characters, value, onChange }) {
  return <select autoFocus className="input rounded-none" value={value} onChange={event => onChange(event.target.value)}><option value="">Selecionar personagem</option>{characters.map(character => <option key={character.id} value={character.id}>{character.nome}</option>)}</select>;
}

function ActionModal({ title, onClose, children }) {
  return <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 px-4" onClick={onClose}><div className="card w-full max-w-md space-y-3 rounded-none shadow-2xl" onClick={event => event.stopPropagation()}><div className="flex items-center justify-between"><h3 className="font-semibold">{title}</h3><button onClick={onClose} className="icon-btn rounded-none" title="Fechar" aria-label="Fechar"><X className="h-4 w-4" /></button></div>{children}</div></div>;
}

function ModalActions({ onCancel, onConfirm, confirmLabel, disabled = false }) {
  return <div className="flex gap-2 border-t border-border pt-3"><button className="btn-ghost flex-1 rounded-none" onClick={onCancel}>Cancelar</button><button className="btn-accent flex-1 rounded-none" onClick={onConfirm} disabled={disabled}>{confirmLabel}</button></div>;
}

function parseEffects(value) {
  if (Array.isArray(value)) return value;
  try { const parsed = JSON.parse(value || '[]'); return Array.isArray(parsed) ? parsed : []; } catch { return []; }
}

function parseMagicNames(value) {
  if (Array.isArray(value)) return value.map(String).filter(Boolean);
  if (typeof value !== 'string' || !value.trim()) return [];
  try { const parsed = JSON.parse(value); return Array.isArray(parsed) ? parsed.map(String).filter(Boolean) : []; }
  catch { return value.split(',').map(name => name.trim()).filter(Boolean); }
}

function normalizeName(value) {
  return String(value || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').trim().toLocaleLowerCase('pt-BR');
}

function addInventory(value, itemName, amount) {
  const current = String(value || '').trim();
  const addition = `${itemName}${amount > 1 ? ` x${amount}` : ''}`;
  return current ? `${current}\n${addition}` : addition;
}

function displayValue(value) {
  const option = [...MAGIC_CATEGORIES, ...ITEM_TYPES].find(item => item.value === value);
  return option?.label || String(value || '').replace(/\b\w/g, character => character.toUpperCase());
}

function withCurrentOption(options, value) {
  if (!value || options.some(option => option.value === value)) return options;
  return [...options, { value, label: displayValue(value) }];
}

function actionLabel(value) {
  return ACTIONS.find(action => action.value === value)?.label || value;
}
