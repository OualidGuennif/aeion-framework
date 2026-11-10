"""Selected readiness input checks, not a CROA conformance assessor."""

ITEMS = tuple(f'{domain}{i}' for domain, count in [('A', 7), ('B', 7), ('R', 6), ('D', 10), ('E', 7)]
              for i in range(1, count + 1))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def tri_and(*values):
    return False if False in values else (None if None in values else True)


def tri_or(*values):
    return True if True in values else (None if None in values else False)


def findings(scores):
    """Guide pp. 5-6. None preserves an unanswered item; no weighted score."""
    require(set(scores) == set(ITEMS), 'CROA assessment item coverage')
    require(all(v is None or type(v) is int and 0 <= v <= 4 for v in scores.values()),
            'CROA item scores must be null or integers from 0 to 4')
    def ge(item, threshold):
        return None if scores[item] is None else scores[item] >= threshold
    def le(item, threshold):
        return None if scores[item] is None else scores[item] <= threshold
    rules = [
        ('CRF-001', 'critical', tri_and(ge('B2', 3), ge('B3', 3)), 'Direct access without a hard stop'),
        ('CRF-002', 'critical', tri_and(ge('R1', 3), tri_or(ge('B1', 3), ge('B2', 3))), 'Sensitive data under advisory/direct access'),
        ('CRF-003', 'critical', tri_and(ge('A3', 3), ge('B3', 2)), 'High-impact action without a hard stop'),
        ('CRF-004', 'high', ge('B4', 3), 'Missing permission-decision evidence'),
        ('CRF-005', 'high', tri_and(ge('A2', 3), ge('B6', 3)), 'Sprawl without a mandatory control point'),
        ('CRF-006', 'high', tri_and(ge('A4', 3), ge('B1', 3)), 'Autonomy under guidance-only controls'),
        ('CRF-007', 'high', le('D4', 1), 'Weak execution boundary'),
        ('CRF-008', 'high', tri_or(le('E3', 1), le('E4', 1)), 'Missing sponsorship or pilot team'),
        ('CRF-009', 'medium', le('D3', 1), 'Missing policy authority'),
        ('CRF-010', 'medium', tri_and(le('D5', 1), ge('A7', 2)), 'External integration without a target registry'),
        ('CRF-011', 'medium', le('D6', 1), 'Limited exact constraint evaluability'),
        ('CRF-012', 'medium', ge('B5', 3), 'Denials treated as operational errors'),
        ('CRF-013', 'medium', tri_and(ge('A6', 3), ge('B1', 3)), 'Authority expansion under guidance-only controls'),
    ]
    return [dict(id=rid, severity=severity,
                 state='unknown' if result is None else ('triggered' if result else 'not_triggered'),
                 subject=subject) for rid, severity, result, subject in rules]


def assess_inputs(spec, record, expected_spec_digest):
    """Requires the sidecar schema first. Check declared references and missing data."""
    require(record['subject']['project_id'] == spec['project']['id'], 'CROA subject project mismatch')
    if record['spec_sha256'] is not None:
        require(record['spec_sha256'] == expected_spec_digest, 'Stale CROA specification digest')
    nodes = {n['id']: n for n in spec['nodes']}
    sources = {s['id']: s for s in spec['sources']}
    bindings = {b['id']: b for b in spec['bindings']}
    gaps = []
    if record['spec_sha256'] is None:
        gaps.append('Specification snapshot not pinned')
    if record['subject']['consequence_class'] is None:
        gaps.append('Action consequence class not assessed')
    scores = {key: answer['score'] for key, answer in record['answers'].items()}
    findings(scores)  # Validate scalar types before applying the evidence policy.
    effective_scores = dict(scores)
    for key, answer in record['answers'].items():
        require(set(answer['source_ids']).issubset(sources), f'Unknown CROA answer source: {key}')
        if answer['score'] is not None:
            if not answer['source_ids']:
                gaps.append(f'{key}: missing evidence source')
            if record['assessment_kind'] == 'evidence_record':
                require(all(sources[sid]['type'] != 'fixture' for sid in answer['source_ids']),
                        f'{key}: fixture cannot substantiate an operational assessment')
                if not answer['source_ids']:
                    effective_scores[key] = None
                if any(sources[sid]['capture_sha256'] is None for sid in answer['source_ids']):
                    gaps.append(f'{key}: uncaptured evidence')
                    effective_scores[key] = None
                if any(sources[sid]['review_state'] != 'reviewed' for sid in answer['source_ids']):
                    gaps.append(f'{key}: source review not declared')
                    effective_scores[key] = None
    for row in record['traceability'] + record['framework_links']:
        require(set(row['node_ids']).issubset(nodes), 'Unknown CROA mapped node')
        require(all(nodes[nid]['status'] != 'retired' for nid in row['node_ids']), 'Retired CROA mapped node')
        for nid in row['node_ids']:
            if nodes[nid]['status'] == 'draft':
                gaps.append(f'{nid}: mapped node remains draft')
        for bid in row.get('binding_ids', []):
            require(bid in bindings, 'Unknown CROA evidence binding')
            require(nodes.get(bindings[bid]['node_id'], {}).get('status') != 'retired', 'CROA evidence binding targets a retired node')
            gaps.append(f'{bid}: operational evidence resolution is not implemented')
    if not record['framework_links']:
        gaps.append('No framework evidence mapping declared')
    seen = set()
    for row in record['invariant_metadata']:
        cid = row['constraint_id']
        require(cid not in seen, 'Duplicate CROA invariant metadata')
        seen.add(cid)
        require(nodes.get(cid, {}).get('kind') == 'Constraint', 'CROA invariant must reference a Constraint')
        require(nodes[cid]['status'] != 'retired', 'Retired CROA invariant metadata')
        if nodes[cid]['status'] == 'draft':
            gaps.append(f'{cid}: invariant candidate remains draft')
        if row['evaluability_class'] is None or row['trajectory_profile'] is None:
            gaps.append(f'{cid}: CROA classification not reviewed')
        bid = row['method_binding_id']
        if bid is None:
            gaps.append(f'{cid}: evaluation method not linked')
        else:
            require(bid in bindings, 'Unknown CROA evaluation-method binding')
            require(bindings[bid]['node_id'] == cid and bindings[bid]['kind'] in {'code', 'enforcement', 'observation'},
                    'CROA evaluation method must bind the same constraint')
            gaps.append(f'{cid}: evaluation method qualification not assessed')
    missing = sorted(key for key, score in scores.items() if score is None)
    return dict(format='axiomspec-croa-input-review/0.2', scope='selected_readiness_inputs',
                input_status='incomplete' if missing or gaps else 'complete',
                source_verification='declared_only', assessment_kind=record['assessment_kind'],
                assessment_status='not_scored', conformance_status='not_assessed',
                spec_sha256=record['spec_sha256'], framework_sha256=record['framework']['sha256'],
                guide_sha256=record['guide']['sha256'], missing_scores=missing,
                evidence_gaps=sorted(set(gaps)), findings=findings(effective_scores),
                declared_scores=scores, effective_scores=effective_scores,
                finding_basis='illustrative_scores' if record['assessment_kind'] == 'illustrative' else 'source_linked_declared_scores',
                effective_unknown_scores=sorted(key for key, score in effective_scores.items() if score is None),
                domain_scores=None, need_score=None, readiness_score=None, maturity_baseline=None,
                limitations=['Only the guide red-flag rules are calculated from declared inputs.',
                             'The companion workbook weights and maturity formula were not supplied.',
                             'Mappings and source hashes do not establish deployed controls or assessor independence.',
                             'No full CROA normative-coverage inventory or conformance claim is produced.'])
