from pathlib import Path

import pytest


@pytest.fixture
def smb_conf() -> str:
    return (Path(__file__).parent.parent / "conf" / "smb.conf").read_text()


class TestSambaConfig:
    def test_config_exists(self, smb_conf: str) -> None:
        assert len(smb_conf) > 0

    def test_config_has_share(self, smb_conf: str) -> None:
        assert "[vault]" in smb_conf

    def test_config_has_path(self, smb_conf: str) -> None:
        assert "path = /mnt/vault" in smb_conf

    def test_config_has_workgroup(self, smb_conf: str) -> None:
        assert "workgroup = VAULTFS" in smb_conf

    def test_config_has_valid_users(self, smb_conf: str) -> None:
        assert "valid users" in smb_conf

    def test_config_no_guest(self, smb_conf: str) -> None:
        assert "guest ok = no" in smb_conf

    def test_config_has_create_mask(self, smb_conf: str) -> None:
        assert "create mask = 0644" in smb_conf

    def test_config_has_directory_mask(self, smb_conf: str) -> None:
        assert "directory mask = 0755" in smb_conf

    def test_docker_compose_has_samba(self) -> None:
        compose = (Path(__file__).parent.parent / "docker-compose.yml").read_text()
        assert "samba:" in compose
        assert "dperson/samba" in compose

    def test_docker_compose_has_mount(self) -> None:
        compose = (Path(__file__).parent.parent / "docker-compose.yml").read_text()
        assert "/mnt/vault" in compose
