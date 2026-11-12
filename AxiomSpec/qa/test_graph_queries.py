"""The graph index, the annotations and the reference queries of the service interface (AX-V-001 to AX-V-008).

Every case reads the reference ledger or a small edit of it and requires one named result. Answers are also
validated against the contract in api/openapi.json, so a query cannot drift from the interface it implements.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'qa'))
import check_package as qa  # noqa: E402
import graph_index  # noqa: E402
import queries  # noqa: E402

LEDGER = 'examples/refund-ledger'
APP = LEDGER + '/app/ledger.py'


def node(spec, nid):
    return next(n for n in spec['nodes'] if n['id'] == nid)


class Ledger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = qa.read(LEDGER + '/spec.json')
        cls.annotations = graph_index.scan(ROOT, [LEDGER])
        cls.snapshot = queries.Snapshot(cls.spec, cls.annotations, ROOT)

    def edited(self, edit, annotations=None, repository=ROOT):
        spec = copy.deepcopy(self.spec)
        edit(spec)
        return queries.Snapshot(spec, self.annotations if annotations is None else annotations, repository)

    def all_pages(self, query, **arguments):
        pages, cursor = [], None
        while True:
            page = query(cursor=cursor, **arguments)
            pages.append(page)
            cursor = page['next_cursor']
            if cursor is None:
                return pages


class Annotations(unittest.TestCase):
    def scan(self, files):
        with tempfile.TemporaryDirectory(prefix='axiomspec-scan-') as directory:
            for name, text in files.items():
                path = Path(directory) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(textwrap.dedent(text))
            return graph_index.scan(directory)

    def test_an_annotation_belongs_to_the_definition_it_precedes_or_sits_in(self):
        found = self.scan({'pkg/mod.py': '''\
            # @req REQ-001
            def above():
                pass


            class Box:
                """Holds things. @req REQ-002, REQ-003"""

                # @req REQ-004
                @staticmethod
                def decorated():
                    return 1  # @req REQ-005

                def inside(self):
                    """@req CON-001"""

            # @req REQ-006
            VALUE = 1
            '''})
        self.assertEqual([(a['line'], a['symbol'], a['ids']) for a in found],
                         [(1, 'above', ['REQ-001']), (7, 'Box', ['REQ-002', 'REQ-003']), (9, 'Box.decorated', ['REQ-004']),
                          (12, 'Box.decorated', ['REQ-005']), (15, 'Box.inside', ['CON-001']), (17, None, ['REQ-006'])])
        self.assertEqual({a['path'] for a in found}, {'pkg/mod.py'})

    def test_only_the_exact_token_in_source_files_counts(self):
        found = self.scan({
            'a.ts': '// @req REQ-010 REQ-011\nexport function f() {}\n',
            'b.go': '// @requires REQ-001\n// @request REQ-002\n// req REQ-003\n// @req lowercase-001\n// @req REQ-12\n',
            'notes.md': '@req REQ-001\n', 'data.json': '{"x": "@req REQ-001"}\n',
            'node_modules/dep/x.js': '// @req REQ-001\n', 'broken.py': '# @req REQ-020\ndef (:\n'})
        # `@requires` and `@request` are other words. The token with nothing valid after it is kept, to be reported.
        self.assertEqual([(a['path'], a['line'], a['symbol'], a['ids']) for a in found],
                         [('a.ts', 1, None, ['REQ-010', 'REQ-011']), ('b.go', 4, None, []), ('b.go', 5, None, []),
                          ('broken.py', 1, None, ['REQ-020'])])

    def test_a_form_feed_line_separator_or_bom_does_not_shift_or_drop_annotations(self):
        # Python counts lines at \n only: splitting at \f or U+2028 lost every annotation after it, and a
        # byte-order mark made ast reject the file, so docstrings and symbols were lost.
        found = self.scan({'a.py': '# page\n\f\n# @req REQ-001\ndef f():\n    """@req REQ-002"""\n',
                           'b.ts': 'const s = "\u2028";\n// @req REQ-003\n',
                           'c.py': '\ufeff# @req REQ-004\ndef g():\n    """@req REQ-005"""\n'})
        self.assertEqual([(a['path'], a['line'], a['symbol'], a['ids']) for a in found],
                         [('a.py', 3, 'f', ['REQ-001']), ('a.py', 5, 'f', ['REQ-002']), ('b.ts', 2, None, ['REQ-003']),
                          ('c.py', 1, 'g', ['REQ-004']), ('c.py', 3, 'g', ['REQ-005'])])

    def test_a_file_that_is_not_utf8_keeps_its_annotations(self):
        # A cp1252 accent in a comment made the whole file unreadable, and its annotations were dropped silently.
        with tempfile.TemporaryDirectory(prefix='axiomspec-scan-') as directory:
            Path(directory, 'ledger.py').write_bytes(b'# V\xe9rifie le solde\n# @req REQ-001\ndef reserve():\n    """@req REQ-002"""\n')
            Path(directory, 'ledger.ts').write_bytes(b'// r\xe9serve\n// @req REQ-003\n')
            found = graph_index.scan(directory)
        self.assertEqual([(a['path'], a['line'], a['symbol'], a['ids']) for a in found],
                         [('ledger.py', 2, 'reserve', ['REQ-001']), ('ledger.py', 4, 'reserve', ['REQ-002']),
                          ('ledger.ts', 2, None, ['REQ-003'])])

    def test_a_binding_resolves_in_a_file_python_reads_with_a_bom_or_a_coding_line(self):
        # The text was decoded as UTF-8 without the BOM rule or the coding line, so a valid file looked unparsable.
        with tempfile.TemporaryDirectory(prefix='axiomspec-symbol-') as directory:
            bom, latin = Path(directory, 'bom.py'), Path(directory, 'latin.py')
            bom.write_bytes(b'\xef\xbb\xbfclass Ledger:\n    def reserve(self):\n        pass\n')
            latin.write_bytes(b'# -*- coding: latin-1 -*-\n# V\xe9rifie\nclass Ledger:\n    def reserve(self):\n        pass\n')
            self.assertEqual([qa.resolve_symbol(path, 'Ledger.reserve') for path in (bom, latin)], [True, True])

    def test_a_deeply_nested_expression_does_not_stop_the_scan(self):
        # A thousand chained terms, as generated code has, overflowed the symbol walk and stopped every scan.
        for terms in (3000, 100000):
            found = self.scan({'gen.py': '# @req REQ-001\ndef f():\n    return ' + ' + '.join(['1'] * terms) + '\n',
                               'other.py': '# @req REQ-002\ndef g():\n    pass\n'})
            self.assertEqual([(a['path'], a['ids']) for a in found], [('gen.py', ['REQ-001']), ('other.py', ['REQ-002'])])
        self.assertEqual(found[1]['symbol'], 'g')

    def test_a_test_file_is_recognized_by_name_or_folder(self):
        for path, expected in [('tests/test_ledger.py', True), ('pkg/ledger_test.go', True), ('src/__tests__/a.ts', True),
                               ('src/ledger.spec.ts', True), ('app/ledger.py', False), ('src/contest.py', False), ('test.py', False)]:
            self.assertIs(graph_index.is_test_path(path), expected, path)

    def test_a_scan_cannot_leave_its_root(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'escapes'):
                graph_index.scan(directory, ['..'])

    def test_an_unreadable_directory_is_an_error_not_an_empty_scan(self):
        with tempfile.TemporaryDirectory(prefix='axiomspec-scan-') as directory:
            root = Path(directory).resolve()
            (root / 'src').mkdir()
            (root / 'src/mod.py').write_text('# @req REQ-001\n')
            scandir = graph_index.os.scandir
            for blocked in (root, root / 'src'):
                def denied(path):
                    if Path(path) == blocked:
                        raise PermissionError('Source directory is unreadable')
                    return scandir(path)
                with self.subTest(blocked=blocked), mock.patch.object(graph_index.os, 'scandir', side_effect=denied):
                    for operation in (graph_index.scan, graph_index.signature):
                        with self.assertRaises(PermissionError):
                            operation(root)


class Index(Ledger):
    def test_the_ledger_code_is_annotated_and_every_annotation_names_a_live_object(self):
        self.assertEqual([(a['symbol'], a['ids']) for a in self.annotations],
                         [('authorize', ['REQ-004', 'CON-005']), ('fits', ['CON-002']), ('record_outcome', ['REQ-007']),
                          ('Ledger.transaction', ['CON-001']), ('Ledger.reserve', ['REQ-001', 'REQ-002', 'REQ-003', 'REQ-008']),
                          ('Ledger.command', ['REQ-005', 'REQ-006', 'REQ-009']), ('Ledger.remaining', ['REQ-010'])])
        self.assertEqual(graph_index.check(self.spec, self.annotations), [])
        stale = [dict(path='a.py', line=3, symbol=None, ids=['REQ-999', 'REQ-004'])]
        self.assertEqual([p['code'] for p in graph_index.check(self.spec, stale)], ['UNKNOWN_ANNOTATION_ID'])
        retired = copy.deepcopy(self.spec)
        node(retired, 'REQ-004')['status'] = 'retired'
        self.assertEqual([(p['code'], p['subject_id'], p['line']) for p in graph_index.check(retired, stale)],
                         [('UNKNOWN_ANNOTATION_ID', 'REQ-999', 3), ('RETIRED_ANNOTATION_ID', 'REQ-004', 3)])

    def test_the_index_is_valid_sorted_and_the_committed_file_is_current(self):
        index = self.snapshot.graph
        qa.make_validator(qa.read('schemas/graph.schema.json')).validate(index)
        self.assertEqual(index['spec_sha256'], qa.digest(qa.canonical(self.spec)))
        self.assertEqual([n['id'] for n in index['nodes']], sorted(n['id'] for n in self.spec['nodes']))
        self.assertEqual(index['edges'], sorted(index['edges'], key=lambda e: (e['from'], e['relation'], e['to'])))
        self.assertEqual((len(index['nodes']), len(index['edges'])), (len(self.spec['nodes']), len(self.spec['edges'])))
        self.assertEqual(graph_index.dumps(index), (ROOT / LEDGER / 'axiom-graph.json').read_text())
        shuffled = copy.deepcopy(self.spec)
        for section in ('nodes', 'edges', 'bindings'):
            shuffled[section].reverse()
        self.assertEqual(graph_index.build(shuffled, self.annotations[::-1]), dict(index, spec_sha256=qa.digest(qa.canonical(shuffled))))

    def test_the_file_is_json_with_one_record_per_line(self):
        text = graph_index.dumps(self.snapshot.graph)
        self.assertEqual(json.loads(text), self.snapshot.graph)
        lines = text.splitlines()
        self.assertEqual(len(lines), 2 + 5 + sum(len(self.snapshot.graph[s]) + 2 for s in graph_index.SECTIONS))
        hits = [line for line in lines if '"REQ-007"' in line]
        self.assertEqual(len(hits), 16)  # the node, 11 links and 4 traces: what a search for the ID returns
        self.assertTrue(all(line.startswith('{') for line in hits))
        located = [json.loads(line.rstrip(',')) for line in lines if APP in line and '"Ledger.reserve"' in line]
        self.assertEqual(sorted({t['node_id'] for t in located}), ['CON-001', 'REQ-001', 'REQ-002', 'REQ-003', 'REQ-008'])

    def test_requirements_carry_their_weight_and_a_trace_leads_to_requirements(self):
        index = self.snapshot.graph
        row = next(n for n in index['nodes'] if n['id'] == 'REQ-004')
        self.assertEqual((row['priority'], row['risk'], row['weight_minor'], row['flag_id']), ('must', 'critical', 950, None))
        self.assertEqual(set(next(n for n in index['nodes'] if n['id'] == 'GOAL-001')), {'id', 'kind', 'status', 'title'})
        guard = next(t for t in index['traces'] if t['origin'] == 'annotation' and t['node_id'] == 'CON-002')
        self.assertEqual((guard['symbol'], guard['kind'], guard['line'] > 0), ('fits', 'code', True))
        formalized = sorted(e['to'] for e in self.spec['edges'] if (e['from'], e['relation']) == ('CON-002', 'formalizes'))
        self.assertEqual(guard['requirement_ids'], formalized)
        without = graph_index.build(self.spec)
        self.assertEqual({t['origin'] for t in without['traces']}, {'binding'})
        self.assertEqual(len(without['traces']), len(self.spec['bindings']))

    def test_command_line(self):
        import contextlib, io
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = graph_index.main(['build', str(ROOT / LEDGER / 'spec.json'), '--repo', str(ROOT), '--include', LEDGER])
            self.assertEqual(graph_index.main(['build']), 4)
        self.assertEqual((code, out.getvalue()), (0, (ROOT / LEDGER / 'axiom-graph.json').read_text()))
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'x.py').write_text('# @req REQ-999\n')
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(graph_index.main(['build', str(ROOT / LEDGER / 'spec.json'), '--repo', directory]), 2)


class Lookup(Ledger):
    def test_a_requirement_is_returned_with_its_sentence_weight_links_and_code(self):
        view = queries.lookup(self.snapshot, 'REQ-007')
        queries.contract_validator('NodeView').validate(view)
        self.assertEqual(view['statement'], 'When an authorization attempt completes or is denied, the RefundLedger shall record '
                         'the operation identifier and outcome without copying credentials or complete request bodies.')
        self.assertEqual(view['requirement'], dict(id='REQ-007', title='Bounded audit diagnostics', status='active', priority='must',
                                                   risk='medium', weight_minor=375, flag_id=None, verification_mode='executable'))
        self.assertEqual((view['content'], view['complete'], view['links_total']), (None, True, 11))
        self.assertIn(dict(relation='formalizes', direction='in', id='CON-011', kind='Constraint',
                           title='An audited operation adds one row holding its identifier, kind and outcome'), view['links'])
        self.assertEqual([(t['symbol'], t['kind'], t['origin']) for t in view['traces']],
                         [('Ledger.audit_events', 'observation', 'binding'), ('record_outcome', 'code', 'binding'),
                          ('record_outcome', 'code', 'annotation'), ('Test013AuditContent', 'test', 'binding')])
        full = queries.lookup(self.snapshot, 'REQ-007', 'full')
        self.assertEqual(full['content'], node(self.spec, 'REQ-007'))
        self.assertLess(len(qa.canonical(view)), len(qa.canonical(full)))
        self.assertNotEqual(view['query_digest'], full['query_digest'])

    def test_each_requirement_pattern_renders_its_sentence(self):
        template = node(self.spec, 'REQ-001')
        def render(**data):
            return queries.statement(dict(template, data=dict(template['data'], subject='ledger', response='refuse it', **data)))
        blank = dict(conditions=[], trigger=None, feature=None)
        self.assertEqual(render(**dict(blank, pattern='ubiquitous')), 'The ledger shall refuse it.')
        self.assertEqual(render(**dict(blank, pattern='event', trigger='a request arrives')), 'When a request arrives, the ledger shall refuse it.')
        self.assertEqual(render(**dict(blank, pattern='unwanted', trigger='capacity is exceeded')), 'If capacity is exceeded, then the ledger shall refuse it.')
        self.assertEqual(render(**dict(blank, pattern='state', conditions=['the payment is open', 'the tenant is active'])),
                         'While the payment is open and the tenant is active, the ledger shall refuse it.')
        self.assertEqual(render(**dict(blank, pattern='optional', feature='reports are enabled')), 'Where reports are enabled, the ledger shall refuse it.')
        self.assertEqual(render(**dict(blank, pattern='composite', conditions=['open'], trigger='asked')), 'While open, when asked, the ledger shall refuse it.')

    def test_every_identified_object_can_be_looked_up_and_an_unknown_id_is_not_guessed(self):
        for object_id, kind in [('ENV-003', 'Environment'), ('FLAG-001', 'Flag'), ('IMP-001', 'Import'), ('KEY-001', 'ApprovalKey'),
                                ('ACTOR-001', 'Actor'), ('BIND-001', 'Binding'), ('SCN-027', 'Scenario')]:
            view = queries.lookup(self.snapshot, object_id, 'full')
            queries.contract_validator('NodeView').validate(view)
            self.assertEqual((view['kind'], view['statement'], view['content']['id']), (kind, None, object_id))
        for wrong in ('REQ-999', 'req-004', 'REQ-04', ''):
            with self.assertRaises(queries.QueryError) as raised:
                queries.lookup(self.snapshot, wrong)
            self.assertEqual((raised.exception.code, raised.exception.status), ('NOT_FOUND', 404))
        with self.assertRaises(queries.QueryError) as raised:
            queries.lookup(self.snapshot, 'REQ-004', 'everything')
        self.assertEqual(raised.exception.code, 'INVALID_PARAMETER')


class Context(Ledger):
    def ids(self, pages):
        return [item['id'] for page in pages for item in page['items']]

    def test_direct_scope_is_the_requirement_and_what_binds_it(self):
        page, = self.all_pages(queries.context, snapshot=self.snapshot, ids=['REQ-007'])
        queries.contract_validator('ContextPage').validate(page)
        self.assertEqual(self.ids([page]), ['REQ-007', 'GOAL-003', 'TERM-001', 'CON-001', 'CON-005', 'CON-006', 'CON-011',
                                            'DEC-001', 'DEC-004', 'ASM-001', 'ENV-001', 'ENV-004', 'BIND-004', 'BIND-005', 'BIND-030'])
        self.assertEqual([i['role'] for i in page['items']][:2], ['seed', 'required'])
        self.assertEqual(page['items'][0]['content'], node(self.spec, 'REQ-007'))
        self.assertIn(['formalizes', 'in', 'CON-011'], page['items'][0]['links'])
        self.assertTrue(page['complete'])
        self.assertIn('not the mandatory context of a change', ' '.join(page['analysis_limits']))
        kinds = {i['kind'] for i in page['items']}
        self.assertFalse(kinds & {'Scenario', 'TestCase', 'Component', 'Actor', 'Source'})
        self.assertLess(len(qa.canonical(page)), 16384)

    def test_change_scope_is_the_conservative_closure(self):
        direct = set(self.ids(self.all_pages(queries.context, snapshot=self.snapshot, ids=['REQ-007'])))
        pages = self.all_pages(queries.context, snapshot=self.snapshot, ids=['REQ-007'], scope='change')
        change = self.ids(pages)
        self.assertEqual(len(change), len(set(change)))
        self.assertTrue(direct <= set(change))
        # Hard project rules bring the requirements they formalize, with their scenarios and tests.
        rules = {n['id'] for n in self.spec['nodes'] if n['kind'] == 'Constraint' and n['data']['scope'] == 'project'}
        self.assertEqual(rules, {'CON-001', 'CON-005'})
        under_rules = {e['to'] for e in self.spec['edges'] if e['relation'] == 'formalizes' and e['from'] in rules}
        self.assertTrue(rules | under_rules | {'TEST-013', 'SCN-027', 'SCN-029', 'SCN-031', 'COMP-003', 'ACTOR-001', 'SRC-001'} <= set(change))
        self.assertNotIn('REQ-010', change)  # behind no project rule and not linked to the audit requirement
        self.assertNotIn('not the mandatory context', ' '.join(pages[0]['analysis_limits']))
        self.assertTrue(pages[-1]['complete'] and all(not p['complete'] for p in pages[:-1]))
        for page in pages:
            queries.contract_validator('ContextPage').validate(page)
            self.assertLessEqual(len(qa.canonical(page)), queries.MAX_BYTES)
        order = [queries.KIND_ORDER.index(item['kind']) for page in pages for item in page['items']]
        self.assertEqual(order, sorted(order))

    def test_a_shared_term_does_not_lead_back_to_unrelated_requirements(self):
        identity = qa.read('examples/identity-adapter/spec.json')
        other = copy.deepcopy(node(identity, 'REQ-001'))
        other.update(id='REQ-002', title='Another requirement using the same term')
        identity['nodes'].append(other)
        identity['edges'] += [dict(id='EDGE-003', relation='satisfies', origin='declared', rationale='x', **{'from': 'REQ-002', 'to': 'GOAL-001'}),
                              dict(id='EDGE-004', relation='uses_term', origin='declared', rationale='x', **{'from': 'REQ-002', 'to': 'TERM-001'})]
        self.assertEqual(qa.reference_errors(identity), [])
        snapshot = queries.Snapshot(identity)
        for scope in ('direct', 'change'):
            found = self.ids(self.all_pages(queries.context, snapshot=snapshot, ids=['REQ-001'], scope=scope))
            self.assertIn('TERM-001', found)
            self.assertNotIn('REQ-002', found)
        both = self.ids(self.all_pages(queries.context, snapshot=snapshot, ids=['REQ-002', 'REQ-001'], scope='change'))
        self.assertEqual(both[:2], ['REQ-001', 'REQ-002'])

    def test_a_seed_that_is_not_a_requirement_leads_to_the_requirements_it_concerns(self):
        for seed, expected in [('CON-011', {'REQ-007'}), ('TEST-013', {'REQ-007'}), ('COMP-003', {'REQ-007'}), ('FLAG-001', {'REQ-010'})]:
            page = queries.context(self.snapshot, [seed])
            seeds = {i['id'] for i in page['items'] if i['role'] == 'seed' and i['kind'] == 'Requirement'}
            self.assertEqual(seeds, expected, seed)
            self.assertIn(seed, {i['id'] for i in page['items']})
        unmapped = queries.context(self.snapshot, ['ACTOR-002'])
        self.assertIn('No requirement is declared for: ACTOR-002', ' '.join(unmapped['analysis_limits']))
        with self.assertRaises(queries.QueryError) as raised:
            queries.context(self.snapshot, ['REQ-004', 'REQ-999'])
        self.assertEqual(raised.exception.code, 'NOT_FOUND')
        for arguments in (dict(ids=[]), dict(ids=['REQ-004'], scope='everything')):
            with self.assertRaises(queries.QueryError) as raised:
                queries.context(self.snapshot, **arguments)
            self.assertEqual(raised.exception.code, 'INVALID_PARAMETER')

    def test_retired_objects_stay_out_unless_asked_for(self):
        snapshot = self.edited(lambda s: node(s, 'CON-006').update(status='retired'))
        self.assertNotIn('CON-006', self.ids(self.all_pages(queries.context, snapshot=snapshot, ids=['REQ-007'], scope='change')))
        self.assertIn('CON-006', self.ids([queries.context(snapshot, ['CON-006'])]))


class Paging(Ledger):
    def test_pages_stay_within_any_budget_and_join_to_the_whole_answer(self):
        whole = [item for page in self.all_pages(queries.context, snapshot=self.snapshot, ids=['REQ-004'], scope='change') for item in page['items']]
        for budget in (4096, 6000, 16384, 32768):
            pages = self.all_pages(queries.context, snapshot=self.snapshot, ids=['REQ-004'], scope='change', budget_bytes=budget)
            self.assertTrue(all(len(qa.canonical(page)) <= budget for page in pages), budget)
            omitted = {o['id'] for page in pages for o in page['omissions']}
            joined = [item for page in pages for item in page['items']]
            self.assertEqual([i['id'] for i in joined], [i['id'] for i in whole if i['id'] not in omitted])
            self.assertEqual({p['total_visible_count'] for p in pages}, {len(whole)})
            self.assertEqual(pages[-1]['complete'], not omitted)
        self.assertGreater(len(self.all_pages(queries.context, snapshot=self.snapshot, ids=['REQ-004'], scope='change', budget_bytes=4096)), 10)

    def test_an_object_too_large_for_the_budget_is_named_never_cut(self):
        pages = self.all_pages(queries.context, snapshot=self.snapshot, ids=['REQ-004'], scope='change', budget_bytes=4096)
        omissions = [o for page in pages for o in page['omissions']]
        self.assertTrue(omissions)
        self.assertTrue(all(o['reason'] == 'exceeds_budget' and o['bytes'] > 3000 for o in omissions))
        self.assertFalse(pages[-1]['complete'])
        self.assertTrue({o['id'] for o in omissions} <= {i['id'] for p in self.all_pages(queries.context, snapshot=self.snapshot, ids=['REQ-004'], scope='change') for i in p['items']})

    def test_at_most_one_hundred_items_per_page(self):
        many = [dict(id=f'X-{number:04d}') for number in range(250)]
        first = queries.page(self.snapshot, 'test', {}, many)
        self.assertEqual((first['returned_count'], first['total_visible_count'], first['complete']), (100, 250, False))
        second = queries.page(self.snapshot, 'test', {}, many, cursor=first['next_cursor'])
        third = queries.page(self.snapshot, 'test', {}, many, cursor=second['next_cursor'])
        self.assertEqual((second['items'][0], third['returned_count'], third['next_cursor'], third['complete']), (many[100], 50, None, True))

    def test_a_cursor_serves_only_its_own_snapshot_and_query(self):
        first = queries.context(self.snapshot, ['REQ-004'], 'change')
        cursor = first['next_cursor']
        other = self.edited(lambda s: s['project'].update(name='Another release'))
        attempts = [lambda: queries.context(self.snapshot, ['REQ-005'], 'change', cursor=cursor),
                    lambda: queries.context(self.snapshot, ['REQ-004'], 'direct', cursor=cursor),
                    lambda: queries.context(other, ['REQ-004'], 'change', cursor=cursor),
                    lambda: queries.gaps(self.snapshot, cursor=cursor),
                    lambda: queries.context(self.snapshot, ['REQ-004'], 'change', cursor=cursor[:-4] + 'AAAA'),
                    lambda: queries.context(self.snapshot, ['REQ-004'], 'change', cursor='not a cursor'),
                    lambda: queries.context(self.snapshot, ['REQ-004'], 'change', budget_bytes=100),
                    lambda: queries.context(self.snapshot, ['REQ-004'], 'change', budget_bytes=10 ** 6)]
        for attempt in attempts:
            with self.assertRaises(queries.QueryError) as raised:
                attempt()
            self.assertIn(raised.exception.code, ('INVALID_CURSOR', 'INVALID_PARAMETER'))
        again = queries.context(self.snapshot, ['REQ-004'], 'change', cursor=cursor)
        self.assertEqual(again, queries.context(self.snapshot, ['REQ-004'], 'change', cursor=cursor))  # stateless and repeatable
        self.assertEqual(again['query_digest'], first['query_digest'])


class Trace(Ledger):
    def test_a_file_or_symbol_leads_to_its_requirements(self):
        page = queries.trace(self.snapshot, path=APP, symbol='Ledger.reserve')
        queries.contract_validator('TracePage').validate(page)
        rows = [(i['symbol'], i['origin'], i['node_id']) for i in page['items']]
        self.assertEqual(rows, [('Ledger', 'binding', 'COMP-001'), ('Ledger.reserve', 'binding', 'CON-001'),
                                ('Ledger.reserve', 'annotation', 'REQ-001'), ('Ledger.reserve', 'annotation', 'REQ-002'),
                                ('Ledger.reserve', 'annotation', 'REQ-003'), ('Ledger.reserve', 'annotation', 'REQ-008')])
        annotated = next(i for i in page['items'] if i['node_id'] == 'REQ-001')
        self.assertEqual(annotated['requirements'], [dict(id='REQ-001', title=node(self.spec, 'REQ-001')['title'], status='active',
                                                          priority='must', risk='high', weight_minor=700)])
        whole_file = queries.trace(self.snapshot, path=APP)
        self.assertGreater(whole_file['total_visible_count'], page['total_visible_count'])
        self.assertEqual(queries.trace(self.snapshot, path='no/such/file.py')['items'], [])
        # `find .` writes ./path; that spelling found nothing and still reported a complete answer.
        for spelling in ('./' + APP, APP.replace('/', '//', 1)):
            self.assertEqual(queries.trace(self.snapshot, path=spelling)['items'], whole_file['items'])
        self.assertEqual({i['symbol'] for i in queries.trace(self.snapshot, path=APP, symbol='authorize')['items']}, {'authorize'})
        self.assertEqual({i['symbol'] for i in queries.trace(self.snapshot, path=APP, symbol='Ledger')['items']} >= {'Ledger', 'Ledger.reserve', 'Ledger.command'}, True)

    def test_an_object_leads_to_its_code_and_tests(self):
        page = queries.trace(self.snapshot, object_id='REQ-004')
        self.assertEqual({(i['path'].rsplit('/', 1)[1], i['kind']) for i in page['items']},
                         {('ledger.py', 'code'), ('ledger.py', 'enforcement'), ('ledger.py', 'observation'), ('test_ledger.py', 'test')})
        self.assertIn(('authorize', 'annotation'), {(i['symbol'], i['origin']) for i in page['items']})
        self.assertIn('does not show that the code satisfies', page['analysis_limits'][0])
        for arguments in (dict(), dict(path=APP, object_id='REQ-004'), dict(symbol='authorize')):
            with self.assertRaises(queries.QueryError) as raised:
                queries.trace(self.snapshot, **arguments)
            self.assertEqual(raised.exception.code, 'INVALID_PARAMETER')
        with self.assertRaises(queries.QueryError) as raised:
            queries.trace(self.snapshot, object_id='REQ-999')
        self.assertEqual(raised.exception.code, 'NOT_FOUND')


class Gaps(Ledger):
    def found(self, snapshot, phase='design'):
        page = queries.gaps(snapshot, phase)
        queries.contract_validator('GapsPage').validate(page)
        return [(g['gate'], g['code'], g['id']) for g in page['items']]

    def test_the_ledger_has_no_gap(self):
        # Until edition 0.7.2 the flagged report requirement had tests in both flag states and no scenario.
        self.assertEqual(self.found(self.snapshot), [])
        self.assertEqual(self.found(self.snapshot, 'implementation'), [])
        without = self.edited(lambda s: s['edges'].__setitem__(slice(None), [e for e in s['edges'] if (e['relation'], e['to']) != ('illustrates', 'REQ-010')]))
        self.assertIn(('G06', 'MISSING_SCENARIO', 'REQ-010'), self.found(without))

    def test_each_design_gap(self):
        def open_decision(spec):
            node(spec, 'DEC-001')['data']['answer'] = None
        def doubt(spec):
            node(spec, 'ASM-001')['data'].update(blocking=True, state='unverified')
        def untested(spec):
            spec['edges'] = [e for e in spec['edges'] if not (e['relation'] == 'verifies' and e['to'] == 'REQ-007')]
        def broken(spec):
            node(spec, 'REQ-007')['owner'] = 'ACTOR-999'
        for edit, expected in [(open_decision, ('G04', 'OPEN_DECISION', 'DEC-001')), (doubt, ('G04', 'UNVALIDATED_ASSUMPTION', 'ASM-001')),
                               (untested, ('G07', 'MISSING_TEST', 'REQ-007')), (broken, ('G02', 'UNKNOWN_ACTOR', None))]:
            self.assertIn(expected, self.found(self.edited(edit)), expected)
        manual = self.edited(lambda s: node(s, 'REQ-010')['data'].update(verification_mode='manual'))
        self.assertEqual(self.found(manual), [])

    def test_each_implementation_gap(self):
        def unbind(spec):
            spec['bindings'] = [b for b in spec['bindings'] if b['node_id'] not in ('COMP-003', 'CON-011')]
        self.assertIn(('G09', 'UNTRACED_REQUIREMENT', 'REQ-007'), self.found(self.edited(unbind, annotations=[]), 'implementation'))
        self.assertNotIn(('G09', 'UNTRACED_REQUIREMENT', 'REQ-007'), self.found(self.edited(unbind), 'implementation'))  # the annotation places it
        self.assertNotIn(('G09', 'UNTRACED_REQUIREMENT', 'REQ-007'), self.found(self.edited(unbind, annotations=[])))
        renamed = self.edited(lambda s: next(b for b in s['bindings'] if b['id'] == 'BIND-002').update(symbol='authorise'))
        self.assertIn(('G09', 'UNRESOLVED_BINDING', 'BIND-002'), self.found(renamed, 'implementation'))
        planned = self.edited(lambda s: next(b for b in s['bindings'] if b['id'] == 'BIND-002').update(expected_resolution='planned'))
        self.assertIn(('G09', 'PLANNED_BINDING', 'BIND-002'), self.found(planned, 'implementation'))
        stale = self.annotations + [dict(path='x.py', line=1, symbol=None, ids=['REQ-999'])]
        self.assertIn(('G09', 'UNKNOWN_ANNOTATION_ID', 'REQ-999'), self.found(self.edited(lambda s: None, annotations=stale), 'implementation'))
        blind = queries.gaps(self.edited(lambda s: None, repository=None), 'implementation')
        self.assertIn('No repository was supplied', ' '.join(blind['analysis_limits']))
        with self.assertRaises(queries.QueryError):
            queries.gaps(self.snapshot, 'release')


class Propose(Ledger):
    def propose(self, *operations, version='1.1.1'):
        result = queries.propose(self.spec, version, list(operations))
        queries.contract_validator('CandidateResult').validate(result)
        return result

    def reworded(self, nid='REQ-007', **changes):
        item = copy.deepcopy(node(self.spec, nid))
        item.update(changes or dict(title=item['title'] + ' (reworded)'))
        return dict(op='put', section='nodes', item=item)

    def test_an_edit_by_id_yields_a_checked_successor(self):
        before = copy.deepcopy(self.spec)
        result = self.propose(self.reworded())
        self.assertEqual(self.spec, before)
        candidate = result['candidate']
        self.assertEqual(candidate['release'], dict(version='1.1.1', compatibility=[], previous=dict(
            version='1.1.0', spec_sha256=qa.digest(qa.canonical(self.spec)))))
        self.assertEqual((result['status'], result['schema_errors'], result['reference_errors']), ('pass', [], []))
        self.assertEqual((result['comparison']['status'], result['comparison']['required_step']), ('pass', 'patch'))
        self.assertEqual(node(candidate, 'REQ-007')['revision'], node(self.spec, 'REQ-007')['revision'] + 1)
        self.assertEqual(result['spec_sha256'], qa.digest(qa.canonical(candidate)))
        self.assertEqual(result, self.propose(self.reworded()))  # the same request, the same digest

    def test_the_service_owns_the_revision(self):
        sent = self.reworded(title='Reworded audit diagnostics', revision=99)
        self.assertEqual(node(self.propose(sent)['candidate'], 'REQ-007')['revision'], node(self.spec, 'REQ-007')['revision'] + 1)
        same = dict(op='put', section='nodes', item=dict(node(self.spec, 'REQ-007'), revision=42))
        unchanged = self.propose(same, self.reworded('REQ-008'))['candidate']
        self.assertEqual(node(unchanged, 'REQ-007'), node(self.spec, 'REQ-007'))
        added = dict(node(self.spec, 'GOAL-001'), id='GOAL-009', title='A new goal', revision=7)
        self.assertEqual(node(self.propose(dict(op='put', section='nodes', item=added))['candidate'], 'GOAL-009')['revision'], 1)

    def test_retire_remove_and_set(self):
        edge = next(e for e in self.spec['edges'] if (e['from'], e['relation'], e['to']) == ('CON-006', 'formalizes', 'REQ-007'))
        result = self.propose(dict(op='retire', id='CON-006'), dict(op='remove', section='edges', id=edge['id']),
                              dict(op='set', field='exports', value=['REQ-004']))
        candidate = result['candidate']
        self.assertEqual((node(candidate, 'CON-006')['status'], node(candidate, 'CON-006')['revision']), ('retired', node(self.spec, 'CON-006')['revision'] + 1))
        self.assertNotIn(edge['id'], [e['id'] for e in candidate['edges']])
        self.assertEqual(candidate['exports'], ['REQ-004'])
        self.assertEqual(result['comparison']['required_step'], 'minor')
        twice = self.propose(dict(op='retire', id='CON-006'), dict(op='retire', id='CON-006'), dict(op='remove', section='edges', id=edge['id']))
        self.assertEqual(node(twice['candidate'], 'CON-006')['revision'], node(self.spec, 'CON-006')['revision'] + 1)

    def test_a_candidate_that_breaks_a_rule_is_returned_with_the_reason(self):
        orphan = self.propose(dict(op='retire', id='GOAL-003'))
        self.assertEqual(orphan['status'], 'fail')
        self.assertIn('ACTIVE_TO_RETIRED', orphan['reference_errors'])
        breaking = self.propose(self.reworded(data=dict(node(self.spec, 'REQ-007')['data'], response='record everything')))
        self.assertEqual((breaking['status'], breaking['comparison']['required_step']), ('fail', 'major'))
        self.assertEqual({e['code'] for e in breaking['comparison']['errors']}, {'UNACKNOWLEDGED_BREAKING', 'VERSION_BUMP_TOO_SMALL'})
        shapeless = self.propose(dict(op='put', section='nodes', item=dict(id='REQ-050', kind='Requirement')))
        self.assertEqual((shapeless['status'], shapeless['comparison'], bool(shapeless['schema_errors'])), ('fail', None, True))

    def test_invalid_edits_are_refused(self):
        for operations in ([], 'put', [dict(op='delete', id='REQ-001')], [dict(op='remove', section='nodes', id='REQ-001')],
                           [dict(op='remove', section='edges', id='EDGE-999')], [dict(op='retire', id='REQ-999')],
                           [dict(op='put', section='release', item=dict(id='X-001'))], [dict(op='put', section='nodes', item=dict(title='no id'))],
                           [dict(op='set', field='project', value={})], [dict(op='set', field='exports')], ['retire']):
            with self.assertRaises(queries.QueryError) as raised:
                queries.propose(self.spec, '1.1.1', operations)
            self.assertEqual(raised.exception.code, 'INVALID_PARAMETER')


class Contract(unittest.TestCase):
    def setUp(self):
        self.document = qa.read('api/openapi.json')
        self.tools = qa.read('api/mcp-tools.json')['tools']
        self.operations = {(method, path): operation for path, item in self.document['paths'].items() for method, operation in item.items()}

    def test_every_read_is_a_get_and_names_its_release(self):
        reads = {key: op for key, op in self.operations.items()
                 if op['x-axiom-modes'] == ['sandbox', 'organization'] and 'read' in op['tags']}
        self.assertEqual(len(reads), 6)
        self.assertEqual({method for method, _ in reads}, {'get'})
        self.assertTrue(all(path == '/v1/snapshots' or path.startswith('/v1/snapshots/{digest}/') for _, path in reads))
        probes = {key for key, op in self.operations.items() if 'health' in op['tags']}
        self.assertEqual(probes, {('get', '/health/live'), ('get', '/health/ready')})
        writes = {key for key in self.operations if key[0] != 'get'}
        self.assertEqual(writes, {('put', '/v1/releases/{digest}'), ('put', '/v1/releases/{digest}/approvals'), ('post', '/v1/candidates')})
        self.assertTrue(all(self.operations[key]['x-axiom-modes'] == ['organization'] for key in writes))

    def test_every_operation_documents_its_answers_and_errors(self):
        self.assertEqual(len(self.operations), 18)
        for (method, path), operation in self.operations.items():
            success = [code for code in operation['responses'] if code.startswith('2')]
            # One answer schema per operation. Only a candidate has two statuses: 201 held, 200 refused.
            self.assertEqual(success, ['200', '201'] if path == '/v1/candidates' else ['200'], path)
            schemas = {operation['responses'][code]['content']['application/json']['schema']['$ref'] for code in success}
            self.assertEqual(len(schemas), 1, path)
            self.assertIn(schemas.pop().rsplit('/', 1)[1], self.document['components']['schemas'])
            for code, response in operation['responses'].items():
                if not code.startswith('2'):
                    self.assertEqual(response['content']['application/problem+json']['schema'], {'$ref': '#/components/schemas/Problem'})
            declared = {p['name'] for p in operation['parameters'] if p['in'] == 'path'}
            self.assertEqual(declared, {part[1:-1] for part in path.split('/') if part.startswith('{')}, path)

    def test_the_tools_are_few_and_each_is_one_operation(self):
        by_id = {operation['operationId']: operation for operation in self.operations.values()}
        self.assertEqual([t['name'] for t in self.tools if 'sandbox' in t['modes']], ['axiom_lookup', 'axiom_context', 'axiom_trace', 'axiom_gaps'])
        self.assertEqual(len(self.tools), 8)
        for tool in self.tools:
            operation = by_id[tool['operation_id']]
            self.assertEqual((operation['x-mcp-tool'], operation['x-axiom-modes']), (tool['name'], tool['modes']))
            self.assertLessEqual(len(tool['description']), 200)
            self.assertFalse(tool['input_schema']['additionalProperties'])
        self.assertLess(len(json.dumps([dict(name=t['name'], description=t['description'], inputSchema=t['input_schema'])
                                        for t in self.tools if 'sandbox' in t['modes']])), 2600)


if __name__ == '__main__':
    unittest.main()
