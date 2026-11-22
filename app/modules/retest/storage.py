import json

from app.errors import InspectionError
from app.modules.archive.identity import canonical
from app.modules.archive.storage import session

SCHEMA = ('CREATE TABLE IF NOT EXISTS retests '
          '(id TEXT UNIQUE NOT NULL, document BLOB NOT NULL, '
          'submitted_at TEXT NOT NULL, duration_ms INTEGER NOT NULL)')


def _connect(db):
    db.execute(SCHEMA)


def ledger_document(database, retest_id):
    with session(database) as db:
        _connect(db)
        row = db.execute('SELECT document, submitted_at, duration_ms FROM retests WHERE id=?',
                         (retest_id,)).fetchone()
        if not row:
            raise InspectionError('RETEST_NOT_FOUND', status=404)
        ledger = json.loads(row[0])
        ledger['submitted_at'] = row[1]
        ledger['duration_ms'] = row[2]
        return ledger


def ledger_recent(database, limit=50):
    with session(database) as db:
        _connect(db)
        rows = db.execute('SELECT document, submitted_at FROM retests ORDER BY rowid DESC LIMIT ?',
                          (limit,))
        result = []
        for data, submitted_at in rows:
            row = json.loads(data)
            result.append({'retest_id': row['retest_id'], 'submitted_at': submitted_at,
                           'state': row['state'],
                           'sides': sorted({batch['side'] for batch in row['batches']})})
        return result


def publish_retest(database, ledger, submitted_at, duration_ms):
    """Idempotent ledger write.

    Same id + same content -> the confirmed record wins (created=False).
    Same id + different content -> RETEST_CONFLICT, nothing is overwritten.
    Late-arriving older measurements therefore can never replace a confirmed retest.
    """
    with session(database) as db:
        _connect(db)
        key = ledger['retest_id']
        payload = canonical(ledger)
        changed = db.execute(
            'INSERT INTO retests VALUES (?, ?, ?, ?) ON CONFLICT(id) DO NOTHING',
            (key, payload, submitted_at, duration_ms)).rowcount
        stored = db.execute('SELECT document, submitted_at, duration_ms FROM retests WHERE id=?',
                            (key,)).fetchone()
        if stored[0] != payload:
            raise InspectionError('RETEST_CONFLICT', source=key, status=409)
        record = json.loads(stored[0])
        record['submitted_at'] = stored[1]
        record['duration_ms'] = stored[2]
        return record, changed == 1
