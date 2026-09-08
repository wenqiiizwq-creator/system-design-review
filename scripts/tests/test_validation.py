import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from check_requirements import check as requirements
from check_power_tree import check as power
from validate_design import check as design, approval_digest
from inventory_package import inventory

FIXTURES = Path(__file__).parent / 'fixtures'


def good():
    return json.loads((FIXTURES / 'sample_good.json').read_text())


def complete():
    return json.loads((ROOT.parent / 'examples/design-intent-v2.json').read_text())


def approve(data, scope):
    data['approvals'].append({'actor': 'synthetic reviewer', 'source_id': 'S3', 'locator': 'synthetic §1',
                              'baseline_version': data['baseline_version'], 'scope': scope,
                              'content_digest': approval_digest(data, scope), 'decision': 'accepted'})


class RequirementTests(unittest.TestCase):
    def test_good_and_bad(self):
        self.assertTrue(requirements(good())['policy_pass'])
        self.assertFalse(requirements(json.loads((FIXTURES/'sample_bad.json').read_text()))['policy_pass'])

    def test_missing_source(self):
        d=good(); d['requirements'][0].pop('source')
        self.assertFalse(requirements(d)['validation_ok'])

    def test_null_and_nonstring_fields(self):
        for key in ('id','text','source','covered_by','verify_method'):
            for value in (None, True, [], {}, 4):
                with self.subTest(key=key, value=value):
                    d=good(); d['requirements'][0][key]=value
                    self.assertFalse(requirements(d)['validation_ok'])

    def test_missing_coverage(self):
        d=good(); d['requirements'][0]['covered_by']=''
        self.assertTrue(requirements(d)['validation_ok'])
        self.assertFalse(requirements(d)['policy_pass'])

    def test_duplicate_id(self):
        d=good(); d['requirements'][1]['id']=d['requirements'][0]['id']
        self.assertFalse(requirements(d)['validation_ok'])

    def test_open_and_assumed_not_confirmed(self):
        for status in ('open','assumed'):
            d=good(); d['requirements'][0]['status']=status
            r=requirements(d)
            self.assertEqual(r['completeness'],'INCOMPLETE')
            self.assertFalse(r['ok'])

    def test_unknown_status_and_container(self):
        for value in ('other',[],None,{}):
            d=good(); d['requirements'][0]['status']=value
            self.assertFalse(requirements(d)['validation_ok'])
        for value in (None,{},[],[None]):
            self.assertFalse(requirements({'requirements':value})['policy_pass'])


class PowerTests(unittest.TestCase):
    def mutate(self, **fields):
        d=good(); d['power_tree']['rails'][0]['loads']=[{'consumer':'load',**fields}]
        return power(d,fail_on_warn=True)

    def test_good_and_bad(self):
        self.assertTrue(power(good(),fail_on_warn=True)['policy_pass'])
        self.assertFalse(power(json.loads((FIXTURES/'sample_bad.json').read_text()))['policy_pass'])

    def test_all_currents_unknown(self):
        r=self.mutate(status='open')
        self.assertFalse(r['ok']); self.assertEqual(r['rails'][0]['status'],'INSUFFICIENT')
        self.assertEqual(r['rails'][0]['known_load_a'],0)
        self.assertIsNone(r['rails'][0]['margin_pct'])

    def test_partial_overload_is_fail(self):
        d=good(); d['power_tree']['rails'][0]['loads']=[{'consumer':'known','current':5},{'consumer':'unknown','status':'open'}]
        r=power(d)
        self.assertEqual(r['rails'][0]['status'],'FAIL')
        self.assertTrue(r['insufficient']); self.assertTrue(r['fails'])

    def test_invalid_numeric_currents(self):
        for value in (-1,True,False,float('inf'),float('nan'),10**500,{},'0.5'):
            with self.subTest(value=str(value)[:20]):
                r=self.mutate(current=value)
                self.assertFalse(r['validation_ok']); self.assertFalse(r['policy_pass'])

    def test_sum_overflow(self):
        d=good(); d['power_tree']['rails'][0]['loads']=[{'consumer':'a','current':1e308},{'consumer':'b','current':1e308}]
        self.assertFalse(power(d)['validation_ok'])

    def test_zero_load_is_valid(self):
        r=self.mutate(current=0)
        self.assertEqual(r['rails'][0]['margin_pct'],100)
        self.assertTrue(r['policy_pass'])

    def test_assumed_and_invalid_status(self):
        self.assertFalse(self.mutate(current=1,status='assumed')['policy_pass'])
        for status in ('invalid',None,[],{}):
            self.assertFalse(self.mutate(current=1,status=status)['validation_ok'])

    def test_bad_inputs_sources_and_ratings(self):
        for value in ([{}], [], None, [True]):
            d=good(); d['power_tree']['inputs']=value
            self.assertFalse(power(d)['validation_ok'])
        for key in ('source','voltage','rated_imax'):
            d=good(); d['power_tree']['rails'][0][key]=True
            self.assertFalse(power(d)['validation_ok'])

    def test_unknown_ratings_are_insufficient_not_fake_numbers(self):
        for key, field in (('inputs','imax'),('rails','rated_imax'),('rails','voltage')):
            d=good(); d['power_tree'][key][0][field]=None
            r=power(d)
            self.assertTrue(r['validation_ok'])
            self.assertFalse(r['policy_pass'])
            self.assertEqual(r['completeness'],'INCOMPLETE')

    def test_duplicate_ids_across_inputs_and_rails(self):
        d=good(); d['power_tree']['inputs'][0]['id']='V12V0'
        self.assertFalse(power(d)['validation_ok'])

    def test_unknown_dependencies(self):
        for field in ('sequence_after','upstream_id'):
            d=good(); d['power_tree']['rails'][0][field]='missing'
            self.assertFalse(power(d)['validation_ok'])

    def test_cyclic_dependencies(self):
        for field in ('sequence_after','upstream_id'):
            d=good(); a,b=d['power_tree']['rails'][:2]
            a[field]=b['id']; b[field]=a['id']
            self.assertFalse(power(d)['validation_ok'])

    def test_sequence_duplicate_order_rail_and_boolean(self):
        for seq in ([{'rail':'V12V0','order':1},{'rail':'V12V0','order':2}],
                    [{'rail':'V12V0','order':True}], [{'rail':[],'order':1}], {},
                    [{'rail':'V12V0','order':1},{'rail':'V5V0','order':1}]):
            d=good(); d['power_tree']['sequence']=seq
            self.assertFalse(power(d)['validation_ok'])

    def test_sequence_conflicts_with_dependency(self):
        d=good(); d['power_tree']['rails'][0]['sequence_after']='V5V0'
        self.assertFalse(power(d)['validation_ok'])

    def test_margin_boundary_and_strict_mode(self):
        d=good(); d['power_tree']['rails'][0]['loads'][0]['current']=3.2
        self.assertTrue(power(d,fail_on_warn=True)['policy_pass'])
        d['power_tree']['rails'][0]['loads'][0]['current']=3.3
        self.assertTrue(power(d)['policy_pass'])
        self.assertFalse(power(d,fail_on_warn=True)['ok'])
        for margin in (float('nan'),float('inf'),-1,100,True):
            self.assertFalse(power(d,min_margin=margin)['validation_ok'])


class GateTests(unittest.TestCase):
    def test_complete_fixture(self):
        r=design(complete())
        self.assertTrue(r['validation_ok'],r)
        self.assertTrue(r['freeze_allowed'],r)

    def test_legacy_never_freezes(self):
        self.assertFalse(design(good())['freeze_allowed'])
        self.assertFalse(requirements(good())['freeze_allowed'])
        self.assertFalse(power(good())['freeze_allowed'])

    def test_missing_collections(self):
        d=complete()
        for key in ('sources','evidence','requirements','modules','states','review_plan','checks','approvals','power_budgets'):
            with self.subTest(key=key):
                altered=copy.deepcopy(d); altered.pop(key)
                self.assertFalse(design(altered)['freeze_allowed'])

    def test_missing_attachment_and_unclassified_source(self):
        for field,value in (('read_status','missing'),('read_status','partial'),('role','unclassified'),('revision','unknown')):
            d=complete(); d['sources'][0][field]=value
            self.assertFalse(design(d)['freeze_allowed'])

    def test_optional_exclusion_requires_reason(self):
        d=complete(); d['sources'].append({'id':'OLD','locator':'old.md','revision':'old','role':'design','required':False,'read_status':'unread'})
        self.assertFalse(design(d)['validation_ok'])
        d['sources'][-1]['exclusion_reason']='另一产品型号，与当前基线不相关'
        self.assertTrue(design(d)['freeze_allowed'])

    def test_unknown_evidence_reference(self):
        d=complete(); d['requirements'][0]['evidence_ids']=['MISSING']
        self.assertFalse(design(d)['validation_ok'])

    def test_unverified_and_low_confidence(self):
        for field,value in (('status','unverified'),('confidence','C')):
            d=complete(); d['evidence'][0][field]=value
            self.assertFalse(design(d)['freeze_allowed'])

    def test_confidence_cannot_be_promoted(self):
        d=complete(); d['checks'][0]['confidence']='A'
        self.assertFalse(design(d)['validation_ok'])

    def test_missing_check_and_layer(self):
        d=complete(); d['checks'].pop()
        self.assertFalse(design(d)['freeze_allowed'])
        d=complete(); d['review_plan'].pop(); d['checks'].pop()
        self.assertFalse(design(d)['freeze_allowed'])

    def test_known_object_not_in_plan(self):
        d=complete(); d['states'].append({'id':'RESET','name':'reset','behavior':'off','evidence_ids':['E1']})
        r=design(d)
        self.assertTrue(any('state:RESET' in x for x in r['insufficient']))

    def test_duplicate_or_unknown_checks(self):
        d=complete(); d['checks'].append(copy.deepcopy(d['checks'][0]))
        self.assertFalse(design(d)['validation_ok'])
        d=complete(); d['checks'][0]['plan_id']='unknown'
        self.assertFalse(design(d)['validation_ok'])

    def test_na_must_match_applicability(self):
        d=complete(); d['checks'][0]['result']='NA'
        self.assertFalse(design(d)['validation_ok'])

    def test_confirmed_requirement_cannot_be_skipped_as_na(self):
        d=complete(); d['review_plan'][0]['applicability']='NA'; d['checks'][0]['result']='NA'
        self.assertFalse(design(d)['validation_ok'])

    def test_legacy_incomplete_fixture_stays_incomplete(self):
        d=json.loads((FIXTURES/'sample_incomplete.json').read_text())
        self.assertFalse(requirements(d)['policy_pass'])
        self.assertFalse(power(d)['policy_pass'])

    def test_critical_fail_not_accepted_by_confirmation(self):
        d=complete(); d['checks'][0]['result']='FAIL'
        approve(d,['risk:C0'])
        self.assertFalse(design(d)['freeze_allowed'])

    def test_no_critical_downgrade(self):
        d=complete(); d['review_plan'][0]['critical']=False
        self.assertFalse(design(d)['validation_ok'])

    def test_noncritical_risk_requires_explicit_scope(self):
        d=complete(); d['review_plan'][1]['critical']=False; d['checks'][1]['result']='FAIL'
        approve(d,['baseline'])
        self.assertFalse(design(d)['freeze_allowed'])
        d['approvals'].pop(); approve(d,['risk:C1'])
        r=design(d)
        self.assertTrue(r['freeze_allowed'],r)
        self.assertTrue(r['warns'])
        self.assertEqual(d['checks'][1]['result'],'FAIL')

    def test_unconfirmed_or_rejected_intent(self):
        d=complete(); d['approvals']=[]
        self.assertFalse(design(d)['freeze_allowed'])
        d=complete(); d['approvals'][0]['decision']='rejected'
        self.assertFalse(design(d)['freeze_allowed'])

    def test_stale_version_and_content(self):
        d=complete(); d['baseline_version']='2'
        self.assertFalse(design(d)['freeze_allowed'])
        d=complete(); d['requirements'][0]['text']='changed target'
        self.assertFalse(design(d)['freeze_allowed'])

    def test_unrelated_check_does_not_invalidate_scoped_intent(self):
        d=complete(); d['checks'][1]['rationale']='new independent evidence explanation'
        self.assertTrue(design(d)['freeze_allowed'])

    def test_approval_requires_provenance(self):
        d=complete(); d['approvals'][0]['source_id']='S2'
        self.assertFalse(design(d)['validation_ok'])

    def test_missing_budget_or_upstream(self):
        d=complete(); d['power_budgets']=[]
        self.assertFalse(design(d)['freeze_allowed'])
        d=complete(); d['power_tree']['rails'][0].pop('upstream_id')
        self.assertFalse(design(d)['freeze_allowed'])

    def test_unknown_mpn_and_interface_role(self):
        d=complete(); d['components'][0]['identity_status']='open'
        self.assertFalse(design(d)['freeze_allowed'])
        d=complete(); d['interfaces'][0]['ends'][0].pop('role')
        self.assertFalse(design(d)['validation_ok'])

    def test_insufficient_cannot_be_waived(self):
        d=complete(); d['checks'][1].update(result='INSUFFICIENT',confidence='C',evidence_ids=[])
        approve(d,['risk:C1'])
        self.assertFalse(design(d)['freeze_allowed'])

    def test_handoff_requires_recipient_and_acceptance(self):
        d=complete(); d['handoffs']=[{'id':'H1','required':True,'state':'ACCEPTED','receivers':['test team'],
                                    'constraint':'Measure startup sequence','verification':'captured waveform'}]
        self.assertFalse(design(d)['freeze_allowed'])
        approve(d,['handoff:H1'])
        self.assertTrue(design(d)['freeze_allowed'])
        d['handoffs'][0]['receivers']=[]
        self.assertFalse(design(d)['validation_ok'])

    def test_critical_issue_cannot_be_accepted(self):
        d=complete(); d['open_issues']=[{'id':'O1','critical':True,'status':'ACCEPTED','description':'missing fault model'}]
        approve(d,['issue:O1'])
        self.assertFalse(design(d)['freeze_allowed'])

    def test_optimization_must_have_tradeoffs_and_decision(self):
        d=complete(); d['optimizations']=[{'id':'O1','objective':'reduce loss','baseline':'current','recommendation':'alternative','decision_id':'D1','candidates':[{},{}]}]
        self.assertFalse(design(d)['validation_ok'])

    def test_malformed_optional_fields_do_not_crash(self):
        for group in ('sources','components','interfaces','states','decisions','observations','checks','approvals','open_issues','handoffs','optimizations'):
            for value in (None,{},[None],[{}]):
                with self.subTest(group=group,value=value):
                    d=complete(); d[group]=value
                    self.assertFalse(design(d)['freeze_allowed'])


class CliAndInventoryTests(unittest.TestCase):
    def cli(self, script, data=None, flags=(), raw=None):
        with tempfile.TemporaryDirectory() as folder:
            inp=Path(folder)/'input.json'; out=Path(folder)/'result.json'
            inp.write_text(raw if raw is not None else json.dumps(data))
            p=subprocess.run([sys.executable,str(ROOT/script),str(inp),*flags,'--json',str(out)],capture_output=True,text=True)
            return p,json.loads(out.read_text())

    def test_cli_strict_results_agree(self):
        d=good(); d['requirements'][0]['status']='open'
        p,r=self.cli('check_requirements.py',d,('--fail-on-open',))
        self.assertEqual(p.returncode,1); self.assertFalse(r['ok'])
        d=good(); d['power_tree']['rails'][0]['loads'][0]['current']=3.9
        p,r=self.cli('check_power_tree.py',d,('--fail-on-warn',))
        self.assertEqual(p.returncode,1); self.assertFalse(r['ok'])

    def test_invalid_json_returns_structured_error(self):
        for raw in ('{broken', '[1]', '{"x": NaN}', '{"x": Infinity}'):
            p,r=self.cli('validate_design.py',raw=raw)
            self.assertEqual(p.returncode,2,p.stderr)
            self.assertFalse(r['freeze_allowed'])

    def test_cli_complete_and_incomplete(self):
        p,r=self.cli('validate_design.py',complete())
        self.assertEqual(p.returncode,0); self.assertTrue(r['freeze_allowed'])
        d=complete(); d['approvals']=[]
        p,r=self.cli('validate_design.py',d)
        self.assertEqual(p.returncode,1); self.assertFalse(r['freeze_allowed'])

    def test_inventory_never_claims_content_read(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder); (p/'需求.md').write_text('requirement')
            (p/'report.json').write_text('old output')
            (p/'.git').mkdir(); (p/'.git'/'private').write_text('not a source')
            (p/'linked').symlink_to(p/'需求.md')
            r=inventory(p,p/'report.json')
            self.assertEqual(r['routing'],'UNDETERMINED')
            self.assertEqual(len(r['sources']),2)
            self.assertEqual({s['read_status'] for s in r['sources']},{'error','unread'})
            self.assertTrue(all(s['role']=='unclassified' for s in r['sources']))
            before=r['sources']
            (p/'需求.md').write_text('changed')
            after=inventory(p,p/'report.json')['sources']
            a=next(x for x in before if x['locator']=='需求.md'); b=next(x for x in after if x['locator']=='需求.md')
            self.assertEqual(a['id'],b['id']); self.assertNotEqual(a['sha256'],b['sha256'])


if __name__=='__main__':
    unittest.main()
