import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.errors import InspectionError
from app.main import create_app
from app.modules.retest.archive import build_ledger
from app.modules.retest.contract import setup

REPAIR = Path(__file__).resolve().parent.parent / 'sample_data' / 'repair'


@pytest.fixture
def repair():
    material = {
        'traces': {key: (REPAIR / f'{key}.csv').read_text(encoding='utf-8')
                   for key in ('a', 'b', 'design')},
        'settings': json.loads((REPAIR / 'link.json').read_text(encoding='utf-8')),
        'retests': json.loads((REPAIR / 'retests.json').read_text(encoding='utf-8')),
    }
    return material


def test_retest_reading_never_couples_with_opposite_baseline(client, repair):
    r = client.post('/api/retest/pairs', json=repair).json
    assert not any(p['a']['epoch'] != p['b']['epoch'] for p in r['pairs'])
    retest_single = next(s for s in r['singles'] if s['id'] == 'RA-04')
    assert retest_single['code'] == 'AWAITING_OPPOSITE_RETEST'
    superseded = next(s for s in r['singles'] if s['id'] == 'A-04')
    assert superseded['code'] == 'SUPERSEDED_BY_RETEST'
    assert r['balanced'] is True


def test_repair_window_joint_waits_for_other_end(client, repair):
    r = client.post('/api/retest/design', json=repair).json
    joint = next(row for row in r['rows'] if row['joint'] == 'F-04')
    assert (joint['code'], joint['bucket'], joint['pair']) == ('RETEST_PENDING', 'missing', None)
    assert joint['retest_scope'] == [{'retest_id': 'RT-A-501-20261122', 'side': 'a',
                                      'start_mm': 480_000, 'end_mm': 520_000}]
    # Joints outside the window still reconcile on the original trace.
    f01 = next(row for row in r['rows'] if row['joint'] == 'F-01')
    assert f01['code'] == 'PASS' and f01['epoch'] == 'BASELINE'
    assert r['retest_pending'] == 1 and r['balanced'] and r['measurements_balanced']


def test_dual_end_retest_confirms_joint_with_lineage(client, repair):
    repair['retests'].append({
        'retest_id': 'RT-B-501-20261122', 'side': 'b',
        'start_distance': 480, 'start_unit': 'm', 'end_distance': 520, 'end_unit': 'm',
        'recorded_at': '2026-11-22T09:10:00+08:00',
        'trace': 'event,distance,unit,loss_db\nRB-04,539,m,0.10\n'})
    r = client.post('/api/retest/design', json=repair).json
    joint = next(row for row in r['rows'] if row['joint'] == 'F-04')
    assert joint['code'] == 'PASS' and joint['bucket'] == 'retest_passed'
    assert joint['evidence'] == [
        {'side': 'a', 'id': 'RA-04', 'line': 2, 'epoch': 'RETEST',
         'retest_id': 'RT-A-501-20261122', 'loss_mdb': 120},
        {'side': 'b', 'id': 'RB-04', 'line': 2, 'epoch': 'RETEST',
         'retest_id': 'RT-B-501-20261122', 'loss_mdb': 100}]
    assert r['retest_reviewed'] == 1


def test_retest_scope_is_its_own_start_and_coverage(client, repair):
    # The new reading sits outside the declared coverage window: flagged, never superseding.
    repair['retests'][0]['trace'] = 'event,distance,unit,loss_db\nRA-FAR,300,m,0.10\n'
    r = client.post('/api/retest/calibration', json=repair).json
    batch = r['batches'][0]
    assert (batch['in_scope'], batch['out_of_scope']) == (0, 1)
    assert batch['out_of_scope_rows'][0]['id'] == 'RA-FAR'
    baseline_a04 = next(row for row in r['aligned']['a'] if row['id'] == 'A-04')
    assert baseline_a04['epoch'] == 'BASELINE'


def test_contract_rejects_bad_retests():
    with pytest.raises(InspectionError, match='RETEST_LIST_REQUIRED'):
        setup([])
    good = {'retest_id': 'R1', 'side': 'a', 'start_distance': 10, 'start_unit': 'm',
            'end_distance': 20, 'end_unit': 'm', 'trace': 'event,distance,unit,loss_db\n'}
    with pytest.raises(InspectionError, match='RETEST_FIELDS'):
        setup([{**good, 'extra': 1}])
    with pytest.raises(InspectionError, match='BAD_RETEST_SIDE'):
        setup([{**good, 'side': 'c'}])
    with pytest.raises(InspectionError, match='BAD_RETEST_RANGE'):
        setup([{**good, 'end_distance': 5}])
    with pytest.raises(InspectionError, match='DUPLICATE_RETEST_ID'):
        setup([good, {**good, 'side': 'b'}])
    with pytest.raises(InspectionError, match='BAD_RETEST_RECORDED_AT'):
        setup([{**good, 'recorded_at': 'not-a-date'}])
    described = setup([{**good, 'recorded_at': '2026-11-22T00:00:00Z'}])
    assert described[0]['recorded_at'].tzinfo is not None


def test_retest_ledger_is_idempotent(client, repair):
    first = client.post('/api/retests', json=repair)
    retry = client.post('/api/retests', json=repair)
    assert (first.status_code, retry.status_code, retry.json['created']) == (201, 200, False)
    assert first.json['record'] == retry.json['record']
    listing = client.get('/api/retests').json['retests']
    assert len(listing) == 1 and listing[0]['state'] == 'CONFIRMED'


def test_confirmed_retest_cannot_be_overwritten(client, repair):
    client.post('/api/retests', json=repair)
    tampered = copy.deepcopy(repair)
    tampered['retests'][0]['trace'] = tampered['retests'][0]['trace'].replace('0.12', '0.18')
    conflict = client.post('/api/retests', json=tampered)
    assert (conflict.status_code, conflict.json['code']) == (409, 'RETEST_CONFLICT')
    # Original confirmed record is untouched.
    record = client.get('/api/retests/' + repair['retests'][0]['retest_id']).json
    assert record['batches'][0]['trace_sha256']
    assert record['state'] == 'CONFIRMED'
    assert client.get('/api/retests').json['retests'][0]['retest_id'] == repair['retests'][0]['retest_id']


def test_late_old_measurement_does_not_replace_confirmed(repair, tmp_path):
    db = tmp_path / 'retest.sqlite'
    first = create_app(db).test_client().post('/api/retests', json=repair).json
    # An older record (earlier recorded_at) arriving afterwards with the same id but new payload.
    late = copy.deepcopy(repair)
    late['retests'][0]['recorded_at'] = '2020-01-01T00:00:00+00:00'
    late['retests'][0]['trace'] = late['retests'][0]['trace'].replace('0.12', '0.30')
    response = create_app(db).test_client().post('/api/retests', json=late)
    assert response.status_code == 409
    restored = create_app(db).test_client().get('/api/retests/' + first['retest_id']).json
    assert restored == first['record']


def test_competing_workers_publish_retest_once(tmp_path, repair):
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda _: build_ledger(tmp_path / 'r.db', repair), range(10)))
    assert sum(fresh for _, fresh in results) == 1
    assert len({r['retest_id'] for r, _ in results}) == 1


def test_ledger_keeps_per_batch_fingerprints(client, repair):
    r = client.post('/api/retests', json=repair).json['record']
    batch = r['batches'][0]
    assert set(batch) == {'retest_id', 'side', 'scope_mm', 'recorded_at', 'trace_sha256',
                          'in_scope', 'out_of_scope', 'isolated'}
    assert batch['scope_mm'] == [480_000, 520_000]
    assert r['pending_joints'] == ['F-04'] and r['reviewed_joints'] == []


def test_unknown_retest_returns_404(client):
    r = client.get('/api/retests/missing')
    assert (r.status_code, r.json['code']) == (404, 'RETEST_NOT_FOUND')


def test_baseline_pipeline_unchanged_without_retests(client):
    r = client.post('/api/design', json={'sample': 'dirty'})
    assert r.status_code == 200 and r.json['missing'] == 2
