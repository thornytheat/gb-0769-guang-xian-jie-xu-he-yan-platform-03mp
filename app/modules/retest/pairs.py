from bisect import bisect_left, bisect_right

from app.modules.pairs.optimal import best_pairs


def _lineage(row):
    return {'epoch': row['epoch'], 'retest_id': row.get('retest_id')}


def join(calibrated):
    """Pairing that never couples baseline readings with retest readings."""
    a, b = [calibrated['aligned'][key] for key in ('a', 'b')]
    tolerance = calibrated['settings']['pair_tol_mm']
    used_a, used_b = set(), set()
    pairs = []
    for epoch in ('RETEST', 'BASELINE'):
        left = [(i, r) for i, r in enumerate(a) if r['epoch'] == epoch]
        right = [(j, r) for j, r in enumerate(b) if r['epoch'] == epoch]
        indices = best_pairs([r['chain_mm'] for _, r in left], [r['chain_mm'] for _, r in right], tolerance)
        for li, rj in indices:
            i, row_a = left[li]
            j, row_b = right[rj]
            used_a.add(i)
            used_b.add(j)
            x, y = row_a['chain_mm'], row_b['chain_mm']
            candidates = [r['id'] for _, r in right
                          if abs(r['chain_mm'] - x) <= tolerance]
            pairs.append({'pair': f'P{len(pairs)+1:03d}', 'a': row_a, 'b': row_b,
                          'span_mm': abs(x-y), 'midpoint_half_mm': x+y,
                          'possible_b': candidates, 'epoch': epoch,
                          'retest_id': row_a.get('retest_id') if epoch == 'RETEST' else None})
    pairs.sort(key=lambda row: row['midpoint_half_mm'])
    pairs = [dict(row, pair=f'P{index+1:03d}') for index, row in enumerate(pairs)]
    singles = []
    for rows, other, used, opposite in ((a, [r['chain_mm'] for r in b], used_a, 'B'),
                                        (b, [r['chain_mm'] for r in a], used_b, 'A')):
        for i, row in enumerate(rows):
            if i in used:
                continue
            if row['epoch'] == 'SUPERSEDED':
                code = 'SUPERSEDED_BY_RETEST'
            else:
                x = row['chain_mm']
                competing = bisect_left(other, x-tolerance) < bisect_right(other, x+tolerance)
                if row['epoch'] == 'RETEST' and competing:
                    code = 'AWAITING_OPPOSITE_RETEST'
                elif competing:
                    code = 'PAIR_COMPETITION'
                else:
                    code = f'NO_{opposite}_NEARBY'
            singles.append({**row, 'code': code})
    counts = {epoch: sum(1 for row in pairs if row['epoch'] == epoch) for epoch in ('RETEST', 'BASELINE')}
    live = [row for row in a + b if row['epoch'] != 'SUPERSEDED']
    return {'pairs': pairs, 'singles': singles, 'pair_count': len(pairs), 'single_count': len(singles),
            'total_span_mm': sum(r['span_mm'] for r in pairs),
            'retest_pair_count': counts['RETEST'], 'baseline_pair_count': counts['BASELINE'],
            'balanced': len(live) == 2*len(pairs) + len([s for s in singles if s['epoch'] != 'SUPERSEDED'])}
