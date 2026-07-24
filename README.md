# VaultFS

Виртуальная файловая система поверх объектного хранилища Telegram.

Файлы разбиваются на зашифрованные чанки фиксированного размера, которые хранятся
в Telegram-канале как медиасообщения. ФС монтируется через FUSE и доступна
локально или по SMB/CIFS.

**Платформы:**
- Linux (pyfuse3) ✅ — основной таргет, протестировано
- WSL2 (pyfuse3) ✅ — протестировано, работает через `\\wsl.localhost\...`
- Windows (refuse + WinFsp) ⚠️ — код написан, но **не тестировался** в нативной среде

---

## Архитектура

```
    ┌─────────────────────────────────────────────┐
    │               Presentation                  │
    │  FUSE (pyfuse3 / refuse)   SMB (Samba)      │
    └──────────────────────┬──────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────┐
    │              Application                    │
    │  FileManager  ChunkManager  CacheLayer       │
    │  ACLSystem    ChunkPolicy  GarbageCollector  │
    └──────────────────────┬──────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────┐
    │                Domain                       │
    │  FileHandle   exceptions   ChunkPolicy (iface)│
    └──────────────────────┬──────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────┐
    │             Infrastructure                  │
    │  SqlAlchemyRepo  FUSE Backends  AsyncioBridge│
    │  EncryptionLayer  KeyManager  Telegram/Memory│
    └─────────────────────────────────────────────┘
```

**Правила:**
- Внешние слои зависят от внутренних
- Domain не импортирует FastAPI, SQLAlchemy, Telethon, Trio
- Application оркестрирует, но не содержит бизнес-правил
- Infrastructure реализует интерфейсы, объявленные во внутренних слоях

---

## Быстрый старт

### 1. Зависимости

- Python >= 3.12
- PostgreSQL 16
- Docker (для PostgreSQL и Samba)
- FUSE3 (Linux: `apt install fuse3`, WSL2: встроен)

### 2. Клонирование и настройка

```bash
git clone https://github.com/pellesh011/vault-404.git
cd vault-404
cp .env.example .env
```

### 3. Запуск PostgreSQL

```bash
docker compose up -d postgres
```

Для тестов (отдельный инстанс на порту 5433):

```bash
docker compose up -d postgres-test
```

### 4. Установка

```bash
uv sync
uv sync --dev       # с dev-зависимостями
```

### 5. Миграции БД

```bash
uv run alembic upgrade head
```

### 6. Настройка Telegram

Заполните `.env`:

```env
TELEGRAM_API_ID=12345
TELEGRAM_API_HASH=abc123def456
TELEGRAM_PHONE=+71234567890
TELEGRAM_CHANNEL_ID=-1001234567890
```

ID канала можно узнать через:

```bash
uv run python -m vaultfs.channel_id
```

### 7. Запуск

```bash
uv run vaultfs
```

Или с указанием точки монтирования и уровня логирования:

```bash
VAULTFS_LOG_LEVEL=DEBUG MOUNTPOINT=/tmp/vault uv run vaultfs
```

Файлы появятся в `/mnt/vault` (или в указанном `MOUNTPOINT`).

### 8. Доступ по SMB

```bash
docker compose up -d samba
```

Из Windows: `\\wsl.localhost\Ubuntu\mnt\vault\` (WSL2) или `\\<host>\vault` (SMB).

---

## Конфигурация

Все настройки задаются через переменные окружения или `.env` файл.

### Telegram

| Переменная | По умолчанию | Описание |
|---|---|---|
| `TELEGRAM_API_ID` | — | API ID приложения [my.telegram.org](https://my.telegram.org) |
| `TELEGRAM_API_HASH` | — | API Hash |
| `TELEGRAM_PHONE` | — | Номер телефона для авторизации |
| `TELEGRAM_CHANNEL_ID` | — | ID канала для хранения чанков (числовой) |
| `TELEGRAM_SESSION_NAME` | `vault_session` | Имя файла сессии Telethon |
| `TELEGRAM_MAX_CONCURRENT` | `10` | Максимум параллельных запросов к Telegram API |

**Прокси:**

| Переменная | Пример | Описание |
|---|---|---|
| `TELEGRAM_PROXY_TYPE` | `socks5` | Тип: `http`, `socks5`, `socks4` |
| `TELEGRAM_PROXY_ADDR` | `127.0.0.1` | Адрес прокси-сервера |
| `TELEGRAM_PROXY_PORT` | `9050` | Порт |
| `TELEGRAM_PROXY_USERNAME` | — | Логин (если требуется) |
| `TELEGRAM_PROXY_PASSWORD` | — | Пароль |

### База данных

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://vault404:vault404@localhost:5432/vault404` | URL подключения к PostgreSQL |

### Файловая система

| Переменная | По умолчанию | Описание |
|---|---|---|
| `MOUNTPOINT` | `/mnt/vault` | Точка монтирования FUSE |
| `FUSE_BACKEND` | `pyfuse3` | `pyfuse3` (Linux/WSL2) или `winfsp` (Windows/refuse) |

### Шифрование

| Переменная | По умолчанию | Описание |
|---|---|---|
| `ENCRYPTION_MASTER_KEY` | авто-генерация | Мастер-ключ в hex (32 байта → 64 hex-символа) |

Если `ENCRYPTION_MASTER_KEY` не задан, ключ автоматически генерируется
и сохраняется в `~/.vaultfs/encryption.key`.

### Логирование

| Переменная | По умолчанию | Описание |
|---|---|---|
| `VAULTFS_LOG_LEVEL` | `INFO` | Уровень: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Архитектура: подробно

### Domain Layer (`vaultfs/domain/`)

Чистое ядро без внешних зависимостей.

| Файл | Содержание |
|---|---|
| `exceptions.py` | `VaultFSError`, `PermissionDeniedError`, `DirectoryNotEmptyError` |
| `chunk_policy.py` | `ChunkPolicy` — выбор размера чанка по расширению файла |
| `file_handle.py` | `FileHandle` — дескриптор открытого файла |
| `acl.py` | `ACLSystem` — контроль доступа (InMemoryACL) |

**ChunkPolicy:** размеры чанков по типу файлов:

| Тип | Расширения | Размер чанка |
|---|---|---|
| Видео | `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm` | 16 MB |
| Аудио | `.mp3`, `.flac`, `.wav` | 8 MB |
| Большие | `.iso`, `.img`, `.dmg` | 32 MB |
| Архивы | `.zip`, `.rar`, `.7z`, `.tar.gz` | 16 MB |
| Документы | `.pdf`, `.doc`, `.docx`, `.xlsx` | 1 MB |
| Всё остальное | — | 2 MB |

### Application Layer (`vaultfs/application/`)

Оркестрация бизнес-операций.

| Файл | Класс | Ответственность |
|---|---|---|
| `file_manager.py` | `FileManager` | Создание/чтение/запись/удаление файлов и директорий |
| `chunk_manager.py` | `ChunkManager` | Разбивка на чанки, read-modify-write, кэширование, флеш |
| `cache.py` | `InMemoryCache` | Простой in-memory кэш со счётчиками hit/miss |
| `cache_layer.py` | `LRUCache`, `SSDDirectoryCache`, `MultiLevelCache` | Многоуровневый кэш (L1 + L2 + provider) |
| `garbage_collector.py` | `ChunkGarbageCollector` | Сбор осиротевших чанков |

**ChunkManager.read()** — основной путь чтения:

1. Получить `Node` (метаданные) + список `FileChunk` из БД
2. Для каждого затронутого чанка:
   - Проверить dirty-буфер
   - Иначе проверить `InMemoryCache`
   - Иначе загрузить с провайдера (Telegram), расшифровать, закэшировать
3. Склеить результат

Если фактический размер данных чанка меньше `node.chunk_size`, чтение
безопасно прерывается (не уходит в бесконечный цикл).

### Infrastructure Layer (`vaultfs/infrastructure/`)

Реализации интерфейсов, взаимодействие с внешними системами.

#### FUSE Backends

```
FUSEBackend (ABC)
├── PyFuse3Backend  — Linux / WSL2 (pyfuse3)
└── WinFspBackend   — Windows (refuse) ⚠️ не тестирован в нативной среде
```

Выбор через переменную `FUSE_BACKEND`:

```bash
FUSE_BACKEND=pyfuse3   # по умолчанию, для Linux и WSL2
FUSE_BACKEND=winfsp     # Windows + WinFsp (не тестировалось)
```

**Примечание:** `refuse` — Python-биндинг для WinFsp, работающий только
в нативной среде Windows. В WSL он не работает (не может загрузить WinFsp DLL),
поэтому в WSL используется `pyfuse3` и доступ к файлам через `\\wsl.localhost\...`.

#### AsyncioBridge

Критический компонент: FUSE использует Trio как основной event-loop, а
Telethon и SQLAlchemy требуют asyncio. Bridge запускает asyncio-loop
в отдельном daemon-треде и пробрасывает вызовы:

```python
class AsyncioBridge:
    async def run(self, coro):
        async def _locked():
            async with self._session_lock:
                return await coro

        future = asyncio.run_coroutine_threadsafe(_locked(), self._loop)
        return await trio.to_thread.run_sync(future.result)
```

**`asyncio.Lock`** гарантирует, что две Trio-задачи не отправят
одновременные запросы к asyncpg через одно соединение.

#### База данных (SQLAlchemy 2.x + asyncpg)

7 таблиц:

| Таблица | Назначение |
|---|---|
| `nodes` | Файлы и директории (иерархическая структура) |
| `file_chunks` | Связь "файл → список чанков" с индексами |
| `chunks` | Метаданные чанков (размер, sha256, external_id, nonce, auth_tag) |
| `storage_providers` | Провайдеры хранилища (telegram, memory) |
| `encryption_keys` | Ключи шифрования, зашифрованные мастер-ключом |
| `acl` | Права доступа (principal → permissions) |

Миграции — Alembic, 7 ревизий.

#### Bridge-прокси

Все asyncio-зависимые компоненты обёрнуты в Bridge для вызова из Trio:

- `BridgedMetadataRepository` → SqlAlchemyMetadataRepository
- `BridgedStorageProvider` → StorageProvider (Telegram/Memory)
- `BridgedKeyManager` → DatabaseKeyManager

### Storage Layer (`vaultfs/storage/`)

Абстракции и реализации провайдеров хранения.

```
StorageProvider (ABC)
├── TelegramStorageProvider  — хранение чанков в Telegram-канале
└── MemoryStorageProvider     — in-memory (для тестов/разработки)
```

**TelegramStorageProvider:**
- `create_chunk(data)` — загружает файл в Telegram, отправляет в канал, возвращает `message_id`
- `get_chunk(external_id)` — получает сообщение, скачивает медиафайл
- `delete_chunk(external_id)` — удаляет сообщение из канала

---

## Шифрование

```
Master Key
    │ (Fernet)
    ▼
Node Key (AES-256-GCM)  ← хранится в encryption_keys, зашифрован мастер-ключом
    │
    ├── Chunk: encrypt(nonce + data) → nonce(12) + ciphertext + auth_tag(16)
    └── Chunk: decrypt(nonce + ciphertext + auth_tag) → data
```

- Каждый файл (node) получает свой 256-битный ключ
- Ключи хранятся в БД, зашифрованные мастер-ключом через `cryptography.fernet.Fernet`
- Мастер-ключ — из `ENCRYPTION_MASTER_KEY` (hex) или `~/.vaultfs/encryption.key`
- Режим шифрования: AES-256-GCM (аутентифицированное шифрование)
- Nonce (12 байт) генерируется случайно для каждого чанка

---

## Кэширование

### InMemoryCache (активен по умолчанию)

Хранит расшифрованные данные чанков в `dict[ChunkId, bytes]`.
При старте кэш пуст, наполняется по мере чтения файлов.

Счётчики `hits`/`misses` доступны в DEBUG-логировании:

```
InMemoryCache.get: key=..., hit=True, total hits=5, total misses=2
```

### MultiLevelCache (опционально)

Готовая, но не включенная в `main.py` реализация:

- **L1:** `LRUCache` — in-memory, лимит по размеру (через `CACHE_L1_MAX_SIZE`)
- **L2:** `SSDDirectoryCache` — файловый кэш на диске (через `CACHE_L2_PATH` / `CACHE_L2_MAX_SIZE`)

---

## Samba / Docker

```bash
docker compose up -d postgres samba
```

Сервисы:

| Сервис | Назначение |
|---|---|
| `postgres` | PostgreSQL 16, порт 5432 |
| `samba` | SMB-шара на `/mnt/vault`, пользователь `vaultfs:password` |
| `postgres-test` | PostgreSQL для тестов, порт 5433, `tmpfs` |

Samba-конфигурация (`conf/smb.conf`):

```
[global]
    workgroup = VAULTFS
    security = user
    map to guest = never

[vault]
    path = /mnt/vault
    valid users = @vaultfs
    create mask = 0644
    directory mask = 0755
```

---

## Разработка

### Настройка окружения

```bash
uv sync
uv sync --dev
```

### Форматирование и линтинг

```bash
uv run ruff check .
uv run ruff format .
```

### Статическая типизация

```bash
uv run pyright vaultfs/
```

### Запуск тестов

```bash
# Требуется запущенный PostgreSQL (docker compose up -d postgres-test)
uv run pytest
```

Структура тестов:

| Файл | Тип | Что тестирует |
|---|---|---|
| `test_acl.py` | Unit | InMemoryACL |
| `test_cache_layer.py` | Unit | LRUCache, SSDDirectoryCache, MultiLevelCache |
| `test_chunk_manager.py` | Unit | ChunkManager (read/write/prefetch, cache) |
| `test_chunk_policy.py` | Unit | DefaultChunkPolicy (выбор размера по расширению) |
| `test_chunk_storage.py` | Unit | InMemoryChunkStorage (CRUD) |
| `test_encryption.py` | Unit | AES-GCM шифрование/расшифровка |
| `test_file_manager.py` | Integration | FileManager (все операции с БД) |
| `test_repository.py` | Integration | SqlAlchemyMetadataRepository (CRUD) |
| `test_telegram.py` | Unit | TelegramStorageProvider (моки) |

### Миграции БД

```bash
# Создать новую миграцию
uv run alembic revision --autogenerate -m "description"

# Применить
uv run alembic upgrade head

# Откатить
uv run alembic downgrade -1
```

---

## Скрипты

### seed_storage_providers.py

Заполняет таблицу `storage_providers` начальными записями (telegram, memory).

```bash
uv run python scripts/seed_storage_providers.py
```

### cleanup_orphaned_chunks.py

Удаляет осиротевшие чанки (без ссылок из file_chunks).

```bash
# Без force — grace period 1 час
uv run python scripts/cleanup_orphaned_chunks.py

# С force — удалить всё сразу
uv run python scripts/cleanup_orphaned_chunks.py --force
```

---

## Ограничения

1. **Нативный Windows (WinFsp/refuse) — не тестировался.**
   Код написан и структурно готов, но у авторов нет возможности
   проверить его в нативной среде Windows. В WSL2 используется
   `pyfuse3` (работает через встроенный в ядро Linux модуль FUSE).

2. **Один мастер-ключ на всё хранилище.**
   В будущем возможна ротация ключей и мульти-ключевая схема.

3. **InMemoryCache без эвикции.**
   Все загруженные чанки хранятся в памяти до перезапуска процесса.
   Для больших файлов это может потреблять значительный объём RAM.

4. **ACL in-memory.**
   Права доступа сбрасываются при перезапуске. В будущем — хранение в БД.

---

## FAQ

**Q: Почему файл открывается долго в первый раз?**
A: Чанки скачиваются из Telegram по требованию. Скорость зависит от
интернет-соединения и размера файла. После первого открытия данные
кэшируются в памяти.

**Q: Как получить ID канала Telegram?**
A: Запустите `uv run python -m vaultfs.channel_id` и отправьте
сообщение в канал. Скрипт выведет ID.

**Q: Можно ли использовать другой провайдер вместо Telegram?**
A: Да. Реализуйте `StorageProvider` (ABC в `vaultfs/storage/provider.py`)
и зарегистрируйте его в `StorageProviderRegistry` в `main.py`.

**Q: Как работает монтирование в WSL2?**
A: WSL2 имеет встроенную поддержку FUSE. VaultFS монтируется через
pyfuse3. Из Windows доступ к файлам — через `\\wsl.localhost\Ubuntu\...`.

**Q: Что делать, если при монтировании ошибка "transport endpoint is not connected"?**
A: Размонтируйте принудительно:
```bash
fusermount -u /mnt/vault
```

---

## Лицензия

MIT
