import dotenv from 'dotenv';
import express from 'express';
import session from 'express-session';
import http from 'node:http';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';
import { WebSocketServer, WebSocket } from 'ws';
import { initDatabase } from './database.js';
import router from './routes.js';
import { requireAuth } from './auth.js';
import { getPlayerState } from './player-state.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: process.env.RPG_SYSTEM_ENV_FILE || path.join(process.cwd(), '.env') });
initDatabase();

const app = express();
const PORT = process.env.PORT || 4000;

app.use(express.json({ limit: '25mb' }));
app.use(session({
  secret: process.env.SESSION_SECRET || 'gg-rpg-fallback',
  resave: false,
  saveUninitialized: false,
  cookie: {
    httpOnly: true,
    sameSite: 'strict',
    maxAge: 24 * 60 * 60 * 1000,
  },
}));

// ── Login ──────────────────────────────────────────────
app.post('/api/login', (req, res) => {
  const { senha } = req.body;
  if (!senha) return res.status(400).json({ error: 'A senha é obrigatória.' });
  if (senha === process.env.MASTER_PASSWORD) {
    req.session.autenticado = true;
    return res.json({ ok: true });
  }
  return res.status(401).json({ error: 'Senha incorreta.' });
});

app.post('/api/logout', (req, res) => {
  req.session.destroy(() => res.json({ ok: true }));
});

app.get('/api/status', (req, res) => {
  res.json({ autenticado: !!(req.session && req.session.autenticado) });
});

app.get('/api/player/state', (req, res) => {
  res.json(getPlayerState());
});

// ── API Protegida ─────────────────────────────────────
app.use('/api', requireAuth, router);

app.use((error, req, res, next) => {
  console.error('Erro interno na API:', error);
  if (res.headersSent) return next(error);
  res.status(500).json({ error: 'Erro interno do servidor.' });
});

// ── Frontend Estático (servidor único) ────────────────
const publicDir = path.join(__dirname, '..', 'public');
if (fs.existsSync(publicDir)) {
  app.use(express.static(publicDir, {
    setHeaders(res, filePath) {
      if (filePath.includes(`${path.sep}assets${path.sep}`)) {
        res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
      }
    },
  }));
  app.get('*', (req, res) => {
    res.sendFile(path.join(publicDir, 'index.html'));
  });
}

const server = http.createServer(app);
const playerWss = new WebSocketServer({ server, path: '/ws/player' });

playerWss.on('connection', socket => {
  socket.send(JSON.stringify(getPlayerState()));
});

const playerBroadcast = setInterval(() => {
  if (playerWss.clients.size === 0) return;
  const message = JSON.stringify(getPlayerState());
  for (const client of playerWss.clients) {
    if (client.readyState === WebSocket.OPEN) client.send(message);
  }
}, 1000);
playerBroadcast.unref();

server.listen(PORT, process.env.HOST || '127.0.0.1', () => {
  const host = process.env.HOST || '127.0.0.1';
  console.log(`\n  RPG System GG rodando em http://${host}:${PORT}`);
  console.log(`  Acesso restrito ao Mestre (localhost).\n`);
});
