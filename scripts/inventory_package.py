#!/usr/bin/env python3
"""盘点资料包，不推断已读内容或需求是否存在；保留 unread 供 Agent 逐份核实。"""
import argparse
import hashlib
import json
from pathlib import Path

SKIP = {'.git', '.venv', '__pycache__', '.DS_Store'}


def inventory(root, output=None):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('资料包必须是目录')
    output = Path(output).resolve() if output else None
    sources = []
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if any(part in SKIP for part in rel.parts) or path.resolve() == output:
            continue
        if not path.is_file() and not path.is_symlink():
            continue
        entry = {'id': 'SRC-' + hashlib.sha256(str(rel).encode()).hexdigest()[:12],
                 'locator': str(rel), 'revision': 'unknown', 'role': 'unclassified',
                 'read_status': 'unread', 'required': True, 'extension': path.suffix.lower()}
        if path.is_symlink() or any((root / parent).is_symlink() for parent in rel.parents):
            entry.update(read_status='error', error='符号链接未读取；确认边界后另行纳入')
        else:
            try:
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(chunk)
                entry.update(sha256=digest.hexdigest(), size_bytes=path.stat().st_size)
            except OSError as exc:
                entry.update(read_status='error', error=str(exc))
        sources.append(entry)
    return {'root': str(root), 'routing': 'UNDETERMINED', 'sources': sources,
            'notice': '文件名/后缀仅定位格式；须阅读内容和引用附件后设置角色及路由。'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('--json', required=True)
    args = parser.parse_args()
    try:
        value = inventory(args.directory, args.json)
        Path(args.json).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}')
        return 2
    print(f"盘点 {len(value['sources'])} 份文件；内容未读，路由未定")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
