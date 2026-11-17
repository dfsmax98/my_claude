# -*- coding: utf-8 -*-
"""ModelScope 模型引用解析，优先复用项目内离线缓存。"""
import os
from pathlib import Path


MODEL_REPOS = {
    "cam++": "iic--speech_campplus_sv_zh-cn_16k-common",
    "paraformer-zh": "iic--speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    "fsmn-vad": "iic--speech_fsmn_vad_zh-cn-16k-common-pytorch",
    "ct-punc": "iic--punc_ct-transformer_cn-en-common-vocab471067-large",
}


def resolve_model(name):
    """返回本地快照目录；缓存不存在时保留原模型别名。"""
    repo = MODEL_REPOS.get(name)
    if repo is None:
        return name

    project_root = Path(__file__).resolve().parents[2]
    project_cache = project_root / "models" / "runtime" / "modelscope"
    cache_roots = []
    configured = os.environ.get("MODELSCOPE_CACHE")
    if configured:
        cache_roots.append(Path(configured).expanduser())
    cache_roots.append(project_cache)

    for cache_root in cache_roots:
        snapshots = cache_root / "models" / repo / "snapshots"
        master = snapshots / "master"
        if master.is_dir():
            return str(master)
        if snapshots.is_dir():
            candidates = sorted(p for p in snapshots.iterdir() if p.is_dir())
            if candidates:
                return str(candidates[-1])
    return name
