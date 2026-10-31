"""Data-only user extension registry. Never execute code while discovering tools.

Installed extension descriptions are independent of the application install directory,
so updating Mint Toolbox never overwrites a user's registrations.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

ID_RE = re.compile(r'^user-[a-z][a-z0-9_-]{0,48}$')
FIELD_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}$')
FIELD_KINDS = {'text', 'file', 'folder', 'file_or_folder', 'boolean'}
SEVERITIES = {'low', 'medium', 'high', 'critical'}


def config_dir() -> Path:
    base = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))).expanduser()
    return base / 'mint-toolbox'


def extension_dir() -> Path:
    return config_dir() / 'extensions'


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError('Refusing to modify a symbolic-link configuration file')
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                     prefix='.mint-toolbox-', delete=False) as handle:
        tmp = Path(handle.name)
        os.fchmod(handle.fileno(), 0o600)
        try:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _limited_text(value: Any, label: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f'Invalid extension field: {label}')
    return value.strip()


def validate_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get('schema_version') != 1:
        raise ValueError('Extension manifest must use schema_version=1')
    key = raw.get('id')
    if not isinstance(key, str) or not ID_RE.fullmatch(key):
        raise ValueError('Extension ID must be a safe identifier beginning with user-')
    data = dict(raw)
    for field in ('name', 'category', 'description', 'executable'):
        data[field] = _limited_text(data.get(field), field, max_length=2048 if field == 'executable' else 500)
    source = Path(data['executable']).expanduser()
    if not source.is_absolute():
        raise ValueError('executable must be an absolute path')
    data['executable'] = str(source)
    manual = data.get('manual')
    if manual:
        if not isinstance(manual, str) or len(manual) > 2048 or not Path(manual).expanduser().is_absolute():
            raise ValueError('manual must be an absolute HTML/Markdown path')
        if Path(manual).suffix.lower() not in {'.md', '.html', '.htm'}:
            raise ValueError('manual only accepts .md or .html')
    else:
        data.pop('manual', None)
    severity = data.get('risk', 'medium')
    if severity not in SEVERITIES:
        raise ValueError('risk must be low/medium/high/critical')
    data['risk'] = severity
    actions = data.get('actions', [{'key':'start','label':'Launch tool','fields':[],'argv':[],'severity':'medium'}])
    if not isinstance(actions, list) or len(actions) > 20:
        raise ValueError('actions must be a list of at most 20 items')
    validated = []
    action_keys = set()
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError('action must be an object')
        action_key = _limited_text(action.get('key'), 'action.key', max_length=40)
        if not FIELD_RE.fullmatch(action_key) or action_key in action_keys:
            raise ValueError('Invalid or duplicate action key')
        action_keys.add(action_key)
        label = _limited_text(action.get('label'), 'action.label')
        fields = action.get('fields', [])
        if not isinstance(fields, list) or len(fields) > 15:
            raise ValueError('fields must be a list of at most 15 items')
        validated_fields = []
        field_keys = set()
        for f in fields:
            if not isinstance(f, dict):
                raise ValueError('Fields must be objects')
            field_key = _limited_text(f.get('key'), 'field.key', max_length=40)
            if not FIELD_RE.fullmatch(field_key) or field_key in field_keys:
                raise ValueError('Invalid or duplicate field key')
            field_keys.add(field_key)
            kind = f.get('kind', 'text')
            if kind not in FIELD_KINDS:
                raise ValueError('Unknown field type')
            default = f.get('default', '')
            if not isinstance(default, str) or len(default) > 2048:
                raise ValueError('Invalid default value')
            validated_fields.append({'key':field_key,
                                     'label':_limited_text(f.get('label'), 'field.label'),
                                     'kind':kind, 'required':bool(f.get('required', True)),
                                     'default':default})
        argv = action.get('argv', [])
        if not isinstance(argv, list) or len(argv) > 100:
            raise ValueError('argv must be a list of at most 100 items')
        for token in argv:
            if isinstance(token, str):
                if len(token) > 2048 or not token or token.count('{') or token.count('}'):
                    raise ValueError('argv strings must be literals; use field objects for dynamic input')
            elif isinstance(token, dict):
                if set(token) - {'field', 'flag'} or token.get('field') not in field_keys:
                    raise ValueError('argv field must reference a declared field')
                flag = token.get('flag', '')
                if not isinstance(flag, str) or len(flag) > 100 or '\n' in flag:
                    raise ValueError('Invalid argv flag')
                if flag and not flag.startswith('-'):
                    raise ValueError('argv flag must begin with -')
            else:
                raise ValueError('argv only accepts strings or field objects')
        action_risk = action.get('severity', severity)
        if action_risk not in SEVERITIES:
            raise ValueError('Unknown action risk level')
        validated.append({'key':action_key, 'label':label, 'fields':validated_fields,
                          'argv':argv, 'severity':action_risk,
                          'note':str(action.get('note', ''))[:1000]})
    data['actions'] = validated
    data['schema_version'] = 1
    return data


def load_extensions() -> tuple[list[dict[str, Any]], list[str]]:
    directory = extension_dir()
    if not directory.is_dir() or directory.is_symlink():
        return [], []
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for file in sorted(directory.glob('user-*.json'))[:300]:
        try:
            if file.is_symlink() or file.stat().st_size > 65536:
                raise ValueError('Invalid or oversized extension file')
            item = validate_manifest(json.loads(file.read_text('utf-8')))
            if file.stem != item['id']:
                raise ValueError('Extension ID does not match its filename')
            item.update(origin='extension', status='User tools', show=True,
                        lifecycle='available' if Path(item['executable']).is_file() else 'unavailable',
                        source='user')
            results.append(item)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            errors.append(f'{file.name}: {e}')
    return results, errors


def add_extension(executable: str, *, name: str | None = None,
                  category: str = 'User tools', description: str | None = None,
                  manual: str | None = None) -> dict[str, Any]:
    source = Path(executable).expanduser().absolute()
    if not source.is_file():
        raise ValueError('Select an existing script or executable file')
    if manual and not Path(manual).expanduser().is_file():
        raise ValueError('Selected manual does not exist')
    stem = re.sub(r'[^a-z0-9_-]+', '-', source.stem.lower()).strip('-_')[:28]
    if not stem or not stem[0].isalpha():
        stem = 'tool'
    fingerprint = hashlib.sha256(str(source).encode('utf-8')).hexdigest()[:10]
    key = f'user-{stem}-{fingerprint}'
    payload = validate_manifest({'schema_version': 1, 'id': key,
                                 'name': name or source.stem, 'category':category,
                                 'description': description or f'Run {source.name}',
                                 'executable':str(source),
                                 'risk':'medium',
                                 'actions':[{'key':'start','label':'Launch tool','fields':[],
                                             'argv':[],'severity':'medium',
                                             'note':'User-provided script. Verify its source before running it.'}],
                                 **({'manual':str(Path(manual).expanduser().absolute())} if manual else {})})
    location = extension_dir() / (key + '.json')
    if location.exists() or location.is_symlink():
        raise FileExistsError('This script is already registered; existing registration was not overwritten')
    # Exclusive creation; do not overwrite even when the destination races into existence.
    location.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    fd = os.open(location, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(encoded)
    return payload


def remove_extension(tool_id: str) -> None:
    if not ID_RE.fullmatch(tool_id):
        raise ValueError('Only user tools can be unregistered')
    file = extension_dir() / (tool_id + '.json')
    if file.is_symlink() or not file.is_file():
        raise FileNotFoundError('User tool not found')
    file.unlink()


def _get_overrides() -> dict:
    path = config_dir() / 'state.json'
    if not path.exists():
        return {}
    if path.is_symlink() or path.stat().st_size > 65536:
        raise ValueError('Invalid local state file')
    data = json.loads(path.read_text('utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Invalid local state structure')
    return data


def is_removed(tool_id: str) -> bool:
    return _get_overrides().get(tool_id) == 'removed'


def is_restored(tool_id: str) -> bool:
    return _get_overrides().get(tool_id) == 'restored'


def mark_removed(tool_id: str, removed: bool = True) -> None:
    state = _get_overrides()
    if removed:
        state[tool_id] = 'removed'
    else:
        state[tool_id] = 'restored'
    _atomic_json(config_dir() / 'state.json', state)


def disabled_tool_ids() -> set[str]:
    """Load independent enabled/disabled state; preserve legacy removal state."""
    path = config_dir() / 'disabled.json'
    if not path.exists():
        return set()
    if path.is_symlink() or path.stat().st_size > 65536:
        raise ValueError('Invalid disabled-state file')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or any(not isinstance(k, str) or v is not True
                                           for k, v in value.items()):
        raise ValueError('Invalid disabled-state structure')
    return set(value)


def is_disabled(tool_id: str) -> bool:
    return tool_id in disabled_tool_ids()


def set_disabled(tool_id: str, disabled: bool = True) -> None:
    """Toggle usability without removing tool registration, file or manual."""
    if (not isinstance(tool_id, str) or not tool_id or len(tool_id) > 150
            or '/' in tool_id or '\\' in tool_id or any(ord(c) < 32 for c in tool_id)):
        raise ValueError('Invalid tool identifier')
    state = {key: True for key in disabled_tool_ids()}
    if disabled:
        state[tool_id] = True
    else:
        state.pop(tool_id, None)
    _atomic_json(config_dir() / 'disabled.json', state)
