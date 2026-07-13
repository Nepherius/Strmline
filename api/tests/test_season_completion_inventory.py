from app.db.models import LibraryEntry, MediaItem, TorBoxStoredFile
from app.season_completion.inventory import library_show
from app.season_completion.ranking import EpisodeRef


def test_library_show_uses_normalized_current_torbox_files() -> None:
    media_item = MediaItem(id=1, media_type="show", title="Example Show", tmdb_id="42")
    active = _entry(file_id=1, episode=1)
    source_file = TorBoxStoredFile(
        id=1,
        torbox_item_id=10,
        external_id="1",
        file_name="Example.Show.S01E01.mkv",
        path="Example.Show.S01E01.mkv",
        mime_type="video/x-matroska",
        size=1,
    )

    show = library_show([(media_item, active, source_file)])

    assert show.episodes == frozenset({EpisodeRef(1, 1)})
    assert show.filenames_by_season == {1: ("Example.Show.S01E01.mkv",)}


def _entry(*, file_id: int, episode: int) -> LibraryEntry:
    return LibraryEntry(
        opaque_id=f"entry-{file_id}",
        media_item_id=1,
        torbox_file_id=file_id,
        category="shows",
        season_number=1,
        episode_number=episode,
    )
