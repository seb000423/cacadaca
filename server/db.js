/* ══════════════════════════════════════════════════════════════
   PolyTwin 계정 저장소 — 백엔드 이원화

   로컬:   node:sqlite (Node 22.5+ 내장) — npm install 없이
           node server/server.js 만으로 뜬다. 기존 그대로.
   Vercel: Turso(libSQL) — 서버리스 함수의 파일시스템은 읽기
           전용이고 인스턴스 간 공유도 안 되므로 파일 DB 가
           유지되지 않는다. TURSO_DATABASE_URL 이 있으면 이쪽.

   두 백엔드 모두 같은 SQL(SQLite 문법)을 쓴다. 인터페이스는
   async 한 벌 — 로컬 sync 호출을 async 로 감싸는 비용으로
   라우트 핸들러를 한 벌만 유지한다.

   의존성은 @libsql/client 하나뿐이고, 그마저 TURSO_DATABASE_URL
   이 있을 때만 require 한다 — 로컬은 여전히 node_modules 없이 돈다.
   ══════════════════════════════════════════════════════════════ */
'use strict';

const path = require('node:path');
const { hashPassword } = require('./auth');

const now = () => Date.now();

const SCHEMA = `
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  login_id      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
  name          TEXT    NOT NULL DEFAULT '',
  pw_hash       TEXT    NOT NULL,
  role          TEXT    NOT NULL DEFAULT 'engineer'  CHECK (role IN ('admin','engineer')),
  status        TEXT    NOT NULL DEFAULT 'pending'   CHECK (status IN ('pending','active','suspended')),
  created_at    INTEGER NOT NULL,
  last_login_at INTEGER
);

CREATE TABLE IF NOT EXISTS sessions (
  token      TEXT    PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS audit (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  at     INTEGER NOT NULL,
  actor  TEXT    NOT NULL,
  action TEXT    NOT NULL,
  target TEXT    NOT NULL DEFAULT '',
  detail TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit(at DESC);
`;

/* ── 저수준 인터페이스: run / get / all — 전부 async ─────────── */

function makeSqliteBackend() {
  const fs = require('node:fs');
  const { DatabaseSync } = require('node:sqlite');

  const DATA_DIR = path.join(__dirname, '..', 'data');
  const DB_PATH = process.env.PT_DB || path.join(DATA_DIR, 'polytwin.db');
  fs.mkdirSync(DATA_DIR, { recursive: true });

  const db = new DatabaseSync(DB_PATH);
  /* WAL 은 읽기와 쓰기가 서로를 막지 않게 한다. 데모 중 잠김을 피하는 목적 */
  db.exec('PRAGMA journal_mode = WAL');
  db.exec('PRAGMA foreign_keys = ON');
  db.exec(SCHEMA);

  return {
    path: DB_PATH,
    async run(sql, args = []) {
      const r = db.prepare(sql).run(...args);
      return { lastId: Number(r.lastInsertRowid), changes: Number(r.changes) };
    },
    async get(sql, args = []) { return db.prepare(sql).get(...args) || null; },
    async all(sql, args = []) { return db.prepare(sql).all(...args); },
  };
}

function makeLibsqlBackend() {
  /* 여기서만 require — 로컬 무의존 기동을 깨지 않는다 */
  const { createClient } = require('@libsql/client');
  const client = createClient({
    url: process.env.TURSO_DATABASE_URL,
    authToken: process.env.TURSO_AUTH_TOKEN,
  });

  /* 서버리스에는 "최초 기동"이 없다 — 스키마는 첫 질의 전에 1회 보장.
     콜드 스타트마다 IF NOT EXISTS 몇 개가 도는 비용은 수 ms 라 수용한다 */
  let ready = null;
  const ensure = () => {
    if (!ready) {
      ready = client.batch(
        SCHEMA.split(';').map((s) => s.trim()).filter(Boolean),
        'write',
      );
    }
    return ready;
  };

  return {
    path: process.env.TURSO_DATABASE_URL,
    async run(sql, args = []) {
      await ensure();
      const r = await client.execute({ sql, args });
      return { lastId: Number(r.lastInsertRowid ?? 0), changes: r.rowsAffected };
    },
    async get(sql, args = []) {
      await ensure();
      const r = await client.execute({ sql, args });
      return r.rows[0] || null;
    },
    async all(sql, args = []) {
      await ensure();
      const r = await client.execute({ sql, args });
      return r.rows;
    },
  };
}

const be = process.env.TURSO_DATABASE_URL ? makeLibsqlBackend() : makeSqliteBackend();

/* ── 스토어 — 백엔드와 무관하게 한 벌 ────────────────────────── */
const store = {
  now,

  findByLogin: (loginId) => be.get('SELECT * FROM users WHERE login_id = ?', [loginId]),
  findById: (id) => be.get('SELECT * FROM users WHERE id = ?', [id]),

  async createUser({ loginId, name = '', password, role = 'engineer', status = 'pending' }) {
    const r = await be.run(
      'INSERT INTO users (login_id, name, pw_hash, role, status, created_at) VALUES (?, ?, ?, ?, ?, ?)',
      [loginId, name, hashPassword(password), role, status, now()],
    );
    return store.findById(r.lastId);
  },

  listUsers: () => be.all(`SELECT id, login_id, name, role, status, created_at, last_login_at
                           FROM users ORDER BY
                             CASE status WHEN 'pending' THEN 0 WHEN 'active' THEN 1 ELSE 2 END,
                             created_at DESC`),
  setStatus: (id, status) => be.run('UPDATE users SET status = ? WHERE id = ?', [status, id]),
  setRole: (id, role) => be.run('UPDATE users SET role = ? WHERE id = ?', [role, id]),
  setPassword: (id, password) => be.run('UPDATE users SET pw_hash = ? WHERE id = ?', [hashPassword(password), id]),
  touchLogin: (id) => be.run('UPDATE users SET last_login_at = ? WHERE id = ?', [now(), id]),
  async deleteUser(id) {
    await be.run('DELETE FROM sessions WHERE user_id = ?', [id]);
    return (await be.run('DELETE FROM users WHERE id = ?', [id])).changes;
  },
  async activeAdminCount() {
    const r = await be.get("SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND status = 'active'");
    return Number(r.n);
  },

  createSession(userId, token, ttlMs) {
    const t = now();
    return be.run('INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)',
      [token, userId, t, t + ttlMs]);
  },
  async readSession(token) {
    if (!token) return null;
    const row = await be.get(`SELECT s.token, s.expires_at, u.*
                              FROM sessions s JOIN users u ON u.id = s.user_id
                              WHERE s.token = ?`, [token]);
    if (!row) return null;
    if (Number(row.expires_at) < now()) { await be.run('DELETE FROM sessions WHERE token = ?', [token]); return null; }
    return row;
  },
  dropSession: (token) => be.run('DELETE FROM sessions WHERE token = ?', [token]),
  dropSessionsOfUser: (userId) => be.run('DELETE FROM sessions WHERE user_id = ?', [userId]),
  async sweepSessions() { return (await be.run('DELETE FROM sessions WHERE expires_at < ?', [now()])).changes; },

  log: (actor, action, target = '', detail = '') =>
    be.run('INSERT INTO audit (at, actor, action, target, detail) VALUES (?, ?, ?, ?, ?)',
      [now(), actor, action, target, detail]),
  recentAudit: (n = 50) => be.all('SELECT * FROM audit ORDER BY at DESC LIMIT ?', [n]),

  path: be.path,
};

module.exports = store;
