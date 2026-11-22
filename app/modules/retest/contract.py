from datetime import datetime

from app.errors import InspectionError
from app.modules.trace.units import distance

RETEST_FIELDS = ('retest_id', 'side', 'start_distance', 'start_unit', 'end_distance', 'end_unit', 'trace')
OPTIONAL_FIELDS = ('recorded_at',)
SIDES = ('a', 'b')


def parse_recorded_at(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise InspectionError('BAD_RETEST_RECORDED_AT')
    text = value.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise InspectionError('BAD_RETEST_RECORDED_AT') from None


def describe(item, index):
    if not isinstance(item, dict):
        raise InspectionError('RETEST_OBJECT_REQUIRED')
    missing = set(RETEST_FIELDS) - set(item)
    unknown = set(item) - set(RETEST_FIELDS) - set(OPTIONAL_FIELDS)
    if missing or unknown:
        raise InspectionError('RETEST_FIELDS')
    identity = item['retest_id']
    if not isinstance(identity, str) or not identity.strip():
        raise InspectionError('BAD_RETEST_ID')
    side = item['side']
    if side not in SIDES:
        raise InspectionError('BAD_RETEST_SIDE')
    try:
        start_mm = distance(str(item['start_distance']), item['start_unit'])
        end_mm = distance(str(item['end_distance']), item['end_unit'])
    except ValueError:
        raise InspectionError('BAD_RETEST_RANGE') from None
    if end_mm < start_mm:
        raise InspectionError('BAD_RETEST_RANGE')
    trace = item['trace']
    if not isinstance(trace, str):
        raise InspectionError('TRACE_TEXT_REQUIRED')
    if len(trace) > 250_000:
        raise InspectionError('TRACE_TOO_LARGE', status=413)
    recorded_at = parse_recorded_at(item.get('recorded_at'))
    return {'retest_id': identity.strip(), 'side': side, 'start_mm': start_mm, 'end_mm': end_mm,
            'trace': trace, 'recorded_at': recorded_at, 'index': index}


def setup(retests):
    if retests is None:
        return []
    if not isinstance(retests, list) or not retests:
        raise InspectionError('RETEST_LIST_REQUIRED')
    described = [describe(item, index) for index, item in enumerate(retests)]
    identifiers = [item['retest_id'] for item in described]
    if len(set(identifiers)) != len(identifiers):
        raise InspectionError('DUPLICATE_RETEST_ID')
    return described
