import logging

from vaultfs.infrastructure.database.repository import MetadataRepository
from vaultfs.storage.provider_factory import StorageProviderRegistry

logger = logging.getLogger(__name__)


class ChunkGarbageCollector:
    def __init__(
        self,
        metadata: MetadataRepository,
        registry: StorageProviderRegistry,
    ) -> None:
        self._metadata = metadata
        self._registry = registry

    async def collect(self, force: bool = False) -> int:
        orphaned = await self._metadata.get_orphaned_chunks(force=force)
        if not orphaned:
            logger.info("No orphaned chunks to collect")
            return 0

        logger.info("Found %d orphaned chunks", len(orphaned))
        cleaned = 0

        for chunk in orphaned:
            try:
                provider_name = await self._metadata.get_provider_name_for_chunk(chunk.id)
                provider = self._registry.get(provider_name)

                if chunk.external_id:
                    await provider.delete_chunk(chunk.external_id)
                    logger.debug(
                        "Deleted chunk %s from provider %s (external_id=%s)",
                        chunk.id,
                        provider_name,
                        chunk.external_id,
                    )

                await self._metadata.hard_delete_chunk(chunk.id)
                cleaned += 1
                logger.debug("Hard-deleted chunk %s", chunk.id)

            except Exception:
                logger.exception(
                    "Failed to clean up orphaned chunk %s, will retry on next run",
                    chunk.id,
                )

        logger.info("Cleaned up %d / %d orphaned chunks", cleaned, len(orphaned))
        return cleaned
