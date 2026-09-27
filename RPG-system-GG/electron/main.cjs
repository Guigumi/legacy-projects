const { app, BrowserWindow, dialog, shell } = require('electron');
const { autoUpdater } = require('electron-updater');
const { spawn, execFile } = require('node:child_process');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');

const APP_ID = 'com.guigumi.rpgsystemgg';
const SERVER_HOST = '127.0.0.1';
const DATA_DIR = process.platform === 'linux' ? path.join(process.env.XDG_DATA_HOME || path.join(os.homedir(), '.local', 'share'), 'rpg-system-gg') : app.getPath('userData');
const ENV_FILE_NAME = '.env';

let mainWindow = null;
let backendProcess = null;
let backendPort = null;
let quitting = false;
let shuttingDown = null;
let logStream = null;

app.setAppUserModelId(APP_ID);
app.setPath('userData', DATA_DIR);

function backendRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'backend')
    : path.join(__dirname, '..', 'backend');
}

function dataPath(name) {
  return path.join(DATA_DIR, name);
}

async function ensureEnvironment() {
  await fsp.mkdir(DATA_DIR, { recursive: true });
  const envFile = dataPath(ENV_FILE_NAME);
  try {
    await fsp.access(envFile, fs.constants.F_OK);
  } catch {
    await fsp.copyFile(path.join(backendRoot(), '.env.example'), envFile);
  }
  return envFile;
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, SERVER_HOST, () => {
      const port = server.address().port;
      server.close(error => error ? reject(error) : resolve(port));
    });
  });
}

function runNodeScript(script, env, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [script], {
      cwd,
      env: { ...env, ELECTRON_RUN_AS_NODE: '1' },
      stdio: ['ignore', logStream, logStream],
    });
    child.once('error', reject);
    child.once('exit', (code, signal) => {
      if (code === 0) resolve();
      else reject(new Error(`${script} encerrou com código ${code ?? signal}.`));
    });
  });
}

async function startBackend() {
  const root = backendRoot();
  const envFile = await ensureEnvironment();
  backendPort = await findFreePort();
  logStream = fs.openSync(dataPath('server.log'), 'a');
  const env = {
    ...process.env,
    HOST: SERVER_HOST,
    PORT: String(backendPort),
    RPG_SYSTEM_DATA_DIR: DATA_DIR,
    RPG_SYSTEM_ENV_FILE: envFile,
  };

  await runNodeScript('src/seed.js', env, root);
  backendProcess = spawn(process.execPath, ['src/server.js'], {
    cwd: root,
    env: { ...env, ELECTRON_RUN_AS_NODE: '1' },
    stdio: ['ignore', logStream, logStream],
  });
  backendProcess.once('error', error => console.error('Falha no backend:', error));
  backendProcess.once('exit', (code, signal) => {
    backendProcess = null;
    if (!quitting && code !== 0) {
      dialog.showErrorBox('RPG System GG', `O servidor encerrou inesperadamente (${code ?? signal}). Consulte server.log.`);
      app.quit();
    }
  });

  const url = `http://${SERVER_HOST}:${backendPort}`;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch(`${url}/api/status`, { cache: 'no-store' });
      if (response.ok) return url;
    } catch { /* backend ainda iniciando */ }
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error(`O backend não respondeu em ${url}. Consulte ${dataPath('server.log')}.`);
}

async function stopBackend() {
  if (shuttingDown) return shuttingDown;
  shuttingDown = (async () => {
    if (!backendProcess) {
      if (logStream) { fs.closeSync(logStream); logStream = null; }
      return;
    }
    const child = backendProcess;
    backendProcess = null;
    child.kill('SIGTERM');
    await new Promise(resolve => {
      const timer = setTimeout(() => {
        if (child.exitCode === null) child.kill('SIGKILL');
        resolve();
      }, 3000);
      child.once('exit', () => {
        clearTimeout(timer);
        resolve();
      });
    });
    if (logStream) {
      fs.closeSync(logStream);
      logStream = null;
    }
  })();
  return shuttingDown;
}

function createWindow(url) {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 980,
    minHeight: 680,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: '#080b0f',
    icon: path.join(__dirname, '..', 'build', 'icon.svg'),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  window.once('ready-to-show', () => window.show());
  window.webContents.setWindowOpenHandler(({ url: target }) => {
    if (target.startsWith(url)) return { action: 'allow' };
    shell.openExternal(target);
    return { action: 'deny' };
  });
  window.loadURL(url).catch(error => {
    dialog.showErrorBox('RPG System GG', `Não foi possível abrir a interface: ${error.message}`);
    app.quit();
  });
  window.on('closed', () => {
    mainWindow = null;
    app.quit();
  });
  return window;
}

function configureAutoUpdater() {
  if (!app.isPackaged) return;
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.on('update-available', async info => {
    const answer = await dialog.showMessageBox(mainWindow, {
      type: 'info',
      title: 'Atualização disponível',
      message: `A versão ${info.version} do RPG System GG está disponível.`,
      detail: 'Deseja baixar agora? A instalação será concluída quando o aplicativo for fechado.',
      buttons: ['Baixar atualização', 'Depois'],
      defaultId: 0,
      cancelId: 1,
    });
    if (answer.response === 0) {
      try { await autoUpdater.downloadUpdate(); }
      catch (error) { dialog.showErrorBox('Atualização', `Não foi possível baixar a atualização: ${error.message}`); }
    }
  });
  autoUpdater.on('update-downloaded', () => {
    dialog.showMessageBox(mainWindow, {
      type: 'info',
      title: 'Atualização pronta',
      message: 'A atualização foi baixada.',
      detail: 'Ela será instalada ao fechar o aplicativo.',
      buttons: ['Fechar e atualizar', 'Depois'],
      defaultId: 0,
    }).then(({ response }) => {
      if (response === 0) autoUpdater.quitAndInstall();
    });
  });
  autoUpdater.on('error', error => {
    console.error('Atualização automática indisponível:', error.message);
  });
  autoUpdater.checkForUpdates().catch(error => console.error('Falha ao verificar atualização:', error.message));
}

async function shutdownAndQuit() {
  if (quitting) return;
  quitting = true;
  await stopBackend();
  app.quit();
}

app.whenReady().then(async () => {
  try {
    const url = await startBackend();
    mainWindow = createWindow(url);
    configureAutoUpdater();
  } catch (error) {
    console.error(error);
    dialog.showErrorBox('RPG System GG', error.message);
    await stopBackend();
    app.quit();
  }
});

app.on('before-quit', event => {
  if (!quitting && backendProcess) {
    event.preventDefault();
    shutdownAndQuit();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') shutdownAndQuit();
});

app.on('activate', () => {
  if (mainWindow === null && backendPort) mainWindow = createWindow(`http://${SERVER_HOST}:${backendPort}`);
});
