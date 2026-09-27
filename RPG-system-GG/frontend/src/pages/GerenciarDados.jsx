import { useRef, useState } from 'react';
import { Database, Download, FileUp, Upload } from 'lucide-react';
import { api } from '../lib/api.js';

export default function GerenciarDados() {
  const backupRef = useRef(null);
  const fichaRef = useRef(null);
  const inimigoRef = useRef(null);
  const [message, setMessage] = useState(null);

  function flash(text, type = 'success') {
    setMessage({ text, type });
    window.setTimeout(() => setMessage(null), 2600);
  }

  async function exportar() {
    try {
      const blob = await api.exportBackup();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `rpg-system-gg-backup-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
      flash('Backup exportado.');
    } catch (error) { flash(error.message, 'error'); }
  }

  async function importarBackup(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || !window.confirm('Importar este backup substituirá os dados atuais. Continuar?')) return;
    try { await api.importBackup(JSON.parse(await file.text())); window.location.reload(); } catch (error) { flash(error instanceof SyntaxError ? 'O arquivo não é um JSON válido.' : error.message, 'error'); }
  }

  async function importarMarkdown(event, tipo) {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    if (!files.length) return;
    try {
      const payload = await Promise.all(files.map(async file => ({ name: file.name, content: await file.text() })));
      const result = tipo === 'fichas' ? await api.importObsidianPersonagens(payload) : await api.importObsidianBestiario(payload);
      flash(`${result.importados} registro${result.importados === 1 ? '' : 's'} importado${result.importados === 1 ? '' : 's'}.`);
    } catch (error) { flash(error.message, 'error'); }
  }

  return <div className="space-y-6"><header><h2 className="flex items-center gap-2 text-lg font-semibold"><Database className="h-5 w-5 text-accent" /> Dados</h2><p className="mt-1 text-sm text-muted">Faça backups e importe arquivos do Obsidian.</p></header>{message && <p className={`rounded-lg border px-3 py-2 text-sm ${message.type === 'error' ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-surface text-muted'}`}>{message.text}</p>}<div className="grid gap-4 md:grid-cols-2"><section className="card space-y-3"><h3 className="font-semibold">Backup</h3><p className="text-sm text-muted">Fichas, inimigos, roteiros, sessões, fotos e configurações.</p><div className="flex gap-2"><button className="btn-accent flex-1" onClick={exportar}><Download className="h-4 w-4" /> Exportar</button><button className="btn-ghost flex-1" onClick={() => backupRef.current?.click()}><Upload className="h-4 w-4" /> Importar</button><input ref={backupRef} type="file" accept=".json,application/json" className="hidden" onChange={importarBackup} /></div></section><section className="card space-y-3"><h3 className="font-semibold">Importar do Obsidian</h3><p className="text-sm text-muted">Importe fichas e inimigos em Markdown.</p><div className="flex flex-wrap gap-2"><button className="btn-ghost btn-sm" onClick={() => fichaRef.current?.click()}><FileUp className="h-3.5 w-3.5" /> Fichas .md</button><button className="btn-ghost btn-sm" onClick={() => inimigoRef.current?.click()}><FileUp className="h-3.5 w-3.5" /> Inimigos .md</button><input ref={fichaRef} type="file" accept=".md,.markdown" multiple className="hidden" onChange={event => importarMarkdown(event, 'fichas')} /><input ref={inimigoRef} type="file" accept=".md,.markdown" multiple className="hidden" onChange={event => importarMarkdown(event, 'inimigos')} /></div></section></div></div>;
}
