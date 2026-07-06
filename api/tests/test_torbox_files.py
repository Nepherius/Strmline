from app.providers.torbox.files import extract_torbox_files, request_download_url


def test_extract_torbox_files_filters_uncached_non_video_and_samples() -> None:
    downloads = [
        {
            "id": 10,
            "name": "Show.Name.S01E02",
            "cached": True,
            "files": [
                {
                    "id": 20,
                    "short_name": "Show.Name.S01E02.mkv",
                    "name": "Show.Name.S01E02/Show.Name.S01E02.mkv",
                    "mimetype": "video/x-matroska",
                    "size": 1_000_000_000,
                },
                {
                    "id": 21,
                    "short_name": "sample.mkv",
                    "name": "Show.Name.S01E02/sample.mkv",
                    "mimetype": "video/x-matroska",
                    "size": 20_000_000,
                },
                {
                    "id": 22,
                    "short_name": "poster.jpg",
                    "mimetype": "image/jpeg",
                },
            ],
        },
        {
            "id": 11,
            "cached": False,
            "files": [
                {
                    "id": 23,
                    "short_name": "Ignored.Movie.2024.mkv",
                    "mimetype": "video/x-matroska",
                },
            ],
        },
    ]

    result = extract_torbox_files(downloads, "torrents")

    assert len(result.files) == 1
    assert result.skipped_count == 3
    assert result.files[0].item_id == "10"
    assert result.files[0].file_id == "20"
    assert result.files[0].file_name == "Show.Name.S01E02.mkv"


def test_extract_torbox_files_filters_pack_extras() -> None:
    downloads = [
        {
            "id": 10,
            "name": "Anime Pack",
            "cached": True,
            "files": [
                {
                    "id": 20,
                    "short_name": "Show.S03E01.mkv",
                    "mimetype": "video/x-matroska",
                },
                {
                    "id": 21,
                    "short_name": "S03OP Ano hi No Kotoba Nao Toyama.mkv",
                    "mimetype": "video/x-matroska",
                },
                {
                    "id": 22,
                    "short_name": "S03ED Kotoba ni Dekinai Maaya Sakamoto.mkv",
                    "mimetype": "video/x-matroska",
                },
                {
                    "id": 23,
                    "short_name": "S03SP01 Ascendance of a Bookworm Part 1.mkv",
                    "mimetype": "video/x-matroska",
                },
            ],
        },
    ]

    result = extract_torbox_files(downloads, "torrents")

    assert len(result.files) == 1
    assert result.skipped_count == 3
    assert result.files[0].file_id == "20"


def test_request_download_url_uses_torbox_id_parameter_for_kind() -> None:
    result = extract_torbox_files(
        [
            {
                "id": "abc",
                "name": "Movie",
                "cached": True,
                "files": [
                    {
                        "id": "def",
                        "short_name": "Movie.2024.mp4",
                        "mimetype": "video/mp4",
                    },
                ],
            },
        ],
        "webdl",
    )

    url = request_download_url("https://api.torbox.app/v1/api/", "api token", result.files[0])

    assert url == (
        "https://api.torbox.app/v1/api/webdl/requestdl?"
        "token=api+token&web_id=abc&file_id=def&redirect=true"
    )
