# -*- coding: utf-8 -*-
"""拆分双声道并增量落盘 ASR 文本，支持中断后续跑。"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from common import asr_role, audio_io


def _atomic_write_json(path, value):
    path = Path(path)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def _load_role_checkpoint(path):
    if path is None:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload.get("records", {})


def _write_markdown(path, records, roles, duration):
    lines = [
        "# 双声道 ASR 转录文本",
        "",
        f"> 每通录音从起点截取前 {duration:g} 秒；L/R 独立转录，结果按声道增量落盘。",
        "",
    ]
    recording_ids = sorted({item["recording_id"] for item in records.values()})
    for recording_id in recording_ids:
        role = roles.get(recording_id, {})
        lines.extend([f"## 通话 {recording_id}", ""])
        if role:
            lines.extend([
                f"- 当前角色判断：客户={role.get('customer_ch')}，客服={role.get('agent_ch')}",
                f"- 置信度：{role.get('confidence')}，阶段={role.get('final_stage')}，"
                f"待复核={role.get('needs_review')}",
                "",
            ])
        for channel in ("L", "R"):
            key = f"{recording_id}_{channel}"
            item = records.get(key)
            if item is None:
                continue
            lines.extend([
                f"### 声道 {channel}",
                "",
                item.get("text") or "（无有效语音）",
                "",
            ])
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def export_transcripts(source_dir, output_dir, recording_ids, roles=None, duration=30):
    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    channel_dir = output_dir / "channels"
    output_dir.mkdir(parents=True, exist_ok=True)
    channel_dir.mkdir(parents=True, exist_ok=True)
    roles = roles or {}
    checkpoint_path = output_dir / "transcriptions.json"
    report_path = output_dir / "转录文本.md"
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    else:
        checkpoint = {"duration_sec": duration, "records": {}, "failures": {}}
    if float(checkpoint.get("duration_sec", duration)) != float(duration):
        raise ValueError("已有转录检查点的截取时长与本次参数不一致")
    records = checkpoint.setdefault("records", {})
    failures = checkpoint.setdefault("failures", {})
    model = asr_role.get_model()

    total = len(recording_ids) * 2
    completed = 0
    for recording_id in recording_ids:
        source = source_dir / f"{recording_id}.mp3"
        for channel_index, channel in ((0, "L"), (1, "R")):
            completed += 1
            key = f"{recording_id}_{channel}"
            if key in records:
                print(f"[{completed}/{total}] CACHE {key}", flush=True)
                continue
            wav_path = channel_dir / f"{key}.wav"
            try:
                audio_io.extract_channel(
                    str(source), channel_index, str(wav_path), dur=duration)
                result = model.generate(
                    input=str(wav_path), batch_size_s=300, disable_pbar=True,
                    sentence_timestamp=True)
                item = result[0] if isinstance(result, list) and result else result
                item = item if isinstance(item, dict) else {}
                summary = asr_role.summarize_result(result)
                records[key] = {
                    "recording_id": recording_id,
                    "channel": channel,
                    "wav": str(Path("channels") / wav_path.name),
                    "text": str(item.get("text", "")).strip(),
                    "summary": summary,
                }
                failures.pop(key, None)
                print(f"[{completed}/{total}] OK {key} chars={summary['char_count']}", flush=True)
            except Exception as exc:
                failures[key] = {
                    "recording_id": recording_id,
                    "channel": channel,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                print(f"[{completed}/{total}] FAIL {key}: {exc}", flush=True)
            _atomic_write_json(checkpoint_path, checkpoint)
            _write_markdown(report_path, records, roles, duration)
    return checkpoint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--role-checkpoint", default=None)
    parser.add_argument(
        "--recording-id", action="append", default=None,
        help="仅导出指定录音ID；可重复传入多次",
    )
    args = parser.parse_args()

    roles = _load_role_checkpoint(args.role_checkpoint)
    if args.recording_id:
        recording_ids = sorted(set(args.recording_id))
    elif roles:
        recording_ids = sorted(roles)
    else:
        recording_ids = sorted(path.stem for path in Path(args.source_dir).glob("*.mp3"))
    if args.limit is not None:
        recording_ids = recording_ids[:args.limit]
    if not recording_ids:
        raise SystemExit("没有可处理的录音")
    result = export_transcripts(
        args.source_dir, args.output_dir, recording_ids, roles=roles,
        duration=args.duration)
    print(
        f"DONE recordings={len(recording_ids)} channels={len(result['records'])} "
        f"failures={len(result['failures'])}", flush=True)


if __name__ == "__main__":
    main()
