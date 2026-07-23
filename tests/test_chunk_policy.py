import pytest

from vaultfs.domain.chunk_policy import ChunkPolicyConfig, DefaultChunkPolicy


@pytest.fixture
def policy() -> DefaultChunkPolicy:
    return DefaultChunkPolicy()


class TestDefaultChunkPolicy:
    def test_video_returns_16mb(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(name="video.mp4") == 16 * 1024 * 1024
        assert policy.choose_chunk_size(name="movie.mkv") == 16 * 1024 * 1024

    def test_audio_returns_8mb(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(name="song.mp3") == 8 * 1024 * 1024
        assert policy.choose_chunk_size(name="track.flac") == 8 * 1024 * 1024
        assert policy.choose_chunk_size(name="voice.wav") == 8 * 1024 * 1024

    def test_large_file_returns_32mb(self, policy: DefaultChunkPolicy) -> None:
        huge = 100 * 1024 * 1024 * 1024
        assert policy.choose_chunk_size(name="backup.iso", file_size=huge) == 32 * 1024 * 1024

    def test_large_file_excludes_video(self, policy: DefaultChunkPolicy) -> None:
        huge = 100 * 1024 * 1024 * 1024
        assert policy.choose_chunk_size(name="movie.mkv", file_size=huge) == 16 * 1024 * 1024

    def test_archive_returns_16mb(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(name="archive.zip") == 16 * 1024 * 1024
        assert policy.choose_chunk_size(name="backup.tar") == 16 * 1024 * 1024
        assert policy.choose_chunk_size(name="backup.tar.gz") == 16 * 1024 * 1024

    def test_document_returns_1mb(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(name="doc.pdf") == 1 * 1024 * 1024
        assert policy.choose_chunk_size(name="letter.doc") == 1 * 1024 * 1024
        assert policy.choose_chunk_size(name="report.docx") == 1 * 1024 * 1024

    def test_default_returns_2mb(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(name="data.bin") == 2 * 1024 * 1024
        assert policy.choose_chunk_size(name="") == 2 * 1024 * 1024
        assert policy.choose_chunk_size() == 2 * 1024 * 1024

    def test_case_insensitive(self, policy: DefaultChunkPolicy) -> None:
        assert policy.choose_chunk_size(name="VIDEO.MKV") == 16 * 1024 * 1024

    def test_custom_config_overrides(self) -> None:
        config = ChunkPolicyConfig(
            default_chunk_size=4096,
            video_chunk_size=8192,
        )
        p = DefaultChunkPolicy(config=config)
        assert p.choose_chunk_size(name="data.bin") == 4096
        assert p.choose_chunk_size(name="video.mp4") == 8192
