from app.library.naming import library_entry_from_file_name


def test_library_entry_from_movie_file_name() -> None:
    entry = library_entry_from_file_name(
        "Project.Hail.Mary.2026.1080p.WEB-DL.mkv",
        "https://example.test/play",
    )

    assert entry.category == "movies"
    assert entry.title == "Project Hail Mary"
    assert entry.year == 2026
    assert entry.season_number is None
    assert entry.episode_number is None


def test_library_entry_from_show_file_name() -> None:
    entry = library_entry_from_file_name(
        "Slow.Horses.S02E03.1080p.WEB-DL.mkv",
        "https://example.test/play",
    )

    assert entry.category == "shows"
    assert entry.title == "Slow Horses"
    assert entry.season_number == 2
    assert entry.episode_number == 3


def test_library_entry_uses_anime_category_hint() -> None:
    entry = library_entry_from_file_name(
        "Frieren.S01E04.mkv",
        "https://example.test/play",
        folder_name="Anime/Frieren",
    )

    assert entry.category == "anime"
    assert entry.title == "Frieren"
