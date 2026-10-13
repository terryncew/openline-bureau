#!/usr/bin/env python3
"""Validate an append-only data contribution with trusted base-branch code.

Invoke this file FROM the trusted base checkout, never the contribution.
No submitted code, workflows, receipts or remote URLs are executed/fetched.
This guard is not a substitute for required human review of publication scope.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

MAX_FILES = 1000
MAX_FILE_BYTES = 262144
MAX_TOTAL_BYTES = 8 * 1024 * 1024
ALLOWED = ('catalog/submissions/', 'catalog/evidence/')


def tracked(root):
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'],
                            check=True, stdout=subprocess.PIPE)
    names = result.stdout.decode('utf-8').split('\0')
    return {name for name in names if name}


def read(root, name):
    path = root / name
    if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
        raise ValueError('non-regular or escaping contribution file: ' + name)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('file too large: ' + name)
    return path.read_bytes()


def check(base, candidate, author):
    base, candidate = Path(base).resolve(), Path(candidate).resolve()
    base_files, candidate_files = tracked(base), tracked(candidate)
    modified = []
    for name in sorted(base_files | candidate_files):
        # Only differences are considered; existing frozen unrelated files are untouched.
        a = read(base, name) if name in base_files else None
        b = read(candidate, name) if name in candidate_files else None
        if a == b:
            continue
        if not name.startswith(ALLOWED) or not name.endswith('.json'):
            raise ValueError('requires separate maintainer code/policy review: ' + name)
        if a is not None:
            raise ValueError('published contribution history is append-only; add a new version: ' + name)
        modified.append(name)
    if not modified:
        raise ValueError('no new data contributions')
    data_files = sorted(n for n in candidate_files if n.startswith(ALLOWED))
    if len(data_files) > MAX_FILES:
        raise ValueError('too many catalog files')
    total = sum(len(read(candidate, name)) for name in data_files)
    if total > MAX_TOTAL_BYTES:
        raise ValueError('contribution data budget exceeded')
    # Materialize JSON data plus trusted policy, never candidate Python or workflows.
    with tempfile.TemporaryDirectory(prefix='openline-pr-data-') as tmp:
        source = Path(tmp) / 'catalog'
        shutil.copytree(base / 'catalog', source, symlinks=True)
        for name in data_files:
            target = Path(tmp) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                raise ValueError('trusted catalog unexpectedly contains symlink')
            target.write_bytes(read(candidate, name))
        sys.path.insert(0, str(base))
        from bureau.catalog import validate_source
        # The parser receives only data; the base review registry is preserved.
        validate_source(source, pending=True)
        from bureau.catalog import load_json
        for name in modified:
            if not name.startswith('catalog/submissions/'):
                continue
            record = load_json(Path(tmp) / name)
            identity = record.get('evaluator_id') if name.startswith('catalog/submissions/evaluations/') else record.get('contributor_id')
            if not isinstance(identity, str) or identity.casefold() != author.casefold():
                raise ValueError('record contributor must match the actual PR author: ' + name)
    return len(modified)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--author', default=os.environ.get('PR_AUTHOR'), required=False)
    args = parser.parse_args(argv)
    if not args.author:
        parser.error('actual PR author is required')
    try:
        count = check(args.base, args.candidate, args.author)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print('Contribution refused: ' + str(exc), file=sys.stderr)
        return 1
    print(f'Validated {count} new JSON files. Nothing approved or published.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
