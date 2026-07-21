import pytest

from vaultfs.domain.chunk_policy import DefaultChunkPolicy


@pytest.fixture
def policy() -> DefaultChunkPolicy:
    return DefaultChunkPolicy()


class TestDefaultChunkPolicy:
    def test_directory_returns_zero(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(type="directory") == 0

    def test_default_size(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(type="file") == 65536

    def test_default_size_with_unknown_ext(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(type="file", name="test.xyz") == 65536

    def test_mkv_gets_16mb(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(type="file", name="video.mkv") == 16 * 1024 * 1024

    def test_mp4_gets_16mb(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(type="file", name="video.mp4") == 16 * 1024 * 1024

    def test_iso_gets_32mb(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(type="file", name="backup.iso") == 32 * 1024 * 1024

    def test_zip_gets_16mb(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(type="file", name="archive.zip") == 16 * 1024 * 1024

    def test_mp3_gets_8mb(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(type="file", name="song.mp3") == 8 * 1024 * 1024

    def test_pdf_gets_2mb(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(type="file", name="doc.pdf") == 2 * 1024 * 1024

    def test_case_insensitive(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(type="file", name="VIDEO.MKV") == 16 * 1024 * 1024

    def test_no_name_uses_default(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(type="file") == 65536
