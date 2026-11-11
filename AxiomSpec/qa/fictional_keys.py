#!/usr/bin/env python3
"""Fictional signing keys for the worked examples and the tests. They authenticate nobody.

Each private key is derived from a public label, so anyone can reproduce it: that is the point. A real
approver signs on their own device or through their organization's approval service, and the private key
never appears in a repository. The passkey case simulates an authenticator; no hardware was involved.
"""
import base64
import hashlib
import json
from pathlib import Path
import sys

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

import approvals
from check_package import strict_json

ORIGIN = 'https://approvals.axiomspec.invalid'
P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


def seed(label):
    return hashlib.sha256(('AxiomSpec fictional example key: ' + label).encode('utf-8')).digest()


def private_key(algorithm, label):
    if algorithm == 'ed25519':
        return ed25519.Ed25519PrivateKey.from_private_bytes(seed(label))
    return ec.derive_private_key(int.from_bytes(seed(label), 'big') % (P256_ORDER - 1) + 1, ec.SECP256R1())


def public_key(algorithm, label):
    """The base64 public key a specification declares for this fictional key."""
    public = private_key(algorithm, label).public_key()
    if algorithm == 'ed25519':
        raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    else:
        raw = public.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.b64encode(raw).decode('ascii')


def approve(spec, governing, actor_id, key_id, label=None, user_verified=True):
    """One approval of `spec` by a fictional key that `governing` declares."""
    key = next(k for k in governing['approval']['keys'] if k['id'] == key_id)
    signer = private_key(key['algorithm'], label or f"{governing['project']['id']}/{key_id}")
    message = approvals.statement(spec, actor_id, key_id, key['method'])
    encode = lambda raw: base64.b64encode(raw).decode('ascii')
    if key['algorithm'] == 'ed25519':
        return dict(actor_id=actor_id, key_id=key_id, signature=encode(signer.sign(message)),
                    authenticator_data=None, client_data_json=None)
    client = json.dumps(dict(type='webauthn.get', challenge=approvals.challenge(message), origin=ORIGIN,
                             crossOrigin=False), separators=(',', ':')).encode('utf-8')
    flags = 0x05 if user_verified else 0x01
    authenticator = hashlib.sha256(ORIGIN.split('//')[1].encode()).digest() + bytes([flags]) + (0).to_bytes(4, 'big')
    signature = signer.sign(authenticator + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
    return dict(actor_id=actor_id, key_id=key_id, signature=encode(signature),
                authenticator_data=encode(authenticator), client_data_json=encode(client))


def approvals_for(spec, governing, signers):
    """An approvals document for `spec` signed by (actor_id, key_id) pairs."""
    document = approvals.empty(spec)
    document['approvals'] = [approve(spec, governing, actor, key) for actor, key in signers]
    return approvals.merge(document, document)


def main(arguments):
    if len(arguments) < 4 or len(arguments) % 2:
        print('Usage: python3 qa/fictional_keys.py <spec.json> <governing.json> <new-approvals.json> <ACTOR-ID> <KEY-ID> [...]\n'
              'Signs with fictional keys derived from public labels. Never use for a real approval.', file=sys.stderr)
        return 4
    spec, governing = (strict_json(Path(name).read_bytes()) for name in arguments[:2])
    document = approvals_for(spec, governing, list(zip(arguments[3::2], arguments[4::2])))
    Path(arguments[2]).write_text(json.dumps(document, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
