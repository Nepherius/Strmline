"""Tests for stream metadata parsing from AIOStreams title/description text."""

from __future__ import annotations

import pytest

from app.search.stream_parser import is_imdb_id, parse_stream


class TestParseStreamQuality:
    def test_detects_4k_from_2160p(self) -> None:
        result = parse_stream(
            title="Movie.2160p.BluRay", description=None, name=None, filename=None, video_size=None
        )
        assert result.quality == "4K"

    def test_detects_4k_label(self) -> None:
        result = parse_stream(
            title="Movie 4K HDR", description=None, name=None, filename=None, video_size=None
        )
        assert result.quality == "4K"

    def test_detects_1080p(self) -> None:
        result = parse_stream(
            title="Movie.1080p.WEB-DL", description=None, name=None, filename=None, video_size=None
        )
        assert result.quality == "1080p"

    def test_detects_720p(self) -> None:
        result = parse_stream(
            title="Movie.720p.HDTV", description=None, name=None, filename=None, video_size=None
        )
        assert result.quality == "720p"

    def test_detects_cam(self) -> None:
        result = parse_stream(
            title="Movie CAM", description=None, name=None, filename=None, video_size=None
        )
        assert result.quality == "CAM"

    def test_no_quality_returns_none(self) -> None:
        result = parse_stream(
            title="Some Movie", description=None, name=None, filename=None, video_size=None
        )
        assert result.quality is None

    def test_uhd_maps_to_4k(self) -> None:
        result = parse_stream(
            title="Movie UHD Remux", description=None, name=None, filename=None, video_size=None
        )
        assert result.quality == "4K"


class TestParseStreamCodec:
    def test_detects_hevc(self) -> None:
        result = parse_stream(
            title="Movie.1080p.HEVC", description=None, name=None, filename=None, video_size=None
        )
        assert result.codec == "H.265"

    def test_detects_h265(self) -> None:
        result = parse_stream(
            title="Movie H.265", description=None, name=None, filename=None, video_size=None
        )
        assert result.codec == "H.265"

    def test_detects_x264(self) -> None:
        result = parse_stream(
            title="Movie.x264", description=None, name=None, filename=None, video_size=None
        )
        assert result.codec == "H.264"

    def test_detects_av1(self) -> None:
        result = parse_stream(
            title="Movie AV1", description=None, name=None, filename=None, video_size=None
        )
        assert result.codec == "AV1"


class TestParseStreamHdr:
    def test_detects_dolby_vision(self) -> None:
        result = parse_stream(
            title="Movie Dolby Vision", description=None, name=None, filename=None, video_size=None
        )
        assert result.hdr == "DV"

    def test_detects_dv_abbreviation(self) -> None:
        result = parse_stream(
            title="Movie DV HDR", description=None, name=None, filename=None, video_size=None
        )
        assert result.hdr == "DV"

    def test_detects_hdr10_plus(self) -> None:
        result = parse_stream(
            title="Movie HDR10+", description=None, name=None, filename=None, video_size=None
        )
        assert result.hdr == "HDR10+"

    def test_detects_hdr10(self) -> None:
        result = parse_stream(
            title="Movie HDR10", description=None, name=None, filename=None, video_size=None
        )
        assert result.hdr == "HDR10"


class TestParseStreamAudio:
    def test_detects_atmos(self) -> None:
        result = parse_stream(
            title="Movie Atmos", description=None, name=None, filename=None, video_size=None
        )
        assert result.audio == "Atmos"

    def test_detects_truehd(self) -> None:
        result = parse_stream(
            title="Movie TrueHD 7.1", description=None, name=None, filename=None, video_size=None
        )
        assert result.audio == "TrueHD"

    def test_detects_dts_hd(self) -> None:
        result = parse_stream(
            title="Movie DTS-HD MA", description=None, name=None, filename=None, video_size=None
        )
        assert result.audio == "DTS-HD"

    def test_detects_eac3_as_ddplus(self) -> None:
        result = parse_stream(
            title="Movie EAC3", description=None, name=None, filename=None, video_size=None
        )
        assert result.audio == "DD+"


class TestParseStreamSource:
    def test_detects_bluray(self) -> None:
        result = parse_stream(
            title="Movie BluRay", description=None, name=None, filename=None, video_size=None
        )
        assert result.source == "BluRay"

    def test_detects_webdl(self) -> None:
        result = parse_stream(
            title="Movie WEB-DL", description=None, name=None, filename=None, video_size=None
        )
        assert result.source == "WEB-DL"

    def test_detects_remux(self) -> None:
        result = parse_stream(
            title="Movie REMUX", description=None, name=None, filename=None, video_size=None
        )
        assert result.source == "Remux"

    def test_detects_hdtv(self) -> None:
        result = parse_stream(
            title="Movie HDTV", description=None, name=None, filename=None, video_size=None
        )
        assert result.source == "HDTV"


class TestParseStreamSize:
    def test_parses_gb_from_description(self) -> None:
        result = parse_stream(
            title="Movie", description="12.5 GB", name=None, filename=None, video_size=None
        )
        assert result.size_label == "12.5 GB"
        assert result.size_bytes is not None
        assert result.size_bytes == int(12.5 * 1024 * 1024 * 1024)

    def test_parses_mb_from_description(self) -> None:
        result = parse_stream(
            title="Movie", description="800 MB", name=None, filename=None, video_size=None
        )
        assert result.size_label == "800 MB"
        assert result.size_bytes == 800 * 1024 * 1024

    def test_prefers_video_size_over_text(self) -> None:
        result = parse_stream(
            title="Movie",
            description="12.5 GB",
            name=None,
            filename=None,
            video_size=5_000_000_000,
        )
        assert result.size_bytes == 5_000_000_000
        assert result.size_label is not None
        assert "4.7" in result.size_label

    def test_no_size_returns_none(self) -> None:
        result = parse_stream(
            title="Movie", description=None, name=None, filename=None, video_size=None
        )
        assert result.size_bytes is None
        assert result.size_label is None


class TestParseStreamLanguage:
    def test_detects_multi(self) -> None:
        result = parse_stream(
            title="Movie Multi", description=None, name=None, filename=None, video_size=None
        )
        assert result.language == "Multi"

    def test_detects_dual_audio(self) -> None:
        result = parse_stream(
            title="Movie Dual Audio", description=None, name=None, filename=None, video_size=None
        )
        assert result.language == "Dual"


class TestParseStreamCombined:
    def test_parses_full_title(self) -> None:
        result = parse_stream(
            title="Movie.2160p.UHD.BluRay.REMUX.HDR.DV.TrueHD.Atmos.7.1.HEVC",
            description="45.2 GB",
            name=None,
            filename=None,
            video_size=None,
        )
        assert result.quality == "4K"
        assert result.codec == "H.265"
        assert result.hdr == "DV"
        assert result.audio == "Atmos"
        assert result.source == "BluRay"
        assert result.size_label == "45.2 GB"

    def test_uses_description_when_title_missing(self) -> None:
        result = parse_stream(
            title=None,
            description="1080p WEB-DL H.264 AAC 2.3 GB",
            name=None,
            filename=None,
            video_size=None,
        )
        assert result.quality == "1080p"
        assert result.codec == "H.264"
        assert result.audio == "AAC"
        assert result.source == "WEB-DL"

    def test_uses_filename_from_behavior_hints(self) -> None:
        result = parse_stream(
            title=None,
            description=None,
            name=None,
            filename="Movie.720p.BluRay.x264.mkv",
            video_size=None,
        )
        assert result.quality == "720p"
        assert result.codec == "H.264"
        assert result.source == "BluRay"


class TestIsImdbId:
    @pytest.mark.parametrize("value", ["tt1375666", "tt0000001", "tt12345678"])
    def test_valid_imdb_ids(self, value: str) -> None:
        assert is_imdb_id(value) is True

    @pytest.mark.parametrize("value", ["Inception", "tt", "tt-123", "1375666", "nm1375666"])
    def test_invalid_imdb_ids(self, value: str) -> None:
        assert is_imdb_id(value) is False

    def test_strips_whitespace(self) -> None:
        assert is_imdb_id("  tt1375666  ") is True
