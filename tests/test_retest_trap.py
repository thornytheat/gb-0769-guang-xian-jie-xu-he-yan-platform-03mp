"""Trap: a repaired end's new reading must never be coupled with the opposite
end's old reading, otherwise the repaired joint could be falsely marked PASS."""
import json
from pathlib import Path


def _material(a_trace, b_trace, retests):
    repair = Path(__file__).resolve().parent.parent / 'sample_data' / 'repair'
    return {
        'traces': {'a': a_trace, 'b': b_trace,
                   'design': (repair / 'design.csv').read_text(encoding='utf-8')},
        'settings': json.loads((repair / 'link.json').read_text(encoding='utf-8')),
        'retests': retests,
    }


HEADER = 'event,distance,unit,loss_db\n'


def test_old_opposite_reading_cannot_make_repair_pass(client):
    # Baseline: A-04 reads a failing 0.50 dB, B-04 reads 0.10 dB (old).
    a = HEADER + 'A-04,600,m,0.50\nA-01,200,m,0.05\n'
    b = HEADER + 'B-04,539,m,0.10\nB-01,943,m,0.05\n'
    # Repair replaces only the A end with a good reading inside 480-520 m chain window.
    retests = [{
        'retest_id': 'RT-A-F04', 'side': 'a',
        'start_distance': 480, 'start_unit': 'm', 'end_distance': 520, 'end_unit': 'm',
        'trace': HEADER + 'RA-04,601,m,0.05\n'}]
    material = _material(a, b, retests)
    design = client.post('/api/retest/design', json=material).json
    joint = next(row for row in design['rows'] if row['joint'] == 'F-04')
    # The tempting but forbidden 0.075 dB "pair" must not produce PASS.
    assert joint['code'] == 'RETEST_PENDING' and joint['pair'] is None
    assert joint['bucket'] == 'missing'
    pairs = client.post('/api/retest/pairs', json=material).json['pairs']
    assert not any(p['a']['id'] == 'RA-04' and p['b']['id'] == 'B-04' for p in pairs)
    # And no cross-epoch pair of any kind exists.
    assert all(p['a']['epoch'] == p['b']['epoch'] for p in pairs)


def test_repair_passes_only_after_both_ends_retested(client):
    a = HEADER + 'A-04,600,m,0.50\n'
    b = HEADER + 'B-04,539,m,0.10\n'
    retests = [
        {'retest_id': 'RT-A-F04', 'side': 'a', 'start_distance': 480, 'start_unit': 'm',
         'end_distance': 520, 'end_unit': 'm', 'trace': HEADER + 'RA-04,601,m,0.05\n'},
        {'retest_id': 'RT-B-F04', 'side': 'b', 'start_distance': 480, 'start_unit': 'm',
         'end_distance': 520, 'end_unit': 'm', 'trace': HEADER + 'RB-04,539,m,0.06\n'},
    ]
    design = client.post('/api/retest/design', json=_material(a, b, retests)).json
    joint = next(row for row in design['rows'] if row['joint'] == 'F-04')
    assert joint['code'] == 'PASS' and joint['bucket'] == 'retest_passed'
    assert {e['retest_id'] for e in joint['evidence']} == {'RT-A-F04', 'RT-B-F04'}
    assert all(e['epoch'] == 'RETEST' for e in joint['evidence'])


def test_audit_trail_names_the_exact_measurement_for_every_segment(client):
    a = HEADER + 'A-01,200,m,0.05\nA-04,600,m,0.50\n'
    b = HEADER + 'B-01,943,m,0.05\nB-04,539,m,0.10\n'
    retests = [{'retest_id': 'RT-A-F04', 'side': 'a', 'start_distance': 480, 'start_unit': 'm',
                'end_distance': 520, 'end_unit': 'm', 'trace': HEADER + 'RA-04,601,m,0.05\n'}]
    design = client.post('/api/retest/design', json=_material(a, b, retests)).json
    by_joint = {row['joint']: row for row in design['rows']}
    # Baseline joint keeps baseline lineage.
    f01 = by_joint['F-01']
    assert f01['evidence'] and all(e['epoch'] == 'BASELINE' and e['retest_id'] is None
                                   for e in f01['evidence'])
    # Repaired-window joint records which retest batch covers it even before confirmation.
    f04 = by_joint['F-04']
    assert f04['retest_scope'][0]['retest_id'] == 'RT-A-F04'
    ledger = client.post('/api/retests', json=_material(a, b, retests)).json['record']
    assert ledger['batches'][0]['trace_sha256'] and ledger['pending_joints'] == ['F-04']
