# -*- coding: utf-8 -*-
"""
轻量 .env 加载器 (纯标准库, 无需 python-dotenv)。

从调用文件所在目录向上逐级查找 .env, 找到即加载其中的 KEY=VALUE 到 os.environ
(不覆盖已存在的环境变量, 便于 CI/生产用真正的环境变量覆盖本地 .env)。

用法(在需要读取凭证的模块顶部):
    from env_loader import load_env
    load_env(__file__)
"""
import os


def load_env(start_path=None, max_up=5):
    """从 start_path 所在目录向上查找并加载 .env。返回加载的 .env 路径或 None。"""
    if start_path is None:
        start_path = os.getcwd()
    d = os.path.dirname(os.path.abspath(start_path))
    for _ in range(max_up + 1):
        env_path = os.path.join(d, '.env')
        if os.path.isfile(env_path):
            _parse_into_environ(env_path)
            return env_path
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def _parse_into_environ(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            key, val = key.strip(), val.strip()
            # 去掉可能的引号
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            # 不覆盖已存在的环境变量(生产环境变量优先)
            if key and key not in os.environ:
                os.environ[key] = val
