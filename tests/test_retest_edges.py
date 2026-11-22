import copy
import json
from pathlib import Path

REPAIR = Path(__file__).resolve().parent.parent / 'sample_data' / 'repair'


def make():
    return {
        'traces': {key: (REPAIR / f'{key}.csv').read_text(encoding='utf-8')
                   for key in ('a', 'b', 'design')},
        'settings': json.loads((REPAIR / 'link.json').read_text(encoding='utf-8')),
        'retests': json.loads((REPAIR / 'retests.json').read_text(encoding='utf-8')),
    }


def test_retest_isolated_rows_are_kept(client):
    material = make()
    material['retests'][0]['trace'] += 'RA-BAD,601,m,N/A\n'
    r = client.post('/api/retest/calibration', json=material).json
    issue = next(row for row in r['retest_isolated'] if row.get('retest_id'))
    assert issue['code'] == 'MISSING_SENTINEL' and issue['retest_id'] == 'RT-A-501-20261122'
    # The valid in-scope reading still lands and still awaits the other end.
    batch = r['batches'][0]
    assert batch['in_scope'] == 1 and batch['isolated'] == 1


def test_superseded_baseline_returns_when_retest_has_no_in_scope_reading(client):
    material = make()
    material['retests'][0]['trace'] = 'event,distance,unit,loss_db\nRA-FAR,300,m,0.10\n'
    r = client.post('/api/retest/pairs', json=material).json
    # No in-scope retest reading: A-04 stays baseline and keeps its original pairing.
    paired_a04 = next(p for p in r['pairs'] if p['a']['id'] == 'A-04')
    assert paired_a04['epoch'] == 'BASELINE' and paired_a04['b']['id'] == 'B-04'
    assert not any(s['id'] == 'A-04' and s['code'] == 'SUPERSEDED_BY_RETEST' for s in r['singles'])
    far = next(s for s in r['singles'] if s['id'] == 'RA-FAR')
    assert far['code'] == 'NO_B_NEARBY'


def test_retest_over_limit_is_bucketed_separately(client):
    material = make()
    material['retests'].append({
        'retest_id': 'RT-B-501', 'side': 'b',
        'start_distance': 480, 'start_unit': 'm', 'end_distance': 520, 'end_unit': 'm',
        'trace': 'event,distance,unit,loss_db\nRB-04,539,m,0.90\n'})
    r = client.post('/api/retest/design', json=material).json
    joint = next(row for row in r['rows'] if row['joint'] == 'F-04')
    assert joint['code'] == 'OVER_LIMIT' and joint['bucket'] == 'retest_over_limit'
    assert r['retest_over_limit'] == 1


def test_retest_net_gain_is_invalid_not_pass(client):
    material = make()
    material['retests'][0]['trace'] = 'event,distance,unit,loss_db\nRA-04,601,m,-0.40\n'
    material['retests'].append({
        'retest_id': 'RT-B-501', 'side': 'b',
        'start_distance': 480, 'start_unit': 'm', 'end_distance': 520, 'end_unit': 'm',
        'trace': 'event,distance,unit,loss_db\nRB-04,539,m,0.01\n'})
    r = client.post('/api/retest/design', json=material).json
    joint = next(row for row in r['rows'] if row['joint'] == 'F-04')
    assert joint['code'] == 'INVALID_NET_GAIN' and joint['bucket'] == 'missing'


def test_two_side_retest_scope_marks_partial_when_only_one_reading_pair_possible(client):
    # Both sides declare coverage, but B retest reading falls outside its own window.
    material = make()
    material['retests'].append({
        'retest_id': 'RT-B-501', 'side': 'b',
        'start_distance': 480, 'start_unit': 'm', 'end_distance': 520, 'end_unit': 'm',
        'trace': 'event,distance,unit,loss_db\nRB-FAR,200,m,0.10\n'})
    r = client.post('/api/retest/design', json=material).json
    joint = next(row for row in r['rows'] if row['joint'] == 'F-04')
    assert joint['code'] == 'RETEST_PARTIAL_PAIR'
    assert {s['side'] for s in joint['retest_scope']} == {'a', 'b'}


def test_original_trace_joins_outside_retest_window_are_untouched(client):
    r = client.post('/api/retest/design', json=make()).json
    outside = [row for row in r['rows'] if row['joint'] != 'F-04']
    assert all(row['epoch'] in ('BASELINE', None) for row in outside)
    paired = [row for row in outside if row['pair']]
    assert all(e['epoch'] == 'BASELINE' for row in paired for e in row['evidence'])


def test_retest_pipeline_requires_trace_text(client):
    material = make()
    material['retests'][0]['trace'] = 5
    response = client.post('/api/retest/calibration', json=material)
    assert (response.status_code, response.json['code']) == (422, 'TRACE_TEXT_REQUIRED')
