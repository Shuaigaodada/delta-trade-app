from pathlib import Path
import importlib.metadata as metadata
import json, re, sys

root = Path(__file__).resolve().parents[1]
expected_prefix = root / '.venv'
if Path(sys.prefix).resolve() != expected_prefix.resolve():
    raise SystemExit('Use the migrated project environment interpreter')
def normalize(s):
    return re.sub('[-_.]+', '-', s).lower()
installed = {normalize(d.metadata['Name']): d.version for d in metadata.distributions()}
missing, mismatched = [], []
raw_requirements = (root / 'requirements.txt').read_bytes()
requirements = raw_requirements.decode('utf-16' if raw_requirements.startswith((bytes([255,254]), bytes([254,255]))) else 'utf-8-sig')
for line in requirements.splitlines():
    if not line.strip() or line.lstrip().startswith('#'):
        continue
    match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)', line.strip())
    if not match:
        raise SystemExit('Requirements format requires review')
    name, expected = match.groups()
    current = installed.get(normalize(name))
    if current is None:
        missing.append({'name': name, 'required': expected})
    elif current != expected:
        mismatched.append({'name': name, 'required': expected, 'installed': current})
print(json.dumps({'project': root.name, 'prefix': sys.prefix, 'base_prefix': sys.base_prefix,
                  'missing': missing, 'mismatched': mismatched, 'ready': not missing and not mismatched}))
raise SystemExit(2 if missing or mismatched else 0)
