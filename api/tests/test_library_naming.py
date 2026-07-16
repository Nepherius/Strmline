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


def test_library_entry_from_spaced_show_episode_file_name() -> None:
    entry = library_entry_from_file_name(
        "Vagabond S01 E09 (2019).mkv",
        "https://example.test/play",
    )

    assert entry.category == "shows"
    assert entry.title == "Vagabond"
    assert entry.year == 2019
    assert entry.season_number == 1
    assert entry.episode_number == 9


def test_library_entry_uses_anime_category_hint() -> None:
    entry = library_entry_from_file_name(
        "Frieren.S01E04.mkv",
        "https://example.test/play",
        folder_name="Anime/Frieren",
    )

    assert entry.category == "anime"
    assert entry.title == "Frieren"


def test_library_entry_strips_leading_release_group() -> None:
    entry = library_entry_from_file_name(
        "[TTGA] Ascendance.of.a.Bookworm.S03E01.2022.1080p.mkv",
        "https://example.test/play",
    )

    assert entry.category == "shows"
    assert entry.title == "Ascendance of a Bookworm"
    assert entry.year == 2022
    assert entry.season_number == 3
    assert entry.episode_number == 1


def test_library_entry_uses_pack_folder_for_bare_episode_number() -> None:
    entry = library_entry_from_file_name(
        "01 - The New Apprentice.mkv",
        "https://example.test/play",
        folder_name=(
            "[TTGA] Ascendance of a Bookworm (2022) (Season 3 + Specials)"
            " [BD Remux] [1080p Dual Audio DTS HD MA AVC]"
        ),
    )

    assert entry.category == "shows"
    assert entry.title == "Ascendance of a Bookworm"
    assert entry.year == 2022
    assert entry.season_number == 3
    assert entry.episode_number == 1


def test_library_entry_uses_sxx_pack_folder_for_title_prefixed_episode() -> None:
    entry = library_entry_from_file_name(
        "Kaijuu 8-gou - 03v2 [WEB 1080p HEVC x265 10-bit EAC-3].mkv",
        "https://example.test/play",
        folder_name=("[sam] Kaijuu 8-gou - S01 (WEB 1080p HEVC x265 10-bit EAC-3) [Dual-Audio]"),
    )

    assert entry.category == "shows"
    assert entry.title == "Kaijuu 8 gou"
    assert entry.season_number == 1
    assert entry.episode_number == 3


def test_library_entry_recognizes_bare_numbered_anime_episode_release() -> None:
    entry = library_entry_from_file_name(
        "Ascendance of a Bookworm 01 JP BD Hi10.mkv",
        "https://example.test/play",
    )

    assert entry.category == "shows"
    assert entry.title == "Ascendance of a Bookworm"
    assert entry.season_number == 1
    assert entry.episode_number == 1


def test_library_entry_does_not_treat_numbered_movie_quality_as_an_episode() -> None:
    entry = library_entry_from_file_name(
        "Movie 01 1080p WEB-DL.mkv",
        "https://example.test/play",
    )

    assert entry.category == "movies"
    assert entry.season_number is None
    assert entry.episode_number is None


def test_library_entry_falls_back_to_cleaned_folder_title() -> None:
    """When file name is bare SxEy, title and year come from the folder."""
    entry = library_entry_from_file_name(
        "S03E01.mkv",
        "https://example.test/play",
        folder_name=(
            "[TTGA] Ascendance of a Bookworm (2022) (Season 3 + Specials)"
            " [BD Remux] [1080p Dual Audio DTS HD MA AVC]"
            " (Honzuki no Gekokujou Shisho ni Naru Tame ni wa Shudan"
            " o Erande Iraremasen)"
        ),
    )

    assert entry.title == "Ascendance of a Bookworm"
    assert entry.year == 2022
    assert entry.season_number == 3
    assert entry.episode_number == 1


def test_library_entry_uses_folder_year_for_classification_metadata() -> None:
    entry = library_entry_from_file_name(
        "Spider.Noir.S01E01.1080p.mkv",
        "https://example.test/play",
        folder_name="Spider Noir (2026)",
    )

    assert entry.title == "Spider Noir"
    assert entry.year == 2026


def test_library_entry_prefers_file_year_over_folder_year() -> None:
    entry = library_entry_from_file_name(
        "Frieren.S01E01.2023.1080p.mkv",
        "https://example.test/play",
        folder_name="Frieren (2024)",
    )

    assert entry.title == "Frieren"
    assert entry.year == 2023


def test_library_entry_strips_year_before_season_episode() -> None:
    entry = library_entry_from_file_name(
        "Slow.Horses.2022.S01E01.1080p.mkv",
        "https://example.test/play",
    )

    assert entry.title == "Slow Horses"
    assert entry.year == 2022
    assert entry.season_number == 1
    assert entry.episode_number == 1
