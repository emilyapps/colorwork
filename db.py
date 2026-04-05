"""
SQLite persistence layer for the pattern generator.
The database file (patterns.db) lives alongside this module.
"""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "patterns.db")


def init_db():
    """Create tables if they don't exist."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT    NOT NULL,
                created_at     TEXT    NOT NULL,
                grid_w         INTEGER NOT NULL,
                grid_h         INTEGER NOT NULL,
                symmetry_group TEXT    NOT NULL,
                fill_color     TEXT    NOT NULL,
                bg_color       TEXT    NOT NULL,
                fill_density   REAL    NOT NULL,
                grid_data      TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                data        TEXT    NOT NULL
            )
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# Pattern persistence  (tile only)
# ---------------------------------------------------------------------------

def save_pattern(name, grid_w, grid_h, symmetry_group,
                 fill_color, bg_color, fill_density, grid):
    """Insert a pattern and return its new id."""
    grid_data  = json.dumps([[bool(cell) for cell in row] for row in grid])
    created_at = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("""
            INSERT INTO patterns
                (name, created_at, grid_w, grid_h, symmetry_group,
                 fill_color, bg_color, fill_density, grid_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, created_at, grid_w, grid_h, symmetry_group,
              fill_color, bg_color, fill_density, grid_data))
        conn.commit()
        return cur.lastrowid


def load_pattern(pattern_id):
    """Return a dict for the given id, with 'grid' as a 2-D list of bools.
    Returns None if not found."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM patterns WHERE id = ?", (pattern_id,)
        ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["grid"] = json.loads(data["grid_data"])
    return data


def list_patterns():
    """Return all patterns ordered newest-first (without grid_data)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT id, name, created_at, grid_w, grid_h, symmetry_group,
                   fill_color, bg_color
            FROM patterns
            ORDER BY created_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


def delete_pattern(pattern_id):
    """Permanently remove a pattern by id."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM patterns WHERE id = ?", (pattern_id,))
        conn.commit()


# ---------------------------------------------------------------------------
# Project persistence  (full state)
# ---------------------------------------------------------------------------

def save_project(name, data_dict):
    """Insert a project and return its new id."""
    created_at = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO projects (name, created_at, data) VALUES (?, ?, ?)",
            (name, created_at, json.dumps(data_dict))
        )
        conn.commit()
        return cur.lastrowid


def load_project(project_id):
    """Return a dict with 'data' already deserialised. Returns None if not found."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["data"] = json.loads(result["data"])
    return result


def list_projects():
    """Return all projects ordered newest-first (without data blob)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, name, created_at FROM projects ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_project(project_id):
    """Permanently remove a project by id."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
