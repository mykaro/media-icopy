"""Logic for grouping files into batches for iterative copying."""

from collections.abc import Generator
from pathlib import Path

from .models import RemoteFile, CopyTask, Batch


def generate_batches(
    files: Generator[RemoteFile, None, None], dest_root: Path, limit_mb: int
) -> Generator[Batch, None, None]:
    """
    Groups files into batches of approximately limit_mb in size.

    This is an incremental generator that yields batches as they are filled.
    It minimizes memory usage by not collecting all files at once.

    Note: total_batches in Batch is set to -1 since it's unknown in incremental mode.

    Args:
        files: Generator yielding RemoteFile objects.
        dest_root: The root destination path.
        limit_mb: Maximum size of a batch in megabytes.

    Returns:
        Generator yielding Batch objects.
    """
    limit_bytes = limit_mb * 1024 * 1024
    current_tasks: list[CopyTask] = []
    current_size = 0
    batch_index = 0

    def create_task(file: RemoteFile) -> CopyTask:
        dest_path = str(dest_root / file.relative_path)
        return CopyTask(file=file, dest_path=dest_path)

    for file in files:
        # Large file -> separate batch
        if file.size_bytes > limit_bytes:
            if current_tasks:
                yield Batch(
                    index=batch_index,
                    total_batches=-1,
                    tasks=current_tasks,
                    total_size_bytes=current_size,
                )
                batch_index += 1
                current_tasks, current_size = [], 0

            yield Batch(
                index=batch_index,
                total_batches=-1,
                tasks=[create_task(file)],
                total_size_bytes=file.size_bytes,
            )
            batch_index += 1
            continue

        # Check if adding this file exceeds limit
        if current_size + file.size_bytes > limit_bytes:
            yield Batch(
                index=batch_index,
                total_batches=-1,
                tasks=current_tasks,
                total_size_bytes=current_size,
            )
            batch_index += 1
            current_tasks, current_size = [], 0

        current_tasks.append(create_task(file))
        current_size += file.size_bytes

    # Final batch
    if current_tasks:
        yield Batch(
            index=batch_index,
            total_batches=-1,
            tasks=current_tasks,
            total_size_bytes=current_size,
        )
