from app.db.models import LibraryEntry, MediaItem
from app.season_completion.inventory import library_show, source_filename_index
from app.season_completion.ranking import EpisodeRef


def test_source_filename_index_maps_every_file_in_a_pack() -> None:
    downloads = {
        "torrents": [
            {
                "id": 10,
                "files": [
                    {"id": 1, "name": "Show.S01E01.mkv"},
                    {"id": 2, "name": "Show.S01E02.mkv"},
                ],
            }
        ]
    }

    assert source_filename_index(downloads) == {
        ("torrents", "10", "1"): "Show.S01E01.mkv",
        ("torrents", "10", "2"): "Show.S01E02.mkv",
    }


def test_library_show_ignores_entries_missing_from_current_torbox_inventory() -> None:
    media_item = MediaItem(id=1, media_type="show", title="Example Show", tmdb_id="42")
    active = _entry(file_id="1", episode=1)
    stale = _entry(file_id="2", episode=2)

    show = library_show(
        [(media_item, active), (media_item, stale)],
        {("torrents", "10", "1"): "Example.Show.S01E01.mkv"},
    )

    assert show.episodes == frozenset({EpisodeRef(1, 1)})
    assert show.filenames_by_season == {1: ("Example.Show.S01E01.mkv",)}


def _entry(*, file_id: str, episode: int) -> LibraryEntry:
    return LibraryEntry(
        opaque_id=f"entry-{file_id}",
        media_item_id=1,
        category="shows",
        season_number=1,
        episode_number=episode,
        provider="torrents",
        provider_item_id="10",
        provider_file_id=file_id,
    )
