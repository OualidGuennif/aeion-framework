#!/usr/bin/env python3
"""Reference check of the approvals of one release: gate G12 (AX-G-014).

An approval is a signature over a statement that names one release by digest. Which keys count, with which
method, and how many approvers each risk band needs are declared in the specification (AX-M-020). The release
that governs is the baseline the candidate names, or the candidate itself for a first release.

The verdict is a function of at most three files: the candidate, its approvals and its baseline. It uses no
clock, no network and no shared service, and approvals may be collected in any order and merged by union.
An approval that does not verify is set aside and reported; it never invalidates the approvals that do, so a
damaged or hostile fragment cannot block a release that has the approvers it needs.

This module verifies signatures. It never holds a private key and does not establish that a declared key
belongs to the person an actor record names: that binding is the organization's.
"""
import base64
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from check_package import BANDS, canonical, decode_base64, digest, make_validator, strict_json
import release_diff

FORMAT = 'axiomspec-approvals/0.1'
STATEMENT = 'axiomspec-approval/0.1'
SCHEMA = Path(__file__).resolve().parents[1] / 'schemas/approvals.schema.json'
ORDER = {band: position for position, band in enumerate(BANDS)}
LIMITATIONS = [
    'Signatures are checked against keys the governing release declares. Nothing here proves that a key belongs to the person named.',
    'A first release is governed by its own policy and keys: trust in it comes from pinning its digest, not from this check.',
    'A key removed in a later release still validates the earlier releases it approved; order comes from the release chain, not from a clock.',
]


def statement(spec, actor_id, key_id, method):
    """The exact bytes an approver signs: one release by digest, one actor, one key, one method."""
    return canonical(dict(format=STATEMENT, project_id=spec['project']['id'], version=spec['release']['version'],
                          spec_sha256=digest(canonical(spec)), actor_id=actor_id, key_id=key_id, method=method))


def challenge(message):
    """The WebAuthn challenge for a statement: its SHA-256, base64url without padding."""
    return base64.urlsafe_b64encode(hashlib.sha256(message).digest()).rstrip(b'=').decode('ascii')


def signature_valid(key, message, approval):
    """True when the approval is a valid signature of `message` under `key`.

    ed25519: a raw 64-byte signature of the statement.
    webauthn-es256: a passkey assertion whose challenge is the statement's digest, with the user present and
    verified (fingerprint, face or PIN), signed with ECDSA P-256 over authenticatorData || SHA-256(clientDataJSON).
    """
    public, signature = decode_base64(key['public_key']), decode_base64(approval['signature'])
    extras = (approval['authenticator_data'], approval['client_data_json'])
    if public is None or signature is None:
        return False
    try:
        if key['algorithm'] == 'ed25519':
            if extras != (None, None):
                return False
            ed25519.Ed25519PublicKey.from_public_bytes(public).verify(signature, message)
            return True
        if None in extras:
            return False
        authenticator, client = decode_base64(extras[0]), decode_base64(extras[1])
        if authenticator is None or client is None or len(authenticator) < 37:
            return False
        data = strict_json(client)
        if not isinstance(data, dict) or data.get('type') != 'webauthn.get' or data.get('challenge') != challenge(message):
            return False
        if authenticator[32] & 0x05 != 0x05:  # bit 0: user present; bit 2: user verified
            return False
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public).verify(
            signature, authenticator + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


@lru_cache(maxsize=1)
def validator():
    return make_validator(json.loads(SCHEMA.read_text()))


def required_bands(candidate, baseline, comparison=None):
    """AX-G-014: the bands whose rule this release must meet, each with what put it there.

    The low band is the floor of every release. A requirement the release reaches adds its band. A change to
    the actors, the approval policy or the keys adds all four. `comparison` is the G14 comparison of the two
    releases when the caller already holds it.
    """
    reasons = {'low': ['every release']}
    labels = {}
    for document in (baseline, candidate):
        for node in (document or {}).get('nodes', []):
            if node['kind'] == 'Requirement' and node['status'] == 'active':
                held = labels.get(node['id'], 'low')
                labels[node['id']] = max(held, node['data']['risk'], key=ORDER.get)
    if baseline is None:
        reached = sorted(n['id'] for n in candidate['nodes'] if n['kind'] == 'Requirement' and n['status'] == 'active')
    else:
        comparison = comparison or release_diff.compare(baseline, candidate)
        reached = [r['id'] for r in comparison['risk']['requirements']]
        if (baseline['approval'], baseline['actors']) != (candidate['approval'], candidate['actors']):
            for band in BANDS:
                reasons.setdefault(band, []).append('actors, approval policy or keys changed')
    for rid in reached:
        reasons.setdefault(labels[rid], []).append(rid)
    return {band: reasons[band] for band in BANDS if band in reasons}


def judge(candidate, governing, offered):
    """Each offered approval with the key it names and why it is set aside: (approval, key, None) when it counts."""
    keys = {key['id']: key for key in governing['approval']['keys']}
    actors = {actor['id']: actor for actor in governing['actors']}
    for approval in offered:
        key = keys.get(approval['key_id'])
        if key is None:
            yield approval, None, ('UNKNOWN_APPROVAL_KEY', approval['key_id'], 'The governing release declares no such key.')
            continue
        if key['attests']:
            vouched = actors.get(approval['actor_id'])
            if vouched is None or vouched['type'] == 'service':
                yield approval, key, ('APPROVER_MISMATCH', approval['actor_id'],
                                      'An attesting key vouches for a declared actor that is not a service.')
                continue
        elif approval['actor_id'] != key['actor_id']:
            yield approval, key, ('APPROVER_MISMATCH', approval['actor_id'], 'A personal key approves for its own actor only.')
            continue
        message = statement(candidate, approval['actor_id'], key['id'], key['method'])
        if not signature_valid(key, message, approval):
            yield approval, key, ('INVALID_SIGNATURE', approval['key_id'],
                                  'The signature does not verify for this release, actor, key and method.')
            continue
        yield approval, key, None


def verify(candidate, approvals, baseline=None, comparison=None, validated=False):
    """Return the deterministic G12 report for one release. Status is pass, fail or unknown.

    `comparison` is the G14 comparison of baseline and candidate when the caller already computed it.
    `validated` says every file merged into `approvals` was checked against the schema when it was read.
    """
    if not validated:
        validator().validate(approvals)
    errors = []

    def error(code, subject_id, message):
        errors.append(dict(code=code, subject_id=subject_id, message=message))

    release = dict(project_id=candidate['project']['id'], version=candidate['release']['version'],
                   spec_sha256=digest(canonical(candidate)))
    rejected = []
    report = dict(format='axiomspec-approval-check/0.1', gate='G12', status='unknown', release=release,
                  governed_by=None, required=[], approvals=[], rejected=rejected, errors=errors, limitations=LIMITATIONS)
    previous = candidate['release']['previous']
    if previous is None:
        governing, baseline = candidate, None
    elif baseline is None or digest(canonical(baseline)) != previous['spec_sha256']:
        error('BASELINE_REQUIRED', None, 'The release that governs these approvals is the named baseline; it was not supplied.')
        return report
    else:
        governing = baseline
    report['governed_by'] = dict(version=governing['release']['version'], spec_sha256=digest(canonical(governing)))
    offered = approvals['approvals']
    if {name: approvals[name] for name in release} != release:
        rejected.append(dict(code='APPROVALS_FOR_OTHER_RELEASE', subject_id=None,
                             message='The approvals name another project, version or digest; none was counted.'))
        offered = []
    valid = {}  # actor -> methods that actor validly approved with
    for approval, key, problem in judge(candidate, governing, offered):
        report['approvals'].append(dict(actor_id=approval['actor_id'], key_id=approval['key_id'],
                                        method=key['method'] if key else None, valid=problem is None))
        if problem is None:
            valid.setdefault(approval['actor_id'], set()).add(key['method'])
        else:
            rejected.append(dict(code=problem[0], subject_id=problem[1], message=problem[2]))
    report['approvals'].sort(key=lambda a: (a['actor_id'], a['key_id'], not a['valid']))
    rejected.sort(key=lambda r: (r['code'], r['subject_id'] or ''))
    for band, because in required_bands(candidate, baseline, comparison).items():
        rule = governing['approval']['policy'][band]
        allowed = set(rule['methods'])
        approvers = sorted(actor for actor, methods in valid.items() if not allowed or methods & allowed)
        report['required'].append(dict(band=band, approvers=rule['approvers'], methods=rule['methods'],
                                       valid_approvers=approvers, because=because))
        if len(approvers) < rule['approvers']:
            error('INSUFFICIENT_APPROVALS', None,
                  f"The {band} band needs {rule['approvers']} approver(s) with an accepted method; {len(approvers)} valid.")
    report['status'] = 'fail' if errors else 'pass'
    return report


def counted(candidate, approvals, governing):
    """The approvals of a document that verify under `governing`, in their original order."""
    release = dict(project_id=candidate['project']['id'], version=candidate['release']['version'],
                   spec_sha256=digest(canonical(candidate)))
    if {name: approvals[name] for name in release} != release:
        return []
    return [approval for approval, _, problem in judge(candidate, governing, approvals['approvals']) if problem is None]


def merge(first, second):
    """Union of two approval files of one release. Commutative, associative and idempotent.

    Every distinct approval of either file is kept. Nothing is chosen between two approvals of one actor and
    key, because a merge cannot tell which of them verifies: an approval that does not is set aside by
    `verify`, and it must never take the place of one that does.
    """
    header = lambda doc: {name: doc[name] for name in ('format', 'project_id', 'version', 'spec_sha256')}
    if header(first) != header(second):
        raise ValueError('Approvals of different releases cannot be merged')
    distinct = {canonical(approval): approval for approval in first['approvals'] + second['approvals']}
    return dict(header(first), approvals=[distinct[raw] for raw in sorted(distinct)])


def empty(spec):
    return dict(format=FORMAT, project_id=spec['project']['id'], version=spec['release']['version'],
                spec_sha256=digest(canonical(spec)), approvals=[])


def main(arguments):
    load = lambda name: strict_json(Path(name).read_bytes())
    command = arguments[0] if arguments else None
    if command == 'statement' and len(arguments) == 4:
        spec = load(arguments[1])
        key = next((k for k in spec['approval']['keys'] if k['id'] == arguments[3]), None)
        if spec['release']['previous'] is not None:
            print('Note: the key and method must be declared by the baseline, which governs this release.', file=sys.stderr)
        if key is None:
            print('No such key in this specification.', file=sys.stderr)
            return 4
        message = statement(spec, arguments[2], key['id'], key['method'])
        print(json.dumps(dict(statement=message.decode('utf-8'), sha256=digest(message), webauthn_challenge=challenge(message)), indent=2))
        return 0
    if command == 'verify' and len(arguments) in (3, 4):
        try:
            report = verify(load(arguments[1]), load(arguments[2]), load(arguments[3]) if len(arguments) == 4 else None)
        except Exception as exc:
            print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
            return 4
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return {'pass': 0, 'fail': 2, 'unknown': 3}[report['status']]
    if command == 'merge' and len(arguments) == 4:
        if Path(arguments[3]).exists():
            print('Refusing to overwrite an existing file.', file=sys.stderr)
            return 4
        Path(arguments[3]).write_text(json.dumps(merge(load(arguments[1]), load(arguments[2])), indent=2) + '\n')
        return 0
    print('Usage: python3 qa/approvals.py statement <spec.json> <ACTOR-ID> <KEY-ID>\n'
          '       python3 qa/approvals.py verify <spec.json> <approvals.json> [<baseline.json>]\n'
          '       python3 qa/approvals.py merge <a.json> <b.json> <new-file.json>', file=sys.stderr)
    return 4


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
