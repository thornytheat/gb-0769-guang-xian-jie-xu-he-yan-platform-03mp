from app.modules.loss.verdict import verdict
from app.modules.pairs.optimal import best_pairs


def _scope_of(point, batches):
    hits = [b for b in batches if b['start_mm'] <= point['chain_mm'] <= b['end_mm']]
    return hits


def reconcile(calibrated, joined, loss):
    points = calibrated['aligned'].get('design')
    if points is None:
        # Retest runs carry only a/b; design points are not needed for pairing previews.
        points = []
    tolerance = calibrated['settings']['design_tol_mm']
    measurements = loss['rows']
    valid = [row for row in points if not row.get('code')]
    links = best_pairs([r['chain_mm']*2 for r in valid], [r['midpoint_half_mm'] for r in measurements], tolerance*2)
    mapped = {valid[i]['id']: measurements[j] for i, j in links}
    batches = calibrated.get('batches', [])
    rows = []
    for point in points:
        candidate = mapped.get(point['id'])
        covering = _scope_of(point, batches) if not point.get('code') else []
        near_singles = [dict(id=r['id'], source=r['source'], line=r['line'], epoch=r['epoch'],
                             retest_id=r.get('retest_id'), code=r['code'])
                        for r in joined['singles']
                        if abs(r['chain_mm']-point['chain_mm']) <= tolerance and not point.get('code')]
        # A joint inside a retest window can only be confirmed by a same-epoch retest pair.
        # A baseline pair there would mean coupling the new reading with the old opposite end.
        pair = candidate if candidate and (not covering or candidate['epoch'] == 'RETEST') else None
        if pair:
            code = verdict(pair['net_double_mdb'], point['limit_mdb'])
        elif point.get('code'):
            code = point['code']
        elif covering:
            retest_sides = {b['side'] for b in covering}
            code = 'RETEST_PENDING' if len(retest_sides) < 2 else 'RETEST_PARTIAL_PAIR'
        else:
            code = 'SINGLE_SIDE_ONLY' if near_singles else 'NO_COUPLED_EVIDENCE'
        bucket = {'PASS': 'passed', 'OVER_LIMIT': 'over_limit'}.get(code, 'missing')
        if pair and pair['epoch'] == 'RETEST':
            bucket = {'PASS': 'retest_passed', 'OVER_LIMIT': 'retest_over_limit'}.get(code, 'missing')
        evidence = []
        if pair:
            for side in ('a', 'b'):
                row = pair[side]
                evidence.append({'side': side, 'id': row['id'], 'line': row['line'],
                                 'epoch': row['epoch'], 'retest_id': row.get('retest_id'),
                                 'loss_mdb': row['loss_mdb']})
        rows.append({'joint': point['id'], 'chain_mm': point['chain_mm'], 'design_line': point['line'],
                     'limit_mdb': point['limit_mdb'], 'pair': pair['pair'] if pair else None,
                     'epoch': pair['epoch'] if pair else None,
                     'retest_id': pair['retest_id'] if pair else None,
                     'net_db': pair['net_db'] if pair else None, 'code': code, 'bucket': bucket,
                     'near_singles': near_singles, 'evidence': evidence,
                     'retest_scope': [dict(retest_id=b['retest_id'], side=b['side'],
                                           start_mm=b['start_mm'], end_mm=b['end_mm']) for b in covering],
                     'a_line': pair['a']['line'] if pair else None,
                     'b_line': pair['b']['line'] if pair else None,
                     'gain_ends': pair['gain_ends'] if pair else []})
    totals = {key: sum(r['bucket'] == key for r in rows)
              for key in ('passed', 'over_limit', 'retest_passed', 'retest_over_limit', 'missing')}
    pending = sum(r['code'] in {'RETEST_PENDING', 'RETEST_PARTIAL_PAIR'} for r in rows)
    reviewed = sum(1 for r in rows if r['epoch'] == 'RETEST')
    measured = sum(1 for side in ('a', 'b') for r in calibrated['aligned'][side] if r['epoch'] != 'SUPERSEDED')
    live_singles = [s for s in joined['singles'] if s['epoch'] != 'SUPERSEDED']
    coupled = sum(1 for r in rows if r['pair'])
    accepted_pairs = {r['pair'] for r in rows if r['pair']}
    effective_orphans = [r for r in measurements if r['pair'] not in accepted_pairs]
    return {'design_count': len(points), **totals, 'retest_pending': pending, 'retest_reviewed': reviewed,
            'balanced': len(measurements) == coupled + len(effective_orphans),
            'rows': rows, 'orphans': effective_orphans, 'orphan_pairs': len(effective_orphans),
            'singles': joined['singles'], 'single_count': joined['single_count'],
            'measurements': measured,
            'measurements_balanced': measured == 2*len(effective_orphans) + 2*coupled + len(live_singles)}
