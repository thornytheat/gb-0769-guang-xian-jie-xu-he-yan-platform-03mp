from app.errors import InspectionError
from app.modules.calibration.contract import setup
from app.modules.calibration.service import calibrate as base_calibrate
from app.modules.trace.service import ingest
from .design import reconcile
from .loss import judge
from .pairs import join
from .service import prepare


def run(material, stage='design'):
    if any(len(text) > 250_000 for text in material['traces'].values()):
        raise InspectionError('TRACE_TOO_LARGE', status=413)
    config = setup(material.get('settings'))
    calibrated = prepare(material, config)
    output = {'retest_calibration': calibrated}
    if stage == 'retest_calibration':
        return output
    joined = join(calibrated)
    output['retest_pairs'] = joined
    if stage == 'retest_pairs':
        return output
    judged = judge(joined, config)
    output['retest_loss'] = judged
    if stage != 'retest_loss':
        # Design points live in A-end coordinates; attach the baseline calibration view.
        design_view = base_calibrate(ingest(material['traces'])['traces'], config)
        calibrated['aligned']['design'] = design_view['aligned']['design']
        output['retest_design'] = reconcile(calibrated, joined, judged)
    return output
