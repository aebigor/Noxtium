import 'dotenv/config';
import express from 'express';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import makeWASocket, { Browsers, DisconnectReason, useMultiFileAuthState } from '@whiskeysockets/baileys';
import QRCode from 'qrcode';
import pino from 'pino';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 3010);
const API_SECRET = process.env.QR_WHATSAPP_API_SECRET || '';
const CALLBACK_URL = process.env.NOXTIUM_CALLBACK_URL || 'http://127.0.0.1:5000/webhooks/qr-whatsapp';
const CALLBACK_SECRET = process.env.NOXTIUM_CALLBACK_SECRET || API_SECRET;
const sessionsDir = path.resolve(process.env.WHATSAPP_SESSIONS_DIR || path.join(__dirname, 'sessions'));
fs.mkdirSync(sessionsDir, { recursive: true });
const app = express();
app.disable('x-powered-by');
app.use(express.json({ limit: '1mb' }));
const sessions = new Map();
const logger = pino({ level: process.env.LOG_LEVEL || 'warn' });

function auth(req, res, next) {
  if (!API_SECRET || req.get('authorization') !== `Bearer ${API_SECRET}`) return res.status(401).json({ error: 'No autorizado.' });
  next();
}
function safeCompanyId(value) {
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}
async function notify(companyId, payload) {
  try {
    const response = await fetch(CALLBACK_URL, {
      method: 'POST', headers: { 'content-type': 'application/json', 'X-Noxtium-Secret': CALLBACK_SECRET },
      body: JSON.stringify({ company_id: companyId, ...payload }), signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) logger.warn({ companyId, status: response.status }, 'Callback NOXTIUM no aceptado');
  } catch (err) { logger.warn({ companyId, error: err.message }, 'Callback NOXTIUM falló'); }
}
function stateFor(companyId) {
  let state = sessions.get(companyId);
  if (!state) {
    state = { status: 'disconnected', qr: null, qrDataUrl: null, phoneNumber: null, verifiedName: null, lastError: null, sock: null, starting: false };
    sessions.set(companyId, state);
  }
  return state;
}
async function startSession(companyId) {
  const state = stateFor(companyId);
  if (state.status === 'connected') return state;
  if (state.starting) return state;
  state.starting = true; state.status = 'connecting'; state.qr = null; state.qrDataUrl = null; state.lastError = null;
  const authDir = path.join(sessionsDir, String(companyId));
  fs.mkdirSync(authDir, { recursive: true });
  try {
    const { state: authState, saveCreds } = await useMultiFileAuthState(authDir);
    const sock = makeWASocket({ auth: authState, logger: pino({ level: 'silent' }), printQRInTerminal: false, browser: Browsers.ubuntu('Chrome'), markOnlineOnConnect: false, syncFullHistory: false });
    state.sock = sock;
    sock.ev.on('creds.update', saveCreds);
    sock.ev.on('connection.update', async update => {
      if (update.qr) {
        state.qr = update.qr;
        try { state.qrDataUrl = await QRCode.toDataURL(update.qr, { margin: 2, width: 320 }); } catch { state.qrDataUrl = null; }
        state.status = 'connecting';
      }
      if (update.connection === 'open') {
        state.status = 'connected'; state.qr = null; state.qrDataUrl = null; state.lastError = null;
        const jid = sock.user?.id || '';
        state.phoneNumber = jid.split(':')[0].split('@')[0] || null;
        state.verifiedName = sock.user?.name || null;
        await notify(companyId, { event: 'connection.update', status: 'connected', phone_number: state.phoneNumber, verified_name: state.verifiedName });
      }
      if (update.connection === 'close') {
        const code = update.lastDisconnect?.error?.output?.statusCode;
        const loggedOut = code === DisconnectReason.loggedOut;
        state.status = loggedOut ? 'logged_out' : 'disconnected'; state.qr = null; state.qrDataUrl = null; state.sock = null;
        if (!loggedOut) state.lastError = 'WhatsApp se desconectó. Pulsa Generar código QR para volver a conectar.';
        await notify(companyId, { event: 'connection.update', status: state.status, last_error: state.lastError });
      }
    });
    sock.ev.on('messages.upsert', async ({ messages, type }) => {
      if (type !== 'notify') return;
      for (const msg of messages || []) {
        if (!msg.message || msg.key?.fromMe || msg.key?.remoteJid === 'status@broadcast') continue;
        const remote = msg.key?.remoteJid || '';
        const fromNumber = remote.split('@')[0].split(':')[0];
        const body = msg.message.conversation || msg.message.extendedTextMessage?.text || msg.message.imageMessage?.caption || msg.message.videoMessage?.caption || '';
        const msgId = msg.key?.id;
        if (!msgId) continue;
        await notify(companyId, { event: 'whatsapp.message', message_id: `qr:${companyId}:${msgId}`, from_number: fromNumber, contact_name: msg.pushName || null, text: body, message_type: body ? 'text' : 'other', timestamp: msg.messageTimestamp || Date.now() });
      }
    });
    return state;
  } catch (err) {
    state.status = 'error'; state.lastError = 'No se pudo iniciar WhatsApp. Revisa los registros del servicio.'; state.starting = false;
    await notify(companyId, { event: 'connection.update', status: 'error', last_error: state.lastError });
    throw err;
  } finally { state.starting = false; }
}

app.get('/health', (_req, res) => res.json({ status: 'ok' }));
app.use(auth);
app.post('/sessions/start', async (req, res) => {
  const companyId = safeCompanyId(req.body?.company_id);
  if (!companyId) return res.status(400).json({ error: 'company_id inválido.' });
  try { const s = await startSession(companyId); return res.json({ status: s.status, qr_data_url: s.qrDataUrl, phone_number: s.phoneNumber }); }
  catch (err) { logger.error({ companyId, error: err.message }, 'startSession'); return res.status(503).json({ error: 'No se pudo iniciar la sesión de WhatsApp.' }); }
});
app.get('/sessions/:companyId/status', async (req, res) => {
  const id = safeCompanyId(req.params.companyId);
  if (!id) return res.status(400).json({ error: 'company_id inválido.' });
  const s = stateFor(id);
  // Restore existing session lazily when the service restarts.
  if (!s.sock && s.status === 'disconnected' && fs.existsSync(path.join(sessionsDir, String(id), 'creds.json'))) {
    startSession(id).catch(() => {});
  }
  res.json({ status: s.status, qr_data_url: s.qrDataUrl, phone_number: s.phoneNumber, verified_name: s.verifiedName, last_error: s.lastError });
});
app.post('/sessions/:companyId/disconnect', async (req, res) => {
  const id = safeCompanyId(req.params.companyId);
  if (!id) return res.status(400).json({ error: 'company_id inválido.' });
  const s = stateFor(id);
  try { if (s.sock) await s.sock.logout(); } catch { try { s.sock?.end(undefined); } catch {} }
  s.sock = null; s.status = 'disconnected'; s.qr = null; s.qrDataUrl = null; s.phoneNumber = null; s.lastError = null;
  await notify(id, { event: 'connection.update', status: 'disconnected' });
  // Explicit disconnect removes the saved login so the next start requires a new QR.
  fs.rmSync(path.join(sessionsDir, String(id)), { recursive: true, force: true });
  res.json({ ok: true, status: s.status });
});
app.post('/sessions/:companyId/send', async (req, res) => {
  const id = safeCompanyId(req.params.companyId);
  if (!id) return res.status(400).json({ error: 'company_id inválido.' });
  const s = stateFor(id);
  if (s.status !== 'connected' || !s.sock) return res.status(409).json({ error: 'WhatsApp no está conectado.' });
  const to = String(req.body?.to || '').replace(/\D/g, '');
  const text = String(req.body?.text || '').trim().slice(0, 4000);
  if (to.length < 8 || to.length > 15 || !text) return res.status(400).json({ error: 'Número internacional o texto no válido.' });
  try {
    const sent = await s.sock.sendMessage(`${to}@s.whatsapp.net`, { text });
    res.json({ ok: true, message_id: `out:${id}:${sent.key?.id || Date.now()}` });
  } catch (err) { logger.error({ id, error: err.message }, 'sendMessage'); res.status(502).json({ error: 'No se pudo enviar el mensaje.' }); }
});

app.listen(PORT, '127.0.0.1', () => {
  if (!API_SECRET) logger.error('QR_WHATSAPP_API_SECRET no está configurada; API bloqueada.');
  logger.info(`NOXTIUM QR service escuchando en 127.0.0.1:${PORT}`);
});
