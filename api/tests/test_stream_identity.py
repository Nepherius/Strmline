from app.providers.aiostreams.client import AioStreamsStream
from app.search.stream_identity import find_stream_by_key, stream_identity


def test_stream_identity_builds_magnet_from_info_hash() -> None:
    stream = AioStreamsStream(
        name="[TB⚡] Test",
        title="Movie.1080p.mkv",
        description=None,
        url=None,
        info_hash="4FB46A63360B938999B72A73E2C19F2231F8A5C3",
        file_idx=None,
        behavior_hints={"filename": "Movie.1080p.mkv", "videoSize": 10},
        raw={},
    )

    identity = stream_identity(stream, media_type="movie", media_id="tt1234567")

    assert len(identity.stream_key) == 32
    assert identity.info_hash == "4fb46a63360b938999b72a73e2c19f2231f8a5c3"
    assert identity.magnet == "magnet:?xt=urn:btih:4fb46a63360b938999b72a73e2c19f2231f8a5c3"
    assert identity.addable is True


def test_stream_identity_uses_magnet_url_hash() -> None:
    stream = AioStreamsStream(
        name=None,
        title="Movie.1080p.mkv",
        description=None,
        url="magnet:?xt=urn:btih:4fb46a63360b938999b72a73e2c19f2231f8a5c3&dn=Movie",
        info_hash=None,
        file_idx=None,
        behavior_hints={},
        raw={},
    )

    identity = stream_identity(stream, media_type="movie", media_id="tt1234567")

    assert identity.info_hash == "4fb46a63360b938999b72a73e2c19f2231f8a5c3"
    assert identity.magnet is not None
    assert identity.addable is True


def test_stream_identity_marks_direct_url_as_not_addable() -> None:
    stream = AioStreamsStream(
        name="Direct",
        title="Movie.1080p.mkv",
        description=None,
        url="https://example.invalid/play",
        info_hash=None,
        file_idx=None,
        behavior_hints={},
        raw={},
    )

    identity = stream_identity(stream, media_type="movie", media_id="tt1234567")

    assert identity.info_hash is None
    assert identity.magnet is None
    assert identity.addable is False


def test_stream_identity_marks_torbox_action_url_as_addable() -> None:
    stream = AioStreamsStream(
        name="[TB⚡] StremThru Torz 1080p",
        title="Movie.1080p.mkv",
        description=None,
        url="https://streams.example/add/123",
        info_hash=None,
        file_idx=None,
        behavior_hints={},
        raw={},
    )

    identity = stream_identity(stream, media_type="movie", media_id="tt1234567")

    assert identity.info_hash is None
    assert identity.magnet is None
    assert identity.action_url == "https://streams.example/add/123"
    assert identity.addable is True


def test_stream_identity_key_does_not_depend_on_action_url() -> None:
    first = AioStreamsStream(
        name="[TB⚡] StremThru Torz 1080p",
        title="Movie.1080p.mkv",
        description=None,
        url="https://streams.example/add/123",
        info_hash=None,
        file_idx=None,
        behavior_hints={"filename": "Movie.1080p.mkv", "videoSize": 10},
        raw={},
    )
    second = AioStreamsStream(
        name="[TB⚡] StremThru Torz 1080p",
        title="Movie.1080p.mkv",
        description=None,
        url="https://streams.example/add/rotated",
        info_hash=None,
        file_idx=None,
        behavior_hints={"filename": "Movie.1080p.mkv", "videoSize": 10},
        raw={},
    )

    first_identity = stream_identity(first, media_type="movie", media_id="tt1234567")
    second_identity = stream_identity(second, media_type="movie", media_id="tt1234567")

    assert first_identity.stream_key == second_identity.stream_key
    assert first_identity.action_url == "https://streams.example/add/123"
    assert second_identity.action_url == "https://streams.example/add/rotated"


def test_find_stream_by_key_matches_same_search_context() -> None:
    stream = AioStreamsStream(
        name="[TB⚡] Test",
        title="Movie.1080p.mkv",
        description=None,
        url=None,
        info_hash="4fb46a63360b938999b72a73e2c19f2231f8a5c3",
        file_idx=None,
        behavior_hints={},
        raw={},
    )
    identity = stream_identity(stream, media_type="series", media_id="tt1234567:1:2")

    assert (
        find_stream_by_key(
            (stream,),
            media_type="series",
            media_id="tt1234567:1:2",
            stream_key=identity.stream_key,
        )
        is stream
    )
    assert (
        find_stream_by_key(
            (stream,),
            media_type="series",
            media_id="tt1234567",
            stream_key=identity.stream_key,
        )
        is None
    )
