import { useRef, useState } from 'react';
import { AlertTriangle, Check, Download, Upload, X } from 'lucide-react';
import { api } from '../lib/api.js';

export function Toast({ toast, onClose }) {
  if (!toast) return null;
  const success = toast.type !== 'error';
  return (
    <div className="fixed right-4 top-4 z-50 flex max-w-sm items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3 shadow-2xl">
      {success ? <Check className="h-4 w-4 text-green-400" /> : <AlertTriangle className="h-4 w-4 text-accent" />}
      <span className="flex-1 text-sm text-gray-200">{toast.message}</span>
      <button className="icon-btn h-6 w-6" onClick={onClose} title="Fechar aviso" aria-label="Fechar aviso"><X className="h-3.5 w-3.5" /></button>
    </div>
  );
}

export function ConfirmModal({ modal, onCancel, onConfirm }) {
  if (!modal) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 px-4">
      <div className="card w-full max-w-sm shadow-2xl">
        <div className="mb-4 flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-accent" />
          <div>
            <h2 className="font-semibold text-white">{modal.title || 'Confirmar ação'}</h2>
            <p className="mt-1 text-sm text-muted">{modal.message}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost flex-1" onClick={onCancel}>Cancelar</button>
          <button className="btn-accent flex-1" onClick={onConfirm}>Confirmar</button>
        </div>
      </div>
    </div>
  );
}

export function ConfigModal({ open, onClose }) {
  const [backupBusy, setBackupBusy] = useState(false);
  const [error, setError] = useState('');
  const importInputRef = useRef(null);

  if (!open) return null;

  async function exportData() {
    setBackupBusy(true);
    setError('');
    try {
      const blob = await api.exportBackup();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `rpg-system-gg-backup-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBackupBusy(false);
    }
  }

  async function importData(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!window.confirm('Importar este backup substituira os dados atuais. Continuar?')) return;
    setBackupBusy(true);
    setError('');
    try {
      await api.importBackup(JSON.parse(await file.text()));
      window.location.reload();
    } catch (requestError) {
      setError(requestError instanceof SyntaxError ? 'O arquivo selecionado não é um JSON válido.' : requestError.message);
      setBackupBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 px-4" role="presentation">
      <div className="card w-full max-w-lg space-y-5 border-accent/30 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="config-title">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h2 id="config-title" className="font-semibold text-white">Configuração</h2>
            <p className="mt-1 text-sm text-muted">Use fichas nativas ou importe arquivos do Obsidian.</p>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} title="Fechar configuração" aria-label="Fechar configuração"><X className="h-4 w-4" /></button>
        </div>

        <div className="flex items-center justify-between border-t border-border pt-4">
           <div><p className="text-sm font-medium">Dados do sistema</p><p className="mt-1 text-xs text-muted">Fichas, combates, fotos e presets.</p></div>
          <div className="flex gap-2">
            <button type="button" className="icon-btn border border-border" onClick={exportData} disabled={backupBusy} title="Exportar backup" aria-label="Exportar backup"><Download className="h-4 w-4" /></button>
            <button type="button" className="icon-btn border border-border" onClick={() => importInputRef.current?.click()} disabled={backupBusy} title="Importar backup" aria-label="Importar backup"><Upload className="h-4 w-4" /></button>
            <input ref={importInputRef} type="file" accept="application/json,.json" className="hidden" onChange={importData} />
          </div>
        </div>

        {error && <p className="rounded-lg border border-red-400/30 bg-red-400/10 px-3 py-2 text-sm text-red-300">{error}</p>}

        <div className="flex justify-end"><button type="button" className="btn-ghost" onClick={onClose}>Fechar</button></div>
      </div>
    </div>
  );
}
