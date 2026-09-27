import { useState, useEffect } from 'react';
import { api } from './lib/api.js';
import Login from './pages/Login.jsx';
import Dashboard from './pages/Dashboard.jsx';
import PlayerView from './pages/PlayerView.jsx';

export default function App() {
  const [autenticado, setAutenticado] = useState(null);
  const playerMode = window.location.pathname === '/jogadores';

  useEffect(() => {
    if (playerMode) return;
    api.status()
      .then((s) => setAutenticado(s.autenticado))
      .catch(() => setAutenticado(false));
  }, [playerMode]);

  if (playerMode) return <PlayerView />;

  if (autenticado === null) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400 animate-pulse">Carregando</p>
      </div>
    );
  }

  if (!autenticado) {
    return <Login onLogin={() => setAutenticado(true)} />;
  }

  return (
    <Dashboard
      onLogout={async () => {
        try { await api.logout(); } catch {}
        setAutenticado(false);
      }}
    />
  );
}
