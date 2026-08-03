from pipeline.managers.decodermanager import DecoderManager
from pipeline.registries.decoderregistry import decoder_registry


def test_restart_preserves_decoder_output_directory(monkeypatch):
    """A restart must not move an automated observation back to data/decoded."""

    class DemoDecoder:
        pass

    manager = DecoderManager(
        processes={"sdr-1": {"data_queue": object(), "decoders": {}}},
        demodulator_manager=None,
    )
    captured_kwargs = {}

    monkeypatch.setattr(decoder_registry, "list_decoders", lambda: ["demo"])
    monkeypatch.setattr(decoder_registry, "get_decoder_class", lambda _name: DemoDecoder)
    monkeypatch.setattr(
        manager,
        "start_decoder",
        lambda **kwargs: captured_kwargs.update(kwargs) or True,
    )

    restarted = manager._restart_decoder(
        "sdr-1",
        "internal:observation-1",
        1,
        {
            "decoder_type": "DemoDecoder",
            "config": object(),
            "output_dir": "/tmp/ISS_20260803_120000.gsobs/decoded",
        },
    )

    assert restarted is True
    assert captured_kwargs["output_dir"] == "/tmp/ISS_20260803_120000.gsobs/decoded"
