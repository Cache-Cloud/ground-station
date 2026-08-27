import threading

import numpy as np
import pytest

from common.iqsamples import require_complex64
from demodulators.iqrecorder import IQRecorder


def test_require_complex64_accepts_complex_array():
    samples = np.array([1 + 2j, -0.25 + 0.5j], dtype=np.complex64)
    out = require_complex64(samples, source="test")
    assert out.dtype == np.complex64
    np.testing.assert_allclose(out, samples)


def test_require_complex64_casts_complex128_to_complex64():
    samples = np.array([1 + 2j, -0.25 + 0.5j], dtype=np.complex128)
    out = require_complex64(samples, source="test")
    assert out.dtype == np.complex64
    np.testing.assert_allclose(out, samples.astype(np.complex64))


def test_require_complex64_rejects_non_complex_input():
    samples = np.array([0, 255, 128, 127], dtype=np.uint8)
    with pytest.raises(TypeError):
        require_complex64(samples, source="test")


def test_ci16_iq_encoding_interleaves_and_records_clipping():
    recorder = object.__new__(IQRecorder)
    recorder.storage_format = "ci16_le"
    recorder.stats_lock = threading.Lock()
    recorder.stats = {
        "peak_component_magnitude": 0.0,
        "quantization_clipped_components": 0,
    }

    encoded = recorder._encode_samples(np.array([0.5 - 0.5j, 1.25 - 1.5j], dtype=np.complex64))

    assert encoded.dtype == np.dtype("<i2")
    np.testing.assert_array_equal(encoded, np.array([16384, -16384, 32767, -32767], dtype="<i2"))
    assert recorder.stats["quantization_clipped_components"] == 2
    assert recorder.stats["peak_component_magnitude"] == 1.5
