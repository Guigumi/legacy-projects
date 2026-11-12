import { useState } from 'react';
import { api } from '../lib/api.js';
import { Lock, ArrowRight } from 'lucide-react';

export default function Login({ onLogin }) {
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setErro('');
    try {
      await api.login(senha);
      onLogin();
    } catch (error) {
      setErro(error?.status === 401 ? 'Senha incorreta.' : 'Servidor indisponível.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="card w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-accent flex items-center justify-center mb-4">
            <Lock className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-xl font-bold text-white">RPG System GG</h1>
          <p className="text-muted text-sm mt-1">Painel do mestre</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <input
              type="password"
              className="input"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              placeholder="Senha"
              autoFocus
            />
          </div>
          {erro && <p className="text-accent text-sm text-center">{erro}</p>}
          <button type="submit" className="btn-accent w-full" disabled={loading || !senha}>
            {loading ? 'Entrando' : 'Entrar'}
            {!loading && <ArrowRight className="w-4 h-4" />}
          </button>
        </form>
      </div>
    </div>
  );
}
