from app.season_completion.matching import title_matches_show


def test_title_matches_show_accepts_normalized_release_name() -> None:
    assert title_matches_show("From", "From.Gal.2010.Saxy-UHD.S01E02.2160p.mkv")


def test_title_matches_show_accepts_season_pack() -> None:
    assert title_matches_show(
        "Ascendance of a Bookworm",
        "Ascendance.of.a.Bookworm.S01+S02+OVAs.1080p.mkv",
    )


def test_title_matches_show_rejects_different_show() -> None:
    assert not title_matches_show("From", "Bridgerton.S03E01.2160p.mkv")


def test_title_matches_show_requires_title_at_start_of_release_name() -> None:
    assert not title_matches_show("The Bear", "Group.The.Bear.S03E01.2160p.mkv")


def test_title_matches_show_requires_season_or_episode_marker() -> None:
    assert not title_matches_show("Ascendance of a Bookworm", "Ascendance.of.a.Bookworm.1080p")
