from pathlib import Path

import virt_lightning.configuration

def test_default(monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(
            virt_lightning.configuration,
            "DEFAULT_CONFIGFILE",
            Path("a"))
        config = virt_lightning.configuration.Configuration()
        assert config.root_password == "root"

def test_load_file(monkeypatch, config_file):
    with monkeypatch.context() as m:
        m.setattr(
            virt_lightning.configuration,
            "DEFAULT_CONFIGFILE",
            Path("a"))
        config = virt_lightning.configuration.Configuration()
        config.load_file(config_file)
        assert config.root_password == "boby"


def test_load_default_config_file(monkeypatch, config_file):
    with monkeypatch.context() as m:
        m.setattr(
            virt_lightning.configuration,
            "DEFAULT_CONFIGFILE",
            config_file)
        config = virt_lightning.configuration.Configuration()
        assert config.root_password == "boby"
