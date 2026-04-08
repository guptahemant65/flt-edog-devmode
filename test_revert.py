"""End-to-end test: multi-file patch revert including token_updated path."""
import tempfile, os, subprocess, re, sys
from pathlib import Path

# Add repo to path so we can import edog
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmpdir = tempfile.mkdtemp(prefix='edog_test_')
os.chdir(tmpdir)
subprocess.run(['git', 'init'], capture_output=True)
subprocess.run(['git', 'config', 'user.email', 'test@test.com'], capture_output=True)
subprocess.run(['git', 'config', 'user.name', 'Test'], capture_output=True)

SERVICE = Path('Service/Microsoft.LiveTable.Service')
ENTRY = Path('Service/Microsoft.LiveTable.Service.EntryPoint')

# Create the file structure
files = {
    'ParametersManifest': ENTRY / 'WorkloadParameters/ParametersManifest.json',
    'TestRollout': ENTRY / 'WorkloadParameters/Rollouts/Test.json',
    'Program': ENTRY / 'Program.cs',
}

originals = {
    'ParametersManifest': '{\n  "DisableFLTAuth": false,\n  "Other": "value"\n}\n',
    'TestRollout': '{\n  "WorkspacePool": "WHP_POOL",\n  "FabricPublicApiHost": "https://api.fabric.microsoft.com"\n  }\n}\n',
    'Program': 'using System;\n\nnamespace Test\n{\n    public static class Program\n    {\n        public static async Task Main(string[] args)\n        {\n            await new WorkloadApp().RunAsync(args);\n        }\n    }\n}\n',
}

for key, rel_path in files.items():
    full = Path(tmpdir) / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(originals[key], encoding='utf-8')

subprocess.run(['git', 'add', '.'], capture_output=True)
subprocess.run(['git', 'commit', '-m', 'init'], capture_output=True)

# Test 1: Program.cs apply doesn't create StyleCop issues
print('=== Test 1: Program.cs apply (no StyleCop brace issues) ===')
import importlib.util
spec = importlib.util.spec_from_file_location('edog', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'edog.py'))
edog = importlib.util.module_from_spec(spec)
sys.modules['edog'] = edog

orig_dir = os.getcwd()
os.chdir(os.path.dirname(os.path.abspath(__file__)))
spec.loader.exec_module(edog)
os.chdir(orig_dir)

content = originals['Program']
new_content, status = edog.apply_log_viewer_registration_program_cs(content)
assert status == 'applied', f'Expected applied, got {status}'

# Check no lines have brace+code on same line
fail = False
for i, line in enumerate(new_content.split('\n'), 1):
    stripped = line.strip()
    if stripped.startswith('{') and len(stripped) > 1 and not stripped.startswith('{}'):
        print(f'  FAIL: Line {i} has brace+code: {stripped[:60]}')
        fail = True

# Check revert is clean
reverted = edog.revert_log_viewer_registration_program_cs(new_content)
if reverted != content:
    print(f'  FAIL: Revert does not match original')
    fail = True

if not fail:
    print('  PASS')
else:
    print('  FAILED')

# Test 2: Test.json apply/revert
print('\n=== Test 2: Test.json apply/revert ===')
content = originals['TestRollout']
new_content, status = edog.apply_disable_flt_auth_test_json(content)
assert status == 'applied'
assert '"DisableFLTAuth": true' in new_content
reverted = edog.revert_disable_flt_auth_test_json(new_content)
if reverted == content:
    print('  PASS')
else:
    print(f'  FAIL: reverted != original')
    print(f'    orig:     {repr(content[:100])}')
    print(f'    reverted: {repr(reverted[:100])}')

# Test 3: Full apply -> patch -> revert cycle (first call)
print('\n=== Test 3: Full first-call cycle ===')
# Write originals to disk
for key, rel in files.items():
    (Path(tmpdir) / rel).write_text(originals[key], encoding='utf-8')
subprocess.run(['git', 'add', '.'], capture_output=True)
subprocess.run(['git', 'commit', '-m', 'reset'], capture_output=True)

# Apply Test.json
fp = Path(tmpdir) / files['TestRollout']
c = open(fp, 'r', encoding='utf-8').read()
new_c, _ = edog.apply_disable_flt_auth_test_json(c)
open(fp, 'w', encoding='utf-8').write(new_c)

# Generate patch
import difflib
original_contents = {files['TestRollout']: c}
modified_contents = {files['TestRollout']: new_c}
patch_path = Path(tmpdir) / '.edog-changes.patch'
edog_patch_path = edog.get_patch_file_path
# Use edog's generate_patch
if edog.generate_patch(original_contents, modified_contents, Path(tmpdir)):
    # Move patch to our tmpdir
    src_patch = edog.get_patch_file_path()
    patch_content = src_patch.read_text(encoding='utf-8')
    patch_path.write_text(patch_content, encoding='utf-8')
    src_patch.unlink()

r = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(patch_path)],
                   cwd=tmpdir, capture_output=True, text=True)
final = open(fp, 'r', encoding='utf-8').read()
if r.returncode == 0 and final == originals['TestRollout']:
    print('  PASS')
else:
    print(f'  FAIL: rc={r.returncode} match={final == originals["TestRollout"]}')

# Test 4: Simulate token_updated path patch
print('\n=== Test 4: token_updated patch has pre-EDOG original ===')
# Reset
for key, rel in files.items():
    (Path(tmpdir) / rel).write_text(originals[key], encoding='utf-8')
subprocess.run(['git', 'add', '.'], capture_output=True)
subprocess.run(['git', 'commit', '-m', 'reset2'], capture_output=True)

# Apply Test.json (first call)
fp = Path(tmpdir) / files['TestRollout']
c = open(fp, 'r', encoding='utf-8').read()
new_c, _ = edog.apply_disable_flt_auth_test_json(c)
open(fp, 'w', encoding='utf-8').write(new_c)

# Now simulate second apply_all_changes (token refresh)
c2 = open(fp, 'r', encoding='utf-8').read()
_, status = edog.apply_disable_flt_auth_test_json(c2)
assert status == 'already_applied', f'Expected already_applied, got {status}'

# Compute pre-EDOG original
reverted = edog.revert_disable_flt_auth_test_json(c2)
assert reverted != c2, 'Revert should differ from current'

# Generate patch with reverted as original
original_contents = {files['TestRollout']: reverted}
modified_contents = {files['TestRollout']: c2}
if edog.generate_patch(original_contents, modified_contents, Path(tmpdir)):
    src_patch = edog.get_patch_file_path()
    patch_content = src_patch.read_text(encoding='utf-8')
    patch_path.write_text(patch_content, encoding='utf-8')
    src_patch.unlink()

r = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(patch_path)],
                   cwd=tmpdir, capture_output=True, text=True)
final = open(fp, 'r', encoding='utf-8').read()
if r.returncode == 0 and final == originals['TestRollout']:
    print('  PASS')
else:
    print(f'  FAIL: rc={r.returncode} match={final == originals["TestRollout"]}')

os.chdir('C:\\')
print('\nAll tests done.')

