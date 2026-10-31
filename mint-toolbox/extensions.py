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
        raise ValueError('拒绝修改符号链接配置文件')
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
        raise ValueError(f'无效扩展字段：{label}')
    return value.strip()


def validate_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get('schema_version') != 1:
        raise ValueError('扩展清单格式必须是 schema_version=1')
    key = raw.get('id')
    if not isinstance(key, str) or not ID_RE.fullmatch(key):
        raise ValueError('扩展 ID 必须是 user- 开头的安全英文标识符')
    data = dict(raw)
    for field in ('name', 'category', 'description', 'executable'):
        data[field] = _limited_text(data.get(field), field, max_length=2048 if field == 'executable' else 500)
    source = Path(data['executable']).expanduser()
    if not source.is_absolute():
        raise ValueError('executable 必须是绝对路径')
    data['executable'] = str(source)
    manual = data.get('manual')
    if manual:
        if not isinstance(manual, str) or len(manual) > 2048 or not Path(manual).expanduser().is_absolute():
            raise ValueError('manual 必须是 HTML/Markdown 文件的绝对路径')
        if Path(manual).suffix.lower() not in {'.md', '.html', '.htm'}:
            raise ValueError('manual 仅接受 .md 或 .html')
    else:
        data.pop('manual', None)
    severity = data.get('risk', 'medium')
    if severity not in SEVERITIES:
        raise ValueError('risk 应为 low/medium/high/critical')
    data['risk'] = severity
    actions = data.get('actions', [{'key':'start','label':'启动工具','fields':[],'argv':[],'severity':'medium'}])
    if not isinstance(actions, list) or len(actions) > 20:
        raise ValueError('actions 必须是最多 20 项的列表')
    validated = []
    action_keys = set()
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError('action 必须是对象')
        action_key = _limited_text(action.get('key'), 'action.key', max_length=40)
        if not FIELD_RE.fullmatch(action_key) or action_key in action_keys:
            raise ValueError('操作 key 无效或重复')
        action_keys.add(action_key)
        label = _limited_text(action.get('label'), 'action.label')
        fields = action.get('fields', [])
        if not isinstance(fields, list) or len(fields) > 15:
            raise ValueError('fields 必须是最多 15 项的列表')
        validated_fields = []
        field_keys = set()
        for f in fields:
            if not isinstance(f, dict):
                raise ValueError('字段必须是对象')
            field_key = _limited_text(f.get('key'), 'field.key', max_length=40)
            if not FIELD_RE.fullmatch(field_key) or field_key in field_keys:
                raise ValueError('字段 key 无效或重复')
            field_keys.add(field_key)
            kind = f.get('kind', 'text')
            if kind not in FIELD_KINDS:
                raise ValueError('未知字段类型')
            default = f.get('default', '')
            if not isinstance(default, str) or len(default) > 2048:
                raise ValueError('默认值不合法')
            validated_fields.append({'key':field_key,
                                     'label':_limited_text(f.get('label'), 'field.label'),
                                     'kind':kind, 'required':bool(f.get('required', True)),
                                     'default':default})
        argv = action.get('argv', [])
        if not isinstance(argv, list) or len(argv) > 100:
            raise ValueError('argv 必须是最多 100 项的列表')
        for token in argv:
            if isinstance(token, str):
                if len(token) > 2048 or not token or token.count('{') or token.count('}'):
                    raise ValueError('argv 字符串必须是普通字面量；动态输入使用 field 对象')
            elif isinstance(token, dict):
                if set(token) - {'field', 'flag'} or token.get('field') not in field_keys:
                    raise ValueError('argv field 必须引用已声明的字段')
                flag = token.get('flag', '')
                if not isinstance(flag, str) or len(flag) > 100 or '\n' in flag:
                    raise ValueError('argv flag 无效')
                if flag and not flag.startswith('-'):
                    raise ValueError('argv flag 必须以 - 开头')
            else:
                raise ValueError('argv 只支持字符串或字段对象')
        action_risk = action.get('severity', severity)
        if action_risk not in SEVERITIES:
            raise ValueError('未知操作风险等级')
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
                raise ValueError('无效的扩展文件或文件过大')
            item = validate_manifest(json.loads(file.read_text('utf-8')))
            if file.stem != item['id']:
                raise ValueError('扩展 ID 与文件名不匹配')
            item.update(origin='extension', status='用户扩展', show=True,
                        lifecycle='available' if Path(item['executable']).is_file() else 'unavailable',
                        source='user')
            results.append(item)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            errors.append(f'{file.name}: {e}')
    return results, errors


def add_extension(executable: str, *, name: str | None = None,
                  category: str = '用户扩展', description: str | None = None,
                  manual: str | None = None) -> dict[str, Any]:
    source = Path(executable).expanduser().absolute()
    if not source.is_file():
        raise ValueError('请选择实际存在的脚本或可执行文件')
    if manual and not Path(manual).expanduser().is_file():
        raise ValueError('找不到所选手册文件')
    stem = re.sub(r'[^a-z0-9_-]+', '-', source.stem.lower()).strip('-_')[:28]
    if not stem or not stem[0].isalpha():
        stem = 'tool'
    fingerprint = hashlib.sha256(str(source).encode('utf-8')).hexdigest()[:10]
    key = f'user-{stem}-{fingerprint}'
    payload = validate_manifest({'schema_version': 1, 'id': key,
                                 'name': name or source.stem, 'category':category,
                                 'description': description or f'运行 {source.name}',
                                 'executable':str(source),
                                 'risk':'medium',
                                 'actions':[{'key':'start','label':'启动工具','fields':[],
                                             'argv':[],'severity':'medium',
                                             'note':'用户自行添加的脚本；请确认来源可信。'}],
                                 **({'manual':str(Path(manual).expanduser().absolute())} if manual else {})})
    location = extension_dir() / (key + '.json')
    if location.exists() or location.is_symlink():
        raise FileExistsError('此脚本已注册，不会覆盖现有扩展')
    # Exclusive creation; do not overwrite even when the destination races into existence.
    location.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    fd = os.open(location, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(encoded)
    return payload


def remove_extension(tool_id: str) -> None:
    if not ID_RE.fullmatch(tool_id):
        raise ValueError('仅允许移除用户扩展')
    file = extension_dir() / (tool_id + '.json')
    if file.is_symlink() or not file.is_file():
        raise FileNotFoundError('没有找到用户扩展')
    file.unlink()


def _get_overrides() -> dict:
    path = config_dir() / 'state.json'
    if not path.exists():
        return {}
    if path.is_symlink() or path.stat().st_size > 65536:
        raise ValueError('本地状态文件无效')
    data = json.loads(path.read_text('utf-8'))
    if not isinstance(data, dict):
        raise ValueError('本地状态结构无效')
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
        raise ValueError('禁用状态文件无效')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or any(not isinstance(k, str) or v is not True
                                           for k, v in value.items()):
        raise ValueError('禁用状态结构无效')
    return set(value)


def is_disabled(tool_id: str) -> bool:
    return tool_id in disabled_tool_ids()


def set_disabled(tool_id: str, disabled: bool = True) -> None:
    """Toggle usability without removing tool registration, file or manual."""
    if (not isinstance(tool_id, str) or not tool_id or len(tool_id) > 150
            or '/' in tool_id or '\\' in tool_id or any(ord(c) < 32 for c in tool_id)):
        raise ValueError('无效工具标识符')
    state = {key: True for key in disabled_tool_ids()}
    if disabled:
        state[tool_id] = True
    else:
        state.pop(tool_id, None)
    _atomic_json(config_dir() / 'disabled.json', state)
