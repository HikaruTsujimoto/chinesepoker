"""Local profiles and transactional, idempotent hand/session statistics."""
import os
import sqlite3
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4


def data_path():
    override = os.environ.get('CHINESEPOKER_DATA_DIR')
    base = Path(override) if override else Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'ChinesePoker'
    return base / 'profiles.sqlite3'


class ProfileStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else data_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=5)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute('PRAGMA foreign_keys=ON')
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2):
                raise sqlite3.DatabaseError('Unsupported profile database version')
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS rounds (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, mode TEXT NOT NULL,
                    occurred_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS hands (
                    round_id TEXT REFERENCES rounds(id), profile_id TEXT REFERENCES profiles(id),
                    points INTEGER NOT NULL, foul INTEGER NOT NULL, was_fl INTEGER NOT NULL,
                    entered_fl INTEGER NOT NULL, continued_fl INTEGER NOT NULL, next_tier INTEGER NOT NULL,
                    PRIMARY KEY(round_id, profile_id));
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT, profile_id TEXT REFERENCES profiles(id), mode TEXT NOT NULL,
                    points INTEGER NOT NULL, occurred_at TEXT NOT NULL,
                    PRIMARY KEY(id, profile_id));
                CREATE INDEX IF NOT EXISTS hands_profile ON hands(profile_id);
                CREATE INDEX IF NOT EXISTS rounds_session ON rounds(session_id);
                CREATE TABLE IF NOT EXISTS wallets (
                    profile_id TEXT PRIMARY KEY REFERENCES profiles(id), balance INTEGER NOT NULL DEFAULT 1000);
                CREATE TABLE IF NOT EXISTS coin_entries (
                    profile_id TEXT REFERENCES profiles(id), reason TEXT, reference TEXT, amount INTEGER NOT NULL,
                    PRIMARY KEY(profile_id,reason,reference));
                INSERT OR IGNORE INTO wallets(profile_id) SELECT id FROM profiles;
                PRAGMA user_version=2;
            ''')
        except Exception:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def profiles(self):
        return [dict(row) for row in self.db.execute('SELECT id,name FROM profiles ORDER BY name_key')]

    def create(self, name):
        name = unicodedata.normalize('NFKC', name).strip()
        if not 1 <= len(name) <= 20 or any(unicodedata.category(c).startswith('C') for c in name):
            raise ValueError('名前は1～20文字で入力してください。')
        ident = uuid4().hex
        try:
            with self.db:
                self.db.execute('INSERT INTO profiles VALUES(?,?,?)', (ident, name, name.casefold()))
                self.db.execute('INSERT INTO wallets(profile_id) VALUES(?)', (ident,))
        except sqlite3.IntegrityError as error:
            raise ValueError('同じ名前のアカウントがあります。') from error
        return ident

    def selected(self):
        known = {p['id'] for p in self.profiles()}
        values = dict(self.db.execute('SELECT key,value FROM settings'))
        result = [values.get(f'seat{i}') for i in range(2)]
        return tuple(p if p in known else None for p in result)

    def select(self, seat, profile_id):
        if seat not in (0, 1):
            raise ValueError('Unknown seat')
        if profile_id is not None:
            if profile_id not in {p['id'] for p in self.profiles()}:
                raise ValueError('アカウントが見つかりません。')
            if self.selected()[1-seat] == profile_id:
                raise ValueError('同じアカウントを両プレイヤーには選べません。')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (f'seat{seat}', profile_id))

    def ensure_test_profiles(self):
        """Create the three starter accounts once, preserving existing accounts and balances."""
        with self.db:
            for i in range(1, 4):
                name = f'テスト{i}'
                self.db.execute('INSERT OR IGNORE INTO profiles VALUES(?,?,?)',
                                (f'starter-{i}', name, name.casefold()))
            self.db.execute('INSERT OR IGNORE INTO wallets(profile_id) SELECT id FROM profiles')

    def balance(self, ident):
        row = self.db.execute('SELECT balance FROM wallets WHERE profile_id=?', (ident,)).fetchone()
        if row is None:
            raise ValueError('アカウントが見つかりません。')
        return row[0]

    def _coins(self, ident, reason, reference, amount):
        added = self.db.execute('INSERT OR IGNORE INTO coin_entries VALUES(?,?,?,?)',
                               (ident, reason, reference, amount)).rowcount
        if added:
            self.db.execute('UPDATE wallets SET balance=balance+? WHERE profile_id=?', (amount, ident))
        return amount if added else 0

    def claim_daily(self, ident, now=None):
        now = now or datetime.now(timezone.utc)
        day = now.astimezone(timezone(timedelta(hours=9))).date().isoformat()
        with self.db:
            # A clock moved backwards must not make older days claimable again.
            last = self.db.execute("SELECT MAX(reference) FROM coin_entries WHERE profile_id=? AND reason='daily'",
                                   (ident,)).fetchone()[0]
            if last and day <= last:
                return 0
            return self._coins(ident, 'daily', day, 50)

    def record_round(self, event):
        """Save both seats and any settled-session totals in one transaction.

        Replaying a saved round is a no-op, so a retry cannot double count.
        Guest seats are absent from event['players']; CPU is never a profile.
        """
        players = event['players']
        if event['mode'] not in ('cpu', 'pvp'):
            raise ValueError('Unknown game mode')
        if len({p['profile_id'] for p in players}) != len(players):
            raise ValueError('Duplicate profile in round')
        with self.db:
            if self.db.execute('SELECT 1 FROM rounds WHERE id=?', (event['round_id'],)).fetchone():
                return
            self.db.execute('INSERT INTO rounds VALUES(?,?,?,?)',
                            (event['round_id'], event['session_id'], event['mode'], event['occurred_at']))
            for p in players:
                self.db.execute('INSERT INTO hands VALUES(?,?,?,?,?,?,?,?)',
                    (event['round_id'], p['profile_id'], p['points'], p['foul'], p['was_fl'],
                     p['entered_fl'], p['continued_fl'], p['next_tier']))
            if event['settled']:
                for p in players:
                    points = self.db.execute('''SELECT SUM(h.points) FROM hands h
                        JOIN rounds r ON r.id=h.round_id WHERE r.session_id=? AND h.profile_id=?''',
                        (event['session_id'], p['profile_id'])).fetchone()[0]
                    self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',
                        (event['session_id'], p['profile_id'], event['mode'], points, event['occurred_at']))
                    if event.get('coin_match'):
                        self._coins(p['profile_id'], 'match', event['session_id'],
                                    100 if points > 0 else -100 if points < 0 else 0)

    def stats(self, profile_id, mode):
        rows = self.db.execute('''SELECT h.*,r.occurred_at FROM hands h JOIN rounds r ON r.id=h.round_id
            WHERE h.profile_id=? AND r.mode=? ORDER BY r.occurred_at DESC,r.rowid DESC''',
            (profile_id, mode)).fetchall()
        sessions = self.db.execute('SELECT points FROM sessions WHERE profile_id=? AND mode=?',
                                   (profile_id, mode)).fetchall()
        points = [r['points'] for r in rows]
        totals = [r['points'] for r in sessions]
        return dict(hands=len(rows), wins=sum(p>0 for p in points), losses=sum(p<0 for p in points),
                    draws=sum(p==0 for p in points), points=sum(points),
                    sessions=len(totals), session_wins=sum(p>0 for p in totals),
                    session_losses=sum(p<0 for p in totals), session_draws=sum(p==0 for p in totals),
                    settled_points=sum(totals), fouls=sum(r['foul'] for r in rows),
                    normal_hands=sum(not r['was_fl'] for r in rows),
                    fl_hands=sum(r['was_fl'] for r in rows),
                    fl_entries=sum(r['entered_fl'] for r in rows),
                    fl_continues=sum(r['continued_fl'] for r in rows),
                    tiers={tier:sum(r['entered_fl'] and r['next_tier']==tier for r in rows)
                           for tier in (14,15,16,17)},
                    recent=[dict(r) for r in rows[:5]])


def round_event(round_id, session_id, mode, profile_ids, players, points, settled):
    """Snapshot only an already resolved, complete hand."""
    if any(p.count_cards()!=13 for p in players):
        raise ValueError('Cannot record an unfinished hand')
    records = []
    for ident, p, score in zip(profile_ids, players, points):
        if ident is None:
            continue
        records.append(dict(profile_id=ident, points=int(score), foul=bool(p.is_foul),
                            was_fl=bool(p.fantasyland),
                            entered_fl=bool(not p.fantasyland and p.next_fantasyland),
                            continued_fl=bool(p.fantasyland and p.next_fantasyland),
                            next_tier=p.next_fantasyland_cards if p.next_fantasyland else 0))
    return dict(round_id=round_id, session_id=session_id, mode=mode,
                occurred_at=datetime.now(timezone.utc).isoformat(), players=records, settled=settled)
