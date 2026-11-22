from datetime import datetime, timezone
from time import perf_counter

from app.modules.archive.identity import digest
from .pipeline import run
from .storage import publish_retest


def build_ledger(database, material):
    started = perf_counter()
    results = run(material)
    duration_ms = round(1000 * (perf_counter() - started))
    calibration = results['retest_calibration']
    batches = []
    for batch in calibration['batches']:
        retest = next(item for item in material['retests'] if item['retest_id'] == batch['retest_id'])
        batches.append({
            'retest_id': batch['retest_id'],
            'side': batch['side'],
            'scope_mm': [batch['start_mm'], batch['end_mm']],
            'recorded_at': batch['recorded_at'],
            'trace_sha256': digest(retest['trace'].encode()),
            'in_scope': batch['in_scope'],
            'out_of_scope': batch['out_of_scope'],
            'isolated': batch['isolated'],
        })
    design_rows = results['retest_design']['rows'] if results.get('retest_design') else []
    # The ledger content is deterministic in the inputs so identical retries deduplicate.
    ledger = {
        'retest_id': '-'.join(batch['retest_id'] for batch in batches),
        'state': 'CONFIRMED',
        'baseline_sha256': {key: digest(text.encode()) for key, text in material['traces'].items()},
        'settings': calibration['settings'],
        'batches': batches,
        'reviewed_joints': [row['joint'] for row in design_rows if row['epoch'] == 'RETEST'],
        'pending_joints': [row['joint'] for row in design_rows
                           if row['code'] in {'RETEST_PENDING', 'RETEST_PARTIAL_PAIR'}],
        'computed': results,
    }
    stored, fresh = publish_retest(
        database, ledger,
        submitted_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        duration_ms=duration_ms)
    return stored, fresh
