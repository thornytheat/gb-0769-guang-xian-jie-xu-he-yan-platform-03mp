from flask import Blueprint, current_app, jsonify

from .input import request_material
from .modules.archive.service import archive
from .modules.archive.storage import get, recent
from .modules.certificate.service import certify
from .modules.retest.archive import build_ledger
from .modules.retest.storage import ledger_document, ledger_recent
from .modules.retest.pipeline import run as run_retest
from .pipeline import run

api = Blueprint('fiber_api', __name__, url_prefix='/api')


def calculate(stage):
    return run(request_material(), stage)[stage]


def calculate_retest(stage):
    return run_retest(request_material(), stage)[stage]


@api.post('/trace')
def trace():
    return calculate('trace')


@api.post('/calibration')
def calibration():
    return calculate('calibration')


@api.post('/pairs')
def pairs():
    return calculate('pairs')


@api.post('/loss')
def loss():
    return calculate('loss')


@api.post('/design')
def design():
    return calculate('design')


@api.post('/retest/calibration')
def retest_calibration():
    return calculate_retest('retest_calibration')


@api.post('/retest/pairs')
def retest_pairs():
    return calculate_retest('retest_pairs')


@api.post('/retest/loss')
def retest_loss():
    return calculate_retest('retest_loss')


@api.post('/retest/design')
def retest_design():
    return calculate_retest('retest_design')


@api.post('/retests')
def submit_retest():
    ledger, fresh = build_ledger(current_app.config['DATABASE'], request_material())
    return {'retest_id': ledger['retest_id'], 'created': fresh, 'record': ledger}, 201 if fresh else 200


@api.get('/retests')
def list_retests():
    return {'retests': ledger_recent(current_app.config['DATABASE'])}


@api.get('/retests/<identifier>')
def retest_item(identifier):
    return ledger_document(current_app.config['DATABASE'], identifier)


@api.post('/inspections')
def submit():
    report, fresh = archive(current_app.config['DATABASE'], request_material())
    return {'inspection_id':report['inspection_id'], 'created':fresh, 'record':report}, 201 if fresh else 200


@api.get('/inspections')
def list_inspections():
    return {'inspections':recent(current_app.config['DATABASE'])}


@api.get('/inspections/<identifier>')
def inspection(identifier):
    return get(current_app.config['DATABASE'], identifier)


@api.get('/certificate/<identifier>')
def certificate(identifier):
    return certify(inspection(identifier))


@api.get('/export/<identifier>')
def export(identifier):
    response = jsonify(certificate(identifier))
    response.headers['Content-Disposition'] = f'attachment; filename="splice-{identifier[:12]}.json"'
    return response
