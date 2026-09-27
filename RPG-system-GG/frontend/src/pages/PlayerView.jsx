import { useEffect, useRef, useState } from 'react';
import { Activity, Droplet, Heart, Music2, Sparkles, Swords, User, Volume2, VolumeX, Wifi, WifiOff } from 'lucide-react';
import { api } from '../lib/api.js';
import { musicEmbed } from '../lib/music.js';

export default function PlayerView() {
  const [state, setState] = useState({ combate: null, participantes: [], efeitos: [], fila: [], logs: [], rolagens: [], transmissao: {} });
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let active = true;
    let socket;
    let reconnectTimer;

    api.getPlayerState().then(next => active && setState(next)).catch(() => {});
    const connect = () => {
      if (!active) return;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      socket = new WebSocket(`${protocol}//${window.location.host}/ws/player`);
      socket.onopen = () => setConnected(true);
      socket.onmessage = event => {
        try {
          const next = JSON.parse(event.data);
           if (active) setState(previous => ({ ...previous, ...next, participantes: next.participantes || [], efeitos: next.efeitos || [], fila: next.fila || [], logs: next.logs || [], rolagens: next.rolagens || [], transmissao: next.transmissao || previous.transmissao || {} }));
        } catch { /* ignora mensagens inválidas sem interromper a visão dos jogadores */ }
      };
      socket.onclose = () => {
        setConnected(false);
        reconnectTimer = window.setTimeout(connect, 2000);
      };
      socket.onerror = () => setConnected(false);
    };
    connect();
    return () => {
      active = false;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  const combate = state.combate;
  const turno = state.participantes.find(participante => participante.id === combate?.turno_atual_id);
  const efeitoAtual = state.efeitos.find(efeito => efeito.id === combate?.turno_atual_efeito_id);

  return (
    <main className="min-h-screen bg-bg px-4 py-6 text-gray-100 sm:px-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="flex items-center justify-between border-b border-border pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-bg"><Swords className="h-5 w-5" /></div>
            <div><h1 className="text-lg font-semibold">RPG System GG</h1><p className="text-xs text-muted">Tela dos jogadores</p></div>
          </div>
          <div className={`flex items-center gap-2 text-xs ${connected ? 'text-accent' : 'text-muted'}`}>
            {connected ? <Wifi className="h-4 w-4" /> : <WifiOff className="h-4 w-4" />}
            {connected ? 'Ao vivo' : 'Reconectando'}
          </div>
        </header>

         <PublicScene transmissao={state.transmissao} />
           {!combate ? <><section className="card py-16 text-center"><Activity className="mx-auto mb-4 h-10 w-10 text-muted" /><h2 className="text-lg font-semibold">Aguardando sessão</h2><p className="mt-2 text-sm text-muted">O mestre ainda não iniciou uma sessão.</p></section>{Boolean(state.transmissao.mostrar_logs) && <RollFeed rolagens={state.rolagens} />}</> : <>
          <section className="card flex flex-wrap items-center justify-between gap-4 border-accent/30">
            <div><p className="text-xs uppercase tracking-widest text-muted">Combate atual</p><h2 className="mt-1 text-2xl font-semibold">{combate.nome}</h2></div>
             <div className="text-right"><p className="text-xs uppercase tracking-widest text-muted">Rodada {combate.rodada}</p><p className="mt-1 text-lg font-semibold text-accent">{efeitoAtual ? `Vez de ${efeitoAtual.nome}` : turno ? `Vez de ${turno.nome}` : 'Aguardando turno'}</p></div>
           </section>

            <section className={`grid gap-4 ${state.transmissao.mostrar_fila ? 'lg:grid-cols-[minmax(260px,21rem)_minmax(0,1fr)]' : ''} lg:items-start`}>
              {Boolean(state.transmissao.mostrar_fila) && <PlayerQueue fila={state.fila} />}
              <div className="space-y-2">{state.participantes.map(participante => <PlayerParticipant key={participante.id} participante={participante} efeitos={state.efeitos.filter(efeito => efeito.alvo_id === participante.id || efeito.conjurador_id === participante.id)} current={combate.turno_atual_tipo !== 'evento' && participante.id === combate.turno_atual_id} />)}</div>
            </section>

           {Boolean(state.transmissao.mostrar_logs) && <section className="grid gap-4 lg:grid-cols-2"><RollFeed rolagens={state.rolagens} /><section className="card"><h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-muted"><Activity className="h-4 w-4" /> Eventos recentes</h2>{state.logs.length === 0 ? <p className="text-sm text-muted">Nenhum evento registrado.</p> : <div className="space-y-2">{state.logs.map((log, index) => <p key={`${log.criado_em}-${index}`} className="border-b border-border/60 pb-2 text-sm text-muted"><span className="mr-2 font-mono text-xs text-accent">R{log.rodada}</span>{log.detalhes || log.evento}</p>)}</div>}</section></section>}
        </>}
      </div>
    </main>
  );
}

function PublicScene({ transmissao = {} }) {
  const [volume, setVolume] = useState(Number(transmissao.volume) || 0.7);
  const [muted, setMuted] = useState(false);
  const audioRef = useRef(null);
  const url = transmissao.musica_url || '';
  useEffect(() => { setVolume(Number(transmissao.volume) || 0.7); }, [transmissao.volume, url]);
  useEffect(() => { if (audioRef.current) { audioRef.current.volume = muted ? 0 : volume; } }, [volume, muted]);
  if (!url && !transmissao.imagem_url) return null;
  const embed = musicEmbed(url);
  return <section className="space-y-3">{transmissao.imagem_url && <img src={transmissao.imagem_url} alt="Cenário da sessão" className="max-h-[28rem] w-full rounded-xl border border-border object-cover" />}{url && <div className="card flex flex-wrap items-center gap-3"><Music2 className="h-4 w-4 text-accent" /><span className="min-w-0 flex-1 truncate text-sm">{transmissao.musica_titulo || 'Trilha da sessão'}</span>{embed ? <iframe title="Música da sessão" src={embed} className="h-10 w-64 rounded" allow="autoplay; encrypted-media" /> : <audio key={url} ref={audioRef} src={url} controls autoPlay className="h-9 max-w-full" />}{!embed && <><button className="icon-btn" onClick={() => setMuted(previous => !previous)} title={muted ? 'Ativar volume' : 'Silenciar'} aria-label={muted ? 'Ativar volume' : 'Silenciar'}>{muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}</button><input className="w-24 accent-accent" type="range" min="0" max="1" step="0.05" value={muted ? 0 : volume} onChange={event => { setMuted(false); setVolume(Number(event.target.value)); }} aria-label="Volume da música" /></>}</div>}</section>;
}

function RollFeed({ rolagens = [] }) {
  return <section className="card"><h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-muted"><Swords className="h-4 w-4" /> Rolagens compartilhadas</h2>{rolagens.length === 0 ? <p className="text-sm text-muted">Nenhuma rolagem ainda.</p> : <div className="space-y-2">{rolagens.slice().reverse().map(roll => <div key={roll.id} className="flex items-center gap-3 border-b border-border/60 pb-2"><span className="text-2xl font-bold text-accent">{roll.resultado}</span><div><p className="text-sm font-medium">{roll.autor} <span className="font-mono text-xs text-muted">{roll.expressao}</span></p><p className="text-xs text-muted">{roll.detalhes}</p></div></div>)}</div>}</section>;
}

function PlayerParticipant({ participante, efeitos = [], current }) {
  const isPlayer = participante.tipo === 'jogador';
  const hp = Math.max(0, Math.min(100, (participante.hp_atual / Math.max(1, participante.hp_max)) * 100));
  const mp = Math.max(0, Math.min(100, (participante.mp_atual / Math.max(1, participante.mp_max)) * 100));
  return <article className={`rounded-lg border bg-surface px-3 py-3 transition-all duration-300 ${current ? 'border-accent bg-accent/5 shadow-[0_0_24px_rgba(49,235,49,0.12)]' : 'border-border'} ${participante.hp_atual <= 0 ? 'opacity-50' : ''}`}>
     <div className="flex items-center gap-2">
      {participante.foto ? <img src={participante.foto} alt="" className="h-8 w-8 rounded-full object-cover" /> : isPlayer ? <User className="h-5 w-5 text-muted" /> : <Swords className="h-5 w-5 text-accent" />}
      <h3 className="flex-1 truncate font-semibold">{participante.nome}</h3><span className="font-mono text-xs text-muted">Init {participante.iniciativa}</span>
     </div>
     {efeitos.length > 0 && <div className="mb-3 flex flex-wrap gap-1">{efeitos.map(efeito => <span key={efeito.id} className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent">{efeito.nome} · {efeito.duracao}</span>)}</div>}
     <div className="mt-3 grid gap-3 sm:grid-cols-2"><Resource icon={Heart} label="HP" value={`${participante.hp_atual} / ${participante.hp_max}`} percent={hp} />{isPlayer && <Resource icon={Droplet} label="MP" value={`${participante.mp_atual} / ${participante.mp_max}`} percent={mp} blue />}</div>
   </article>;
}

function PlayerQueue({ fila = [] }) {
  return <section className="card p-0 lg:sticky lg:top-6"><div className="border-b border-border bg-surface2/60 px-4 py-3"><p className="text-xs font-semibold uppercase tracking-widest text-muted">Fila de ação</p></div><div className="max-h-[min(58vh,34rem)] space-y-1 overflow-y-auto p-2">{fila.length === 0 ? <p className="px-2 py-5 text-center text-sm text-muted">A fila ainda está vazia.</p> : fila.map((item, index) => { const evento = item.tipo === 'evento'; const label = evento ? item.efeito?.nome : item.participante?.nome; return <div key={`${item.token}-${index}`} className={`flex items-center gap-2 rounded-md border px-2.5 py-2 ${index === 0 ? 'border-accent bg-accent/10 text-accent' : 'border-transparent text-muted'}`}><span className="w-5 text-center font-mono text-[10px]">{index === 0 ? '>' : index + 1}</span>{evento ? <Sparkles className="h-4 w-4 shrink-0 text-violet-300" /> : item.participante?.foto ? <img src={item.participante.foto} alt="" className="h-6 w-6 rounded-full object-cover" /> : <span className="flex h-6 w-6 items-center justify-center rounded-full bg-bg text-[10px] font-bold">{label?.slice(0, 1).toUpperCase()}</span>}<span className="min-w-0 flex-1 truncate text-sm">{label}</span>{evento ? <span className="text-[10px] text-violet-300">{item.efeito?.duracao}t</span> : <span className="text-[10px]">{item.participante?.tipo === 'jogador' ? 'Aliado' : 'Inimigo'}</span>}</div>; })}</div></section>;
}

function Resource({ icon: Icon, label, value, percent, blue = false }) {
  return <div className="mb-3 last:mb-0"><div className="mb-1 flex items-center justify-between text-sm"><span className="flex items-center gap-1 text-muted"><Icon className="h-3.5 w-3.5" />{label}</span><span className="font-mono">{value}</span></div><div className="bar-bg"><div className={`h-full transition-[width] duration-500 ${blue ? 'bg-blue-500' : 'bg-accent'}`} style={{ width: `${percent}%` }} /></div></div>;
}
