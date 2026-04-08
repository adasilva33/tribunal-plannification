#!/usr/bin/env python3
"""
Run ONCE to migrate the existing tribunal.db from the old schema (Assesseur/president string)
to the new schema (Judge + ChamberRole + SessionAssignment).

Usage:
    python migrate.py
"""

import sqlite3
import os
import sys
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'tribunal.db')

# Normalize inconsistent spellings in the source data
NAME_MAP = {
    'P.J. ANCETTE':         'PJ. ANCETTE',
    'H. OUMEDIAN':          'H. OUMÉDIAN',
    'JP. LEYRAUD            ': 'JP. LEYRAUD',
    'R. DUPLESSY         ':  'R. DUPLESSY',
}


def norm(name: str) -> str:
    name = name.strip()
    return NAME_MAP.get(name, name)


def table_exists(cur, name):
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def migrate():
    if not os.path.exists(DB_PATH):
        print(f'ERROR: {DB_PATH} not found. Run `python app.py` first to create it.')
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── Guard: only run once ───────────────────────────────────────────────
    if table_exists(cur, 'judge') and '--force' not in sys.argv:
        print('Migration already applied (judge table exists).')
        print('Use --force to re-run.')
        conn.close()
        return

    if '--force' in sys.argv and table_exists(cur, 'judge'):
        print('Dropping existing new tables for forced re-migration…')
        cur.execute('DROP TABLE IF EXISTS session_assignment')
        cur.execute('DROP TABLE IF EXISTS chamber_role')
        cur.execute('DROP TABLE IF EXISTS judge')

    print('Creating judge table…')
    cur.execute('''
        CREATE TABLE judge (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL UNIQUE,
            email         TEXT UNIQUE,
            password_hash TEXT,
            is_admin      INTEGER NOT NULL DEFAULT 0,
            is_active     INTEGER NOT NULL DEFAULT 1
        )
    ''')

    # ── Collect all unique judge names ─────────────────────────────────────
    unique_names: set[str] = set()

    if table_exists(cur, 'chamber'):
        # Old schema had chamber.president as a string column
        try:
            cur.execute('SELECT president FROM chamber WHERE president IS NOT NULL AND president != ""')
            for row in cur.fetchall():
                unique_names.add(norm(row['president']))
        except Exception:
            pass  # column might not exist if schema was already partially updated

    if table_exists(cur, 'assesseur'):
        cur.execute('SELECT name FROM assesseur WHERE name IS NOT NULL AND name != ""')
        for row in cur.fetchall():
            unique_names.add(norm(row['name']))

    # Insert judges (no email/password — admin sets those later)
    name_to_id: dict[str, int] = {}
    for name in sorted(unique_names):
        cur.execute('INSERT INTO judge (name) VALUES (?)', (name,))
        name_to_id[name] = cur.lastrowid

    print(f'  → {len(name_to_id)} judges created.')

    # ── Create admin account ───────────────────────────────────────────────
    pw_hash = generate_password_hash('admin123')
    cur.execute(
        'INSERT OR IGNORE INTO judge (name, email, password_hash, is_admin) VALUES (?,?,?,1)',
        ('Administrateur', 'admin@tribunal.fr', pw_hash),
    )
    print('  → Admin created: admin@tribunal.fr / admin123  ← CHANGE THIS PASSWORD')

    # ── Create chamber_role table ──────────────────────────────────────────
    print('Creating chamber_role table…')
    cur.execute('''
        CREATE TABLE chamber_role (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            chamber_id INTEGER NOT NULL REFERENCES chamber(id),
            judge_id   INTEGER NOT NULL REFERENCES judge(id),
            role       TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            UNIQUE(chamber_id, judge_id, role)
        )
    ''')

    # Presidents
    if table_exists(cur, 'chamber'):
        try:
            cur.execute('SELECT id, president FROM chamber WHERE president IS NOT NULL AND president != ""')
            for row in cur.fetchall():
                judge_id = name_to_id.get(norm(row['president']))
                if judge_id:
                    cur.execute(
                        'INSERT OR IGNORE INTO chamber_role (chamber_id, judge_id, role, sort_order) VALUES (?,?,?,0)',
                        (row['id'], judge_id, 'president'),
                    )
        except Exception:
            pass

    # Assesseurs
    if table_exists(cur, 'assesseur'):
        cur.execute('SELECT chamber_id, name, sort_order FROM assesseur ORDER BY sort_order')
        for row in cur.fetchall():
            judge_id = name_to_id.get(norm(row['name']))
            if judge_id:
                cur.execute(
                    'INSERT OR IGNORE INTO chamber_role (chamber_id, judge_id, role, sort_order) VALUES (?,?,?,?)',
                    (row['chamber_id'], judge_id, 'assesseur', row['sort_order']),
                )

    # ── Create session_assignment table ───────────────────────────────────
    print('Creating session_assignment table…')
    cur.execute('''
        CREATE TABLE session_assignment (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            chamber_id INTEGER NOT NULL REFERENCES chamber(id),
            date       DATE NOT NULL,
            judge_id   INTEGER NOT NULL REFERENCES judge(id),
            role       TEXT NOT NULL,
            UNIQUE(chamber_id, date, judge_id)
        )
    ''')

    conn.commit()
    conn.close()
    print('\nMigration complete!')
    print('Next: set judge emails/passwords via /config/judges in the web UI.')


if __name__ == '__main__':
    migrate()
