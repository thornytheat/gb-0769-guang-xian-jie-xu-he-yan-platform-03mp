from app.modules.calibration.service import calibrate
from app.modules.trace.service import ingest, receive_source
from .contract import setup

SOURCES = ('a', 'b')


def _within(row, retest):
    return retest['start_mm'] <= row['chain_mm'] <= retest['end_mm']


def prepare(material, settings):
    """Build epoch-aware calibration from baseline traces plus retest batches."""
    retests = setup(material.get('retests'))
    accepted = ingest({key: material['traces'][key] for key in (*SOURCES, 'design')})
    base = calibrate(accepted['traces'], settings)
    aligned = {key: [dict(row, epoch='BASELINE', retest_id=None) for row in base['aligned'][key]]
               for key in SOURCES}
    outliers = [dict(row, epoch='BASELINE', retest_id=None) for row in base['outliers']]
    isolated = list(accepted['isolated'])
    batches = []
    for retest in retests:
        data, meta, issues = receive_source(retest['side'], retest['trace'])
        for issue in issues:
            isolated.append({**issue, 'retest_id': retest['retest_id']})
        # A retest uses the same end coordinate convention as its side; reuse calibration rules.
        other = 'b' if retest['side'] == 'a' else 'a'
        stub = calibrate({retest['side']: data, other: [], 'design': []}, settings)
        covered, outside = [], []
        for row in stub['aligned'][retest['side']]:
            tagged = {**row, 'epoch': 'RETEST', 'retest_id': retest['retest_id'],
                      'coverage': 'INSIDE' if _within(row, retest) else 'OUTSIDE_SCOPE'}
            (covered if tagged['coverage'] == 'INSIDE' else outside).append(tagged)
        for row in stub['outliers']:
            outliers.append({**row, 'retest_id': retest['retest_id'], 'epoch': 'RETEST',
                             'coverage': 'OUTSIDE_SCOPE'})
        side = retest['side']
        if covered:
            # Only a retest that actually contributes in-scope readings supersedes baseline rows.
            for row in aligned[side]:
                if row['epoch'] == 'BASELINE' and _within(row, retest):
                    row['superseded_by'] = retest['retest_id']
                    row['epoch'] = 'SUPERSEDED'
        # In-scope readings replace baseline; out-of-scope ones stay visible as retest singles.
        aligned[side].extend(covered)
        aligned[side].extend(outside)
        batches.append({'retest_id': retest['retest_id'], 'side': side,
                        'start_mm': retest['start_mm'], 'end_mm': retest['end_mm'],
                        'recorded_at': retest['recorded_at'].isoformat(timespec='seconds')
                        if retest['recorded_at'] else None,
                        'accepted': meta['accepted'], 'isolated': meta['isolated'],
                        'in_scope': len(covered), 'out_of_scope': len(outside),
                        'issues': issues, 'out_of_scope_rows': outside})
    for key in SOURCES:
        aligned[key].sort(key=lambda item: (item['chain_mm'], item['id']))
    return {'settings': settings, 'aligned': aligned, 'outliers': outliers,
            'retest_isolated': isolated, 'batches': batches}
