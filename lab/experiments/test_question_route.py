"""Actual SDK owner routing preserves scope and fails closed on missing facts."""

import copy
import json
from pathlib import Path
import shlex
from unittest.mock import patch

import test_our_v0
from test_sdk_workflows import SdkFixture, ROOT
from test_roadmap import context
from app_server_harness import sse, ev_response_created, ev_function_call, ev_completed
from workflows.interaction_policy import InteractionPolicy
from workflows.our_v0 import question_proposal


class QuestionRouteTest(SdkFixture):
    def manifest(self):
        manifest = test_our_v0.OurV0Test.manifest(self)
        manifest['trials'][0]['fixture'] = 'py-retention-owner'
        manifest['sdk_runtime'].update(interaction_policy='delegated-task-v1', task_directories={'py-retention-owner': 'sentinels/py-retention-owner'})
        return manifest

    def execute(self, manifest):
        return test_our_v0.OurV0Test.execute(self, manifest)

    def plan(self):
        return dict(**context('Return the retained records', 'Preserve all fields and record order.'), open_questions=[{'question': 'What is the retention policy?', 'impact': 'Resolve the missing policy; do not add export.'}], increments=[dict(id='retention', intent='Implement the authorized retention filter.', acceptance=['Retain the records required by the owner policy.'], depends_on=[], requirement_ids=['r-outcome'])])

    def planner_workers(self, manifest):
        events = [json.loads(line) for line in (Path(manifest['output']) / 'runs/trial-0001/session/session.jsonl').read_text().splitlines()]
        return [row['worker_id'] for row in events if row['type'] == 'worker_started']

    def test_answered_policy_preserves_original_scope_in_two_fresh_builders(self):
        manifest = self.manifest()
        initial = self.plan()
        self.response(json.dumps(initial))
        answer = json.loads((ROOT / 'lab/tasks/sentinels/py-retention-owner/private/policy.json').read_text())['owner_facts'][0]['answer']
        revised = copy.deepcopy(initial)
        revised['open_questions'] = []
        revised['requirements'].append(dict(id='r-policy', source_quote=answer, acceptance=['Apply exactly the supplied retention policy.']))
        revised['increments'][0]['requirement_ids'].append('r-policy')
        revised['increments'].append(dict(id='compatibility', intent='Verify compatibility and retained metadata.', acceptance=['Fields and ordering remain unchanged.'], depends_on=['retention'], requirement_ids=['r-outcome', 'r-policy']))
        self.response(json.dumps(revised))
        source = (ROOT / 'lab/tasks/sentinels/py-retention-owner/solution/src/app.py').read_text()
        script = "from pathlib import Path; Path('src/app.py').write_text(" + repr(source) + ')'
        self.mock.enqueue_sse(sse([ev_response_created('write'), ev_function_call('write', 'exec_command', json.dumps({'cmd': 'python3 -c ' + shlex.quote(script)})), ev_completed('write')]))
        self.response('Retention implemented')
        self.response(json.dumps({'findings': [], 'discoveries': []}))
        self.response('Compatibility verified')
        self.response(json.dumps({'findings': [], 'discoveries': []}))
        result = self.execute(manifest)
        self.assertIs(result['task_success'], True, result)
        evidence = result['workflow_result']['evidence']
        dispatch = evidence['our_dispatch']
        self.assertEqual(dispatch['recipe_status'], 'completed')
        self.assertEqual(dispatch['repairs'], 0)
        self.assertEqual(len(dispatch['owner_batches']), 1)
        self.assertEqual(json.loads(dispatch['question_turns'][0]['text'])['open_questions'][0]['impact'], initial['open_questions'][0]['impact'])
        root = Path(manifest['output']) / 'runs/trial-0001'
        roadmap = json.loads((root / 'roadmap-2/roadmap.json').read_text())
        self.assertEqual(roadmap['requirements'][0], initial['requirements'][0])
        self.assertIn(answer, roadmap['owner_followups'][0])
        self.assertNotIn('do not add export', roadmap['owner_followups'][0])
        invocations = [json.loads(line) for line in (root / 'session/invocations.jsonl').read_text().splitlines()]
        builders = [row for row in invocations if row['type'] == 'turn_prompt' and row['worker_id'].startswith('builder-')]
        self.assertEqual(len({row['worker_id'] for row in builders}), 2)
        self.assertTrue(all(answer in row['prompt'] for row in builders))
        self.assertEqual(len(self.mock.requests()), 7)
        self.assertEqual(result['workflow_result']['stop_status'], 'confirmed')

    def test_partial_answer_and_unknown_question_block_without_builder(self):
        manifest = self.manifest()
        plan = self.plan()
        plan['open_questions'].append({'question': 'Which timezone should be used?', 'impact': 'This affects retention.'})
        self.response(json.dumps(plan))
        result = self.execute(manifest)
        dispatch = result['workflow_result']['evidence']['our_dispatch']
        self.assertEqual(dispatch['recipe_status'], 'blocked')
        self.assertEqual(len(dispatch['owner_batches']), 1)
        answers = dispatch['owner_batches'][0]['response']['answers']
        self.assertIn('at most 30 days', answers['roadmap-0']['answers'][0])
        self.assertIn('No additional product fact', answers['roadmap-1']['answers'][0])
        self.assertTrue(all(worker.startswith('planner-') for worker in self.planner_workers(manifest)))
        self.assertEqual(len(self.mock.requests()), 1)
        self.assertIs(result['task_success'], False)

    def test_exhausted_shared_owner_allowance_blocks_without_inventing_facts(self):
        manifest = self.manifest()
        self.response(json.dumps(self.plan()))

        def exhausted(*args, **kwargs):
            policy = InteractionPolicy(*args, **kwargs)
            policy.owner.exchanges = policy.owner.limit
            return policy

        with patch('workflows.interaction_policy.InteractionPolicy', side_effect=exhausted):
            result = self.execute(manifest)
        dispatch = result['workflow_result']['evidence']['our_dispatch']
        self.assertEqual(dispatch['recipe_status'], 'blocked')
        self.assertIn('Owner interaction allowance exhausted.', json.dumps(dispatch['owner_batches']))
        self.assertTrue(all(worker.startswith('planner-') for worker in self.planner_workers(manifest)))
        self.assertEqual(len(self.mock.requests()), 1)

    def test_invalid_source_plan_cannot_consume_owner_allowance(self):
        manifest = self.manifest()
        plan = self.plan()
        plan['requirements'][0]['source_quote'] = 'Invent an export feature.'
        self.response(json.dumps(plan))
        result = self.execute(manifest)
        dispatch = result['workflow_result']['evidence']['our_dispatch']
        self.assertNotIn('owner_batches', dispatch)
        self.assertEqual(dispatch['error']['message'], 'invalid source-grounded requirement')
        self.assertTrue(all(worker.startswith('planner-') for worker in self.planner_workers(manifest)))

    def test_question_objects_are_exact_and_impact_is_retained(self):
        plan = self.plan()
        text, questions = question_proposal(json.dumps(plan))
        self.assertEqual(questions, ['What is the retention policy?'])
        self.assertIn(plan['open_questions'][0]['impact'], json.loads(text)['open_questions'][0])
        plan['open_questions'][0]['owner_answer'] = 'Unauthorized answer'
        with self.assertRaisesRegex(ValueError, 'exact question/impact'):
            question_proposal(json.dumps(plan))
