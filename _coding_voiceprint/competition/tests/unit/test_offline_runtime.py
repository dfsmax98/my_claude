# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from common import audio_io
from common.model_paths import MODEL_REPOS, resolve_model


class OfflineRuntimeTest(unittest.TestCase):
    def test_resolve_model_prefers_configured_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = (Path(temp_dir) / "models" / MODEL_REPOS["cam++"] /
                        "snapshots" / "master")
            snapshot.mkdir(parents=True)
            with mock.patch.dict(os.environ, {"MODELSCOPE_CACHE": temp_dir}):
                self.assertEqual(resolve_model("cam++"), str(snapshot))

    def test_extract_channel_without_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "stereo.wav"
            output = Path(temp_dir) / "right.wav"
            sample_rate = 8000
            t = np.arange(sample_rate, dtype=np.float32) / sample_rate
            stereo = np.column_stack([
                np.sin(2 * np.pi * 220 * t),
                np.sin(2 * np.pi * 440 * t),
            ])
            sf.write(source, stereo, sample_rate)

            with mock.patch.object(audio_io, "FFMPEG", None):
                audio_io.extract_channel(str(source), 1, str(output))

            info = sf.info(output)
            self.assertEqual(info.channels, 1)
            self.assertEqual(info.samplerate, 16000)
            self.assertAlmostEqual(info.duration, 1.0, places=2)


if __name__ == "__main__":
    unittest.main()
