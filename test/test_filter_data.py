import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.filter_data import (
    catalog_quality_rejection_reason,
    deduplicate_song_entities,
    is_non_original_version,
    run_filter,
)


def _run_filter(rows, tmp_path: Path) -> pd.DataFrame:
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.csv"
    report_path = tmp_path / "report.md"
    pd.DataFrame(rows).to_csv(input_path, index=False)
    return run_filter(input_path=input_path, output_path=output_path, report_path=report_path)


def test_keeps_vietnamese_ascii_title_but_drops_foreign_lyrics(tmp_path: Path):
    rows = [
        {
            "track_id": "keep-open-your-eyes",
            "track_name": "Open Your Eyes",
            "artists": "MONO, Onionn",
            "artist_ids": "a1,a2",
            "primary_artist": "MONO",
            "primary_artist_id": "a1",
            "album_name": "ĐẸP",
            "album_id": "al1",
            "track_duration_ms": 210000,
            "track_popularity": 70,
            "year": 2024,
            "plain_lyrics": "Khép đôi mắt lại để nhìn rõ bản chất trong ta va em. "
            "Mặt trời cười tươi chiếu muôn hoa vàng và đôi chân bước.",
            "instrumental": False,
            "has_lyrics": True,
        },
        {
            "track_id": "keep-be-alright",
            "track_name": "Be Alright",
            "artists": "7UPPERCUTS",
            "artist_ids": "a3",
            "primary_artist": "7UPPERCUTS",
            "primary_artist_id": "a3",
            "album_name": "Summer Jam",
            "album_id": "al3",
            "track_duration_ms": 210000,
            "track_popularity": 70,
            "year": 2024,
            "plain_lyrics": "Could it be that I forgot my falling rights, the right to fall for you. "
            "Whenever I feel like I listened to my heart and here I am in dirt.",
            "instrumental": False,
            "has_lyrics": True,
        },
        {
            "track_id": "drop-rage",
            "track_name": "Rage",
            "artists": "Orkestrated, MIN",
            "artist_ids": "b1,b2",
            "primary_artist": "Orkestrated",
            "primary_artist_id": "b1",
            "album_name": "Minimal Strike",
            "album_id": "al2",
            "track_duration_ms": 210000,
            "track_popularity": 70,
            "year": 2024,
            "plain_lyrics": "Take me back home from these cryptic walls. "
            "I wait for a sign from my own reality in a nameless time.",
            "instrumental": False,
            "has_lyrics": True,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"keep-open-your-eyes", "keep-be-alright"}


def test_direct_vietnamese_artist_evidence_survives_after_dedup(tmp_path: Path):
    rows = [
        {
            "track_id": "keep-khoi-vu",
            "track_name": "Berlin",
            "artists": "Khôi Vũ",
            "artist_ids": "artist-khoi-vu",
            "primary_artist": "Khôi Vũ",
            "primary_artist_id": "artist-khoi-vu",
            "album_name": "Berlin",
            "album_id": "album-berlin",
            "track_duration_ms": 210000,
            "track_popularity": 70,
            "year": 2024,
            "plain_lyrics": "Anh đi qua thành phố và nhớ em trong một chiều mưa.",
            "instrumental": False,
            "has_lyrics": True,
        },
        {
            "track_id": "keep-pay-feature",
            "track_name": "Summer Vibe",
            "artists": "Pay, Thịnh Suy",
            "artist_ids": "artist-pay,artist-thinh-suy",
            "primary_artist": "Pay",
            "primary_artist_id": "artist-pay",
            "album_name": "Summer Vibe",
            "album_id": "album-summer-vibe",
            "track_duration_ms": 210000,
            "track_popularity": 70,
            "year": 2024,
            "plain_lyrics": "Mùa hè đi qua cùng em và những ngày nắng trong veo.",
            "instrumental": False,
            "has_lyrics": True,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"keep-khoi-vu", "keep-pay-feature"}


def test_catalog_quality_rejects_instrumental_speech_fragments_and_legacy():
    assert catalog_quality_rejection_reason(
        {
            "track_id": "FVN2srj9OIk",
            "track_name": "Khúc Hát Chim Trời",
            "album_name": "Khúc Hát Chim Trời",
            "track_duration_ms": 131_000,
        }
    ) == "verified_wrong_content"
    assert catalog_quality_rejection_reason(
        {
            "track_id": "score",
            "track_name": "A Trap",
            "album_name": "Original Motion Picture Soundtracks",
            "primary_artist_id": "UCNctzUfSQywEVfR-L8fUXFw",
            "track_duration_ms": 86_000,
        }
    ) == "soundtrack_score_catalog"
    assert catalog_quality_rejection_reason(
        {
            "track_id": "tv-cut",
            "track_name": "Sau Tất Cả",
            "album_name": "Sàn Đấu Ca Từ Mùa 3 Tập 3",
            "track_duration_ms": 127_000,
        }
    ) == "fragment_or_program_excerpt"
    assert catalog_quality_rejection_reason(
        {
            "track_id": "tv-full",
            "track_name": "Ánh Nắng Của Anh",
            "album_name": "Sàn Đấu Ca Từ Mùa 4 Tập 5",
            "track_duration_ms": 261_000,
        }
    ) == "fragment_or_program_excerpt"
    assert catalog_quality_rejection_reason(
        {
            "track_id": "voice-show",
            "track_name": "Một Ca Khúc",
            "album_name": "Sàn Chiến Giọng Hát 7",
            "track_duration_ms": 273_000,
        }
    ) == "fragment_or_program_excerpt"
    assert catalog_quality_rejection_reason(
        {
            "track_id": "instrumental",
            "track_name": "Hoa Đầu Mùa",
            "track_duration_ms": 193_000,
        },
        {
            "instrumental_probability": 0.78,
            "voice_probability": 0.22,
            "yamnet_singing_mean": 0.003,
        },
    ) == "instrumental_audio"
    assert catalog_quality_rejection_reason(
        {
            "track_id": "spoken",
            "track_name": "A Program Cut",
            "track_duration_ms": 160_000,
        },
        {
            "yamnet_speech_mean": 0.20,
            "yamnet_music_mean": 0.30,
            "yamnet_singing_mean": 0.01,
            "speech_dominant_fraction": 0.20,
        },
    ) == "spoken_audio"


def test_short_track_floor_keeps_only_editorial_allowlist(tmp_path: Path):
    common = {
        "artist_ids": "artist",
        "primary_artist_id": "artist",
        "album_id": "album",
        "track_popularity": 80,
        "year": 2024,
        "instrumental": False,
        "has_lyrics": True,
    }
    rows = [
        {
            **common,
            "track_id": "TpO5ZVEB3Ek",
            "track_name": "Hạt Giống Số 1",
            "artists": "24k.Right",
            "primary_artist": "24k.Right",
            "album_name": "Hạt Giống Số 1",
            "track_duration_ms": 111000,
            "plain_lyrics": "Người Việt bay trên đất Việt và bước đi trong ngày mới.",
        },
        {
            **common,
            "track_id": "Ety-Zn2nPfs",
            "track_name": "On My Own",
            "artists": "7UPPERCUTS",
            "primary_artist": "7UPPERCUTS",
            "album_name": "Summer Jam",
            "track_duration_ms": 96000,
            "plain_lyrics": "It's like I'm on my own tonight, I missed the train back home.",
        },
        {
            **common,
            "track_id": "drop-short-normal",
            "track_name": "Bài Ngắn Thường",
            "artists": "MONO",
            "primary_artist": "MONO",
            "album_name": "Bài Ngắn Thường",
            "track_duration_ms": 149000,
            "plain_lyrics": "Anh đi qua mùa hè và nghe thành phố gọi tên em.",
        },
        {
            **common,
            "track_id": "keep-long",
            "track_name": "Bài Đủ Dài",
            "artists": "MONO",
            "primary_artist": "MONO",
            "album_name": "Bài Đủ Dài",
            "track_duration_ms": 150000,
            "plain_lyrics": "Anh đi qua mùa hè và nghe thành phố gọi tên em.",
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"TpO5ZVEB3Ek", "keep-long"}


def test_non_original_version_rejects_medleys_and_named_performance_shows():
    assert is_non_original_version(
        "LK Tình Đơn Phương / Cuộc Tình Trong Cơn Mưa"
    )
    assert is_non_original_version("Liên Khúc Tình Yêu")
    assert is_non_original_version("Suýt Nữa Thì - In The Moonlight Show")
    assert is_non_original_version("Thiên Thần Ác Quỷ - A COLORS SHOW")
    assert not is_non_original_version("Show Me Love", "99%")
    assert catalog_quality_rejection_reason(
        {
            "track_id": "too-long",
            "track_name": "Một Liên Khúc",
            "track_duration_ms": 320_000,
        },
        {"actual_duration_s": 620.0},
    ) == "actual_duration_out_of_range"
    assert catalog_quality_rejection_reason(
        {
            "track_id": "valid-long-current-song",
            "track_name": "Một Bài Hát Mới",
            "album_name": "Một Bài Hát Mới",
            "track_duration_ms": 330_000,
        },
        {
            "instrumental_probability": 0.12,
            "voice_probability": 0.88,
        },
    ) is None


def test_entity_dedup_merges_swapped_primary_artist_and_credits():
    rows = [
        {
            "track_id": "den-primary",
            "track_name": "Bài Này Chill Phết",
            "artists": "Đen, MIN",
            "artist_ids": "den,min",
            "primary_artist": "Đen",
            "primary_artist_id": "den",
            "track_duration_ms": 277000,
            "plain_lyrics": "Một đoạn lời đủ dài " * 20,
            "view_count": 200000,
        },
        {
            "track_id": "min-primary",
            "track_name": "Bài Này Chill Phết (feat. Đen)",
            "artists": "MIN, Đen",
            "artist_ids": "min,den",
            "primary_artist": "MIN",
            "primary_artist_id": "min",
            "track_duration_ms": 277000,
            "plain_lyrics": "Một đoạn lời đủ dài " * 20,
            "view_count": None,
        },
    ]

    result, removed = deduplicate_song_entities(pd.DataFrame(rows))

    assert removed == 1
    assert result["track_id"].tolist() == ["den-primary"]
    assert set(result.iloc[0]["artists"].split(", ")) == {"Đen", "MIN"}


def test_entity_dedup_merges_cross_uploader_when_lyrics_and_duration_match():
    rows = [
        {
            "track_id": "lead-upload",
            "track_name": "Ai Cũng Có Một Ngày Dài",
            "artists": "Lil Ce, Pjpo, Blacka",
            "artist_ids": "lilce,pjpo,blacka",
            "primary_artist": "Lil Ce",
            "primary_artist_id": "lilce",
            "track_duration_ms": 268000,
            "plain_lyrics": "Ngày dài trôi qua và ta vẫn bước tiếp " * 12,
        },
        {
            "track_id": "second-upload",
            "track_name": "Ai Cũng Có Một Ngày Dài (feat. Blacka)",
            "artists": "Channel Upload",
            "artist_ids": "channel-profile",
            "primary_artist": "Channel Upload",
            "primary_artist_id": "channel-profile",
            "track_duration_ms": 269000,
            "plain_lyrics": "Ngày dài trôi qua và ta vẫn bước tiếp " * 12,
        },
    ]

    audio_embeddings = {
        "lead-upload": [1.0, 0.0, 0.0],
        "second-upload": [0.999, 0.001, 0.0],
    }
    result, removed = deduplicate_song_entities(
        pd.DataFrame(rows),
        audio_embeddings=audio_embeddings,
    )

    assert removed == 1
    assert len(result) == 1


def test_entity_dedup_keeps_cross_artist_same_lyrics_when_audio_differs():
    lyrics = "Một lyrics có thể bị dịch vụ bên ngoài gán nhầm cho hai bài " * 12
    rows = [
        {
            "track_id": "artist-one",
            "track_name": "Hành Tinh Ánh Sáng",
            "artists": "Juky San",
            "artist_ids": "juky",
            "primary_artist": "Juky San",
            "primary_artist_id": "juky",
            "track_duration_ms": 219000,
            "plain_lyrics": lyrics,
        },
        {
            "track_id": "artist-two",
            "track_name": "Hành Tinh Ánh Sáng",
            "artists": "Vũ Cát Tường",
            "artist_ids": "vct",
            "primary_artist": "Vũ Cát Tường",
            "primary_artist_id": "vct",
            "track_duration_ms": 228000,
            "plain_lyrics": lyrics,
        },
    ]
    audio_embeddings = {
        "artist-one": [1.0, 0.0, 0.0],
        "artist-two": [0.0, 1.0, 0.0],
    }

    result, removed = deduplicate_song_entities(
        pd.DataFrame(rows),
        audio_embeddings=audio_embeddings,
    )

    assert removed == 0
    assert len(result) == 2


def test_entity_dedup_keeps_distinct_covers_with_different_duration():
    lyrics = "Có chàng trai viết lên cây lời yêu thương năm ấy " * 12
    rows = [
        {
            "track_id": "original",
            "track_name": "Có Chàng Trai Viết Lên Cây",
            "artists": "Phan Mạnh Quỳnh",
            "artist_ids": "pmq",
            "primary_artist": "Phan Mạnh Quỳnh",
            "primary_artist_id": "pmq",
            "track_duration_ms": 311000,
            "plain_lyrics": lyrics,
        },
        {
            "track_id": "cover",
            "track_name": "Có Chàng Trai Viết Lên Cây",
            "artists": "Hà Anh Tuấn",
            "artist_ids": "hat",
            "primary_artist": "Hà Anh Tuấn",
            "primary_artist_id": "hat",
            "track_duration_ms": 342000,
            "plain_lyrics": lyrics,
        },
    ]

    result, removed = deduplicate_song_entities(pd.DataFrame(rows))

    assert removed == 0
    assert set(result["track_id"]) == {"original", "cover"}


def test_entity_dedup_keeps_same_artist_title_when_content_differs():
    rows = [
        {
            "track_id": "song-a",
            "track_name": "Người Đầu Tiên (feat. A)",
            "artists": "Juky San",
            "artist_ids": "juky",
            "primary_artist": "Juky San",
            "primary_artist_id": "juky",
            "track_duration_ms": 200000,
            "plain_lyrics": "Lời của ca khúc thứ nhất hoàn toàn riêng biệt " * 12,
        },
        {
            "track_id": "song-b",
            "track_name": "Người Đầu Tiên (feat. B)",
            "artists": "Juky San",
            "artist_ids": "juky",
            "primary_artist": "Juky San",
            "primary_artist_id": "juky",
            "track_duration_ms": 240000,
            "plain_lyrics": "Nội dung của bài hát thứ hai không giống bài trước " * 12,
        },
    ]

    result, removed = deduplicate_song_entities(pd.DataFrame(rows))

    assert removed == 0
    assert len(result) == 2


def test_filter_removes_duet_version(tmp_path: Path):
    rows = [
        {
            "track_id": "duet-version",
            "track_name": "Không Lời (Duet)",
            "artists": "Thiều Bảo Trâm, Guest",
            "artist_ids": "tbt,guest",
            "primary_artist": "Thiều Bảo Trâm",
            "primary_artist_id": "tbt",
            "album_name": "Không Lời (Duet)",
            "track_duration_ms": 220000,
            "track_popularity": 60,
            "year": 2025,
            "plain_lyrics": "Một đoạn lời tiếng Việt đủ dài để vượt qua kiểm tra ngôn ngữ.",
            "instrumental": False,
            "has_lyrics": True,
        }
    ]

    assert _run_filter(rows, tmp_path).empty


def test_keeps_verified_soundtrack_song_but_drops_obscure_score(tmp_path: Path):
    rows = [
        {
            "track_id": "keep-vocal-ost",
            "track_name": "Mất Nhau",
            "artists": "Anh Tú",
            "artist_ids": "artist-anh-tu",
            "primary_artist": "Anh Tú",
            "primary_artist_id": "artist-anh-tu",
            "album_name": 'Mất Nhau - Original Soundtrack From "Yêu Trước Ngày Cưới"',
            "album_id": "album-vocal-ost",
            "track_duration_ms": 210000,
            "track_popularity": 70,
            "year": 2024,
            "plain_lyrics": "Điều gì có thể làm ta đau hơn khi đến cuối chỉ bước đi mình ta.",
            "instrumental": False,
            "has_lyrics": True,
        },
        {
            "track_id": "drop-obscure-score",
            "track_name": "The Wrong Survivor",
            "artists": "Khuất Duy Minh",
            "artist_ids": "artist-score-composer",
            "primary_artist": "Khuất Duy Minh",
            "primary_artist_id": "artist-score-composer",
            "album_name": "Ốc Mượn Hồn (Original Motion Picture Soundtrack)",
            "album_id": "album-score",
            "track_duration_ms": 210000,
            "track_popularity": None,
            "year": 2025,
            "plain_lyrics": "Một đoạn lời bị ghép nhầm không đủ để biến nhạc nền thành ca khúc pop.",
            "instrumental": False,
            "has_lyrics": True,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"keep-vocal-ost"}


def test_drops_seasonal_and_profane_tracks(tmp_path: Path):
    rows = [
        {
            "track_id": "drop-xuan-son",
            "track_name": "Xuân Son",
            "artists": "2Can, Jombie",
            "artist_ids": "c1,c2",
            "primary_artist": "2Can",
            "primary_artist_id": "c1",
            "album_name": "Xuân Son",
            "album_id": "al3",
            "track_duration_ms": 210000,
            "track_popularity": 65,
            "year": 2024,
            "plain_lyrics": "Cái địt con mẹ đời này. Đéo cần quan tâm gì đến tụi mày. "
            "Sống như lồn và og con cặc gì.",
            "instrumental": False,
            "has_lyrics": True,
        },
        {
            "track_id": "keep-lang-thang",
            "track_name": "Cho Tôi Lang Thang",
            "artists": "Ngọt, Đen",
            "artist_ids": "d2,d3",
            "primary_artist": "Ngọt",
            "primary_artist_id": "d2",
            "album_name": "Cho Tôi Lang Thang",
            "album_id": "al4b",
            "track_duration_ms": 210000,
            "track_popularity": 75,
            "year": 2024,
            "plain_lyrics": "Nơi nhân gian sum vầy em có nghe thấy tiếng réo gọi tâm hồn. "
            "Ngày lang thang trong cơn mơ không veston không cà vạt.",
            "instrumental": False,
            "has_lyrics": True,
        },
        {
            "track_id": "drop-mung-xuan",
            "track_name": "Mừng Xuân 2026",
            "artists": "ERIK",
            "artist_ids": "d1",
            "primary_artist": "ERIK",
            "primary_artist_id": "d1",
            "album_name": "Nhạc Tết 2026",
            "album_id": "al4",
            "track_duration_ms": 210000,
            "track_popularity": 75,
            "year": 2026,
            "plain_lyrics": "Chúc tết chúc xuân năm mới bình an và tài lộc.",
            "instrumental": False,
            "has_lyrics": True,
        },
        {
            "track_id": "keep-clean",
            "track_name": "Đi Về Phía Mặt Trời",
            "artists": "2Can",
            "artist_ids": "c1",
            "primary_artist": "2Can",
            "primary_artist_id": "c1",
            "album_name": "Đi Về Phía Mặt Trời",
            "album_id": "al5",
            "track_duration_ms": 210000,
            "track_popularity": 75,
            "year": 2024,
            "plain_lyrics": "Bàn tay phải lau mồ hôi và lo đồng lương cho ngày mai. "
            "Tôi kể câu chuyện của mình trên bản nhạc.",
            "instrumental": False,
            "has_lyrics": True,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"keep-clean", "keep-lang-thang"}


def test_seasonal_filter_catches_clear_spring_holiday_titles_only(tmp_path: Path):
    common = {
        "artist_ids": "artist",
        "primary_artist_id": "artist",
        "album_id": "album",
        "track_duration_ms": 210000,
        "track_popularity": 70,
        "year": 2024,
        "instrumental": False,
        "has_lyrics": True,
    }
    rows = [
        {
            **common,
            "track_id": "drop-mua-xuan",
            "track_name": "Mùa Xuân Ơi",
            "artists": "Bích Phượng",
            "primary_artist": "Bích Phượng",
            "album_name": "Bao Giờ Lấy Chồng",
            "plain_lyrics": "Mùa xuân về trên phố, mọi nhà cùng đón năm mới bình an.",
        },
        {
            **common,
            "track_id": "keep-xuan-thi",
            "track_name": "Xuân Thì",
            "artists": "Phan Mạnh Quỳnh",
            "primary_artist": "Phan Mạnh Quỳnh",
            "album_name": "CineLove",
            "plain_lyrics": "Gặp em trong những người bạn thân quen một ngày mùa đông.",
        },
        {
            **common,
            "track_id": "keep-esports-spring",
            "track_name": "KEEP FIGHTING (Đấu Trường Danh Vọng mùa Xuân 2021)",
            "artists": "Thành Draw",
            "primary_artist": "Thành Draw",
            "album_name": "KEEP FIGHTING",
            "plain_lyrics": "Ta đã đi trên chặng đường này quá lâu và vẫn tiếp tục chiến đấu.",
        },
        {
            **common,
            "track_id": "keep-spring-metaphor",
            "track_name": "Một Buổi Sáng Mùa Xuân / Người",
            "artists": "Hà Anh Tuấn",
            "primary_artist": "Hà Anh Tuấn",
            "album_name": "Losing You",
            "plain_lyrics": "Đôi khi tôi ngồi dưới cây rụng lá không ưu tư và nghĩ suy gì.",
        },
        {
            **common,
            "track_id": "drop-spring-album",
            "track_name": "Lúng La Lúng Luyến Xuân",
            "artists": "Anh Tú",
            "primary_artist": "Anh Tú",
            "album_name": "Giai Điệu Mùa Xuân",
            "plain_lyrics": "Mùa xuân đến đây, lúng la lúng liếng duyên.",
        },
        {
            **common,
            "track_id": "drop-tet-lyrics",
            "track_name": "Cơm Đoàn Viên",
            "artists": "Quốc Thiên",
            "primary_artist": "Quốc Thiên",
            "album_name": "Cơm Đoàn Viên",
            "plain_lyrics": (
                "Tết này con đi làm xa không ở nhà. "
                "Thành phố lớn Tết đến càng cô đơn, pháo hoa sáng trời."
            ),
        },
        {
            **common,
            "track_id": "keep-wrong-seasonal-lyrics",
            "track_name": "Nếu Mình Gần Nhau",
            "artists": "Đen, Chi Pu",
            "primary_artist": "Đen",
            "album_name": "Nếu Mình Gần Nhau",
            "plain_lyrics": (
                "Tết này chúc nhau năm mới, Tết đến bên nhau. "
                "Dữ liệu lời này bị gán nhầm nên không được dùng một mình."
            ),
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {
        "keep-xuan-thi",
        "keep-esports-spring",
        "keep-spring-metaphor",
        "keep-wrong-seasonal-lyrics",
    }


def test_old_genre_filter_checks_all_artists_not_only_primary(tmp_path: Path):
    rows = [
        {
            "track_id": "drop-old-feature",
            "track_name": "Tình Ca",
            "artists": "ERIK, Le Thuy",
            "artist_ids": "e1,e2",
            "primary_artist": "ERIK",
            "primary_artist_id": "e1",
            "album_name": "Tình Ca",
            "album_id": "al6",
            "track_duration_ms": 210000,
            "track_popularity": 80,
            "year": 2024,
            "plain_lyrics": "Anh và em đi qua con phố rất dài trong mưa đêm.",
            "instrumental": False,
            "has_lyrics": True,
        },
        {
            "track_id": "keep-modern",
            "track_name": "Chạm Em Một Chút Nhẹ",
            "artists": "ERIK, MIN",
            "artist_ids": "e1,e3",
            "primary_artist": "ERIK",
            "primary_artist_id": "e1",
            "album_name": "Chạm Em Một Chút Nhẹ",
            "album_id": "al7",
            "track_duration_ms": 210000,
            "track_popularity": 80,
            "year": 2024,
            "plain_lyrics": "Anh ơi em đang chờ một điều nho nhỏ giữa đêm.",
            "instrumental": False,
            "has_lyrics": True,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"keep-modern"}


def test_keeps_lyrics_with_only_light_profanity(tmp_path: Path):
    rows = [
        {
            "track_id": "keep-light-profanity",
            "track_name": "Lối Sống",
            "artists": "Wxrdie",
            "artist_ids": "f1",
            "primary_artist": "Wxrdie",
            "primary_artist_id": "f1",
            "album_name": "THE WXRDIES",
            "album_id": "al8",
            "track_duration_ms": 210000,
            "track_popularity": 80,
            "year": 2024,
            "plain_lyrics": "Trong số bọn tao có thằng tết tóc có thằng dreadlocks. "
            "Chúng mày đéo có cảnh, nhưng vẫn đéo rõ mày là lồn nào.",
            "instrumental": False,
            "has_lyrics": True,
        },
        {
            "track_id": "drop-heavy-profanity",
            "track_name": "Xuân Son",
            "artists": "2Can, Jombie",
            "artist_ids": "f2,f3",
            "primary_artist": "2Can",
            "primary_artist_id": "f2",
            "album_name": "Xuân Son",
            "album_id": "al9",
            "track_duration_ms": 210000,
            "track_popularity": 80,
            "year": 2024,
            "plain_lyrics": "Cái địt con mẹ đời này. Đéo cần quan tâm gì đến tụi mày. "
            "Sống như lồn, con cặc gì, đéo đéo đéo.",
            "instrumental": False,
            "has_lyrics": True,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"keep-light-profanity"}


def test_non_artist_channel_filter_uses_primary_artist_only(tmp_path: Path):
    rows = [
        {
            "track_id": "keep-featured-channelish",
            "track_name": "Bỗng Dưng",
            "artists": "1nG, VoVanDuc",
            "artist_ids": "g1,g2",
            "primary_artist": "1nG",
            "primary_artist_id": "g1",
            "album_name": "Bỗng Dưng",
            "album_id": "al10",
            "track_duration_ms": 210000,
            "track_popularity": 70,
            "year": 2024,
            "plain_lyrics": "Nhìn thành phố lên đèn, anh nhớ em giữa cơn mưa phùn. "
            "Bao câu nói trong tim vẫn còn nguyên như lúc đầu.",
            "instrumental": False,
            "has_lyrics": True,
        },
        {
            "track_id": "drop-primary-channel",
            "track_name": "Fake Channel Song",
            "artists": "Feliks Alvin, RHYDER",
            "artist_ids": "g3,g4",
            "primary_artist": "Feliks Alvin",
            "primary_artist_id": "g3",
            "album_name": "Feliks Alvin Collection",
            "album_id": "al11",
            "track_duration_ms": 210000,
            "track_popularity": 70,
            "year": 2024,
            "plain_lyrics": "Anh chỉ muốn hát lên một bài ca không tên giữa đêm nay.",
            "instrumental": False,
            "has_lyrics": True,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"keep-featured-channelish"}


def test_current_artist_bypasses_stale_artist_blocks_but_not_track_year(tmp_path: Path):
    rows = [
        {
            "track_id": "keep-current-khac-viet",
            "track_name": "Bài Hát Mới",
            "artists": "Khắc Việt",
            "artist_ids": "h1",
            "primary_artist": "Khắc Việt",
            "primary_artist_id": "h1",
            "album_name": "Bài Hát Mới",
            "album_id": "al12",
            "track_duration_ms": 210000,
            "track_popularity": 60,
            "year": 2025,
            "plain_lyrics": "Anh vẫn đi qua con phố và nhớ em trong một chiều mưa.",
            "instrumental": False,
            "has_lyrics": True,
        },
        {
            "track_id": "drop-old-khac-viet",
            "track_name": "Bài Hát Cũ",
            "artists": "Khắc Việt",
            "artist_ids": "h1",
            "primary_artist": "Khắc Việt",
            "primary_artist_id": "h1",
            "album_name": "Bài Hát Cũ",
            "album_id": "al13",
            "track_duration_ms": 210000,
            "track_popularity": 60,
            "year": 2010,
            "plain_lyrics": "Anh vẫn đi qua con phố và nhớ em trong một chiều mưa.",
            "instrumental": False,
            "has_lyrics": True,
        },
        {
            "track_id": "keep-captain-boy",
            "track_name": "Mong Em Sẽ Cố Quên",
            "artists": "Captain Boy",
            "artist_ids": "h2",
            "primary_artist": "Captain Boy",
            "primary_artist_id": "h2",
            "album_name": "Mong Em Sẽ Cố Quên",
            "album_id": "al14",
            "track_duration_ms": 210000,
            "track_popularity": 50,
            "year": 2024,
            "plain_lyrics": "Mong em sẽ cố quên những ngày mình từng ở bên nhau.",
            "instrumental": False,
            "has_lyrics": True,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"keep-current-khac-viet", "keep-captain-boy"}


def test_current_artist_does_not_bypass_old_genre_or_popularity(tmp_path: Path):
    rows = [
        {
            "track_id": "drop-current-bolero",
            "track_name": "Tình Buồn Bolero",
            "artists": "Khắc Việt",
            "primary_artist": "Khắc Việt",
            "album_name": "Tuyển Tập Nhạc Vàng",
            "track_duration_ms": 210000,
            "track_popularity": 60,
            "year": 2025,
        },
        {
            "track_id": "drop-current-low-pop",
            "track_name": "Một Bài Không Hot",
            "artists": "Hồ Quang Hiếu",
            "primary_artist": "Hồ Quang Hiếu",
            "album_name": "Single",
            "track_duration_ms": 210000,
            "track_popularity": 10,
            "year": 2025,
        },
        {
            "track_id": "drop-current-old-genre-metadata",
            "track_name": "Duyên Phận",
            "artists": "Hồ Quang Hiếu",
            "primary_artist": "Hồ Quang Hiếu",
            "album_name": "Single",
            "artist_genres": "v-pop, vietnamese bolero",
            "track_duration_ms": 210000,
            "track_popularity": 60,
            "year": 2025,
        },
        {
            "track_id": "keep-current-modern",
            "track_name": "Một Bài Pop Mới",
            "artists": "Hồ Quang Hiếu",
            "primary_artist": "Hồ Quang Hiếu",
            "album_name": "Single",
            "track_duration_ms": 210000,
            "track_popularity": 45,
            "year": 2025,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"keep-current-modern"}


def test_post_download_view_floor_removes_obscure_tracks(tmp_path: Path):
    rows = [
        {
            "track_id": "drop-low-views",
            "track_name": "Bài Mới Ít Người Nghe",
            "artists": "Captain Boy",
            "primary_artist": "Captain Boy",
            "album_name": "Single",
            "track_duration_ms": 210000,
            "year": 2025,
            "view_count": 25_000,
        },
        {
            "track_id": "keep-enough-views",
            "track_name": "Bài Mới Được Quan Tâm",
            "artists": "Captain Boy",
            "primary_artist": "Captain Boy",
            "album_name": "Single",
            "track_duration_ms": 210000,
            "year": 2025,
            "view_count": 500_000,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"keep-enough-views"}


def test_recent_release_uses_lower_view_floor_without_artist_penalty(tmp_path: Path):
    rows = [
        {
            "track_id": "keep-established-artist",
            "track_name": "Bài Mới Được Quan Tâm",
            "artists": "Khắc Việt",
            "primary_artist": "Khắc Việt",
            "album_name": "Single",
            "track_duration_ms": 210000,
            "year": 2025,
            "view_count": 200_000,
        },
        {
            "track_id": "keep-recent-momentum",
            "track_name": "Bài Mới Có Đà Tăng",
            "artists": "Hồ Quang Hiếu",
            "primary_artist": "Hồ Quang Hiếu",
            "album_name": "Single",
            "track_duration_ms": 210000,
            "year": 2025,
            "view_count": 60_000,
        },
        {
            "track_id": "drop-recent-too-low",
            "track_name": "Bài Mới Quá Ít Người Nghe",
            "artists": "Khắc Việt",
            "primary_artist": "Khắc Việt",
            "album_name": "Single",
            "track_duration_ms": 210000,
            "year": 2025,
            "view_count": 20_000,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {
        "keep-established-artist",
        "keep-recent-momentum",
    }


def test_foreign_identity_release_is_not_saved_by_known_artist_name(tmp_path: Path):
    rows = [
        {
            "track_id": "drop-orange-collision",
            "track_name": "Sinag",
            "artists": "Orange",
            "primary_artist": "Orange",
            "album_name": "Project Outbreak",
            "track_duration_ms": 186000,
            "track_popularity": 60,
            "year": 2014,
            "plain_lyrics": "Dalangin ang lagi mong habilin at ang iyong sinag ay nauuna pa sa araw. " * 4,
            "instrumental": False,
            "has_lyrics": True,
        },
        {
            "track_id": "drop-obscure-english",
            "track_name": "SHAME",
            "artists": "tanny ng, kinu",
            "primary_artist": "tanny ng",
            "album_name": "SHAME",
            "track_duration_ms": 152000,
            "track_popularity": 60,
            "year": 2023,
            "plain_lyrics": "She falls in love with cigarettes on the floor and calls me late at night. " * 4,
            "instrumental": False,
            "has_lyrics": True,
        },
        {
            "track_id": "keep-established-english",
            "track_name": "Be Alright",
            "artists": "7UPPERCUTS",
            "primary_artist": "7UPPERCUTS",
            "album_name": "Summer Jam",
            "track_duration_ms": 210000,
            "track_popularity": 60,
            "year": 2023,
            "plain_lyrics": "Could it be that I forgot my falling rights and listened to my heart. " * 4,
            "instrumental": False,
            "has_lyrics": True,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"keep-established-english"}


def test_emerging_artist_keeps_only_tracks_with_a_hot_signal(tmp_path: Path):
    rows = [
        {
            "track_id": "keep-emerging-hit",
            "track_name": "Bài Hit Đầu Tay",
            "artists": "Nghệ Sĩ Gen Z Mới",
            "primary_artist": "Nghệ Sĩ Gen Z Mới",
            "album_name": "EP Đầu Tay",
            "track_duration_ms": 210000,
            "track_popularity": 8,
            "view_count": 1_500_000,
            "year": 2025,
        },
        {
            "track_id": "drop-emerging-deep-cut",
            "track_name": "Bài Ít Người Nghe",
            "artists": "Nghệ Sĩ Gen Z Mới",
            "primary_artist": "Nghệ Sĩ Gen Z Mới",
            "album_name": "EP Đầu Tay",
            "track_duration_ms": 210000,
            "track_popularity": 8,
            "view_count": 20_000,
            "year": 2025,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"keep-emerging-hit"}


def test_variant_album_is_removed_and_original_wins_dedup(tmp_path: Path):
    rows = [
        {
            "track_id": "variant-acoustic",
            "track_name": "Bài Hát",
            "artists": "AMEE",
            "primary_artist": "AMEE",
            "album_name": "EP Acoustic",
            "track_duration_ms": 210000,
            "track_popularity": 80,
            "year": 2025,
        },
        {
            "track_id": "original-studio",
            "track_name": "Bài Hát",
            "artists": "AMEE",
            "primary_artist": "AMEE",
            "album_name": "Album Phòng Thu",
            "track_duration_ms": 210000,
            "track_popularity": 80,
            "year": 2025,
        },
        {
            "track_id": "variant-remxi-typo",
            "track_name": "Bài Khác (Remxi Ver.)",
            "artists": "AMEE",
            "primary_artist": "AMEE",
            "album_name": "Single",
            "track_duration_ms": 210000,
            "track_popularity": 80,
            "year": 2025,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"original-studio"}


def test_unlabeled_performance_and_arrangement_suffixes_are_removed(tmp_path: Path):
    common = {
        "artists": "Đen",
        "artist_ids": "den",
        "primary_artist": "Đen",
        "primary_artist_id": "den",
        "album_id": "album",
        "track_duration_ms": 210000,
        "track_popularity": 70,
        "year": 2024,
        "plain_lyrics": "Một bài hát Việt Nam có lời đầy đủ để vượt qua các lớp ngôn ngữ.",
        "instrumental": False,
        "has_lyrics": True,
    }
    rows = [
        {
            **common,
            "track_id": "keep-original",
            "track_name": "Bài Này Chill Phết",
            "album_name": "Bài Này Chill Phết",
        },
        {
            **common,
            "track_id": "drop-harmony",
            "track_name": "Bài Này Chill Phết (dongvui harmony)",
            "album_name": "dongvui harmony",
        },
        {
            **common,
            "track_id": "drop-romance",
            "track_name": "Có Chàng Trai Viết Lên Cây (Romance)",
            "album_name": "Đi Đâu Để Thấy Hoa Bay",
        },
        {
            **common,
            "track_id": "drop-first-version",
            "track_name": "Người Đầu Tiên (Bản Đầu Tiên)",
            "album_name": "Đẫm Tình",
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"keep-original"}


def test_dedup_prefers_original_with_higher_views(tmp_path: Path):
    rows = [
        {
            "track_id": "metadata-poor-copy",
            "track_name": "Bài Trùng",
            "artists": "JUUN D",
            "primary_artist": "JUUN D",
            "primary_artist_id": "same-artist",
            "album_name": "Single",
            "track_duration_ms": 210000,
            "view_count": None,
            "year": 2025,
        },
        {
            "track_id": "official-high-view",
            "track_name": "Bài Trùng",
            "artists": "Juun Đăng Dũng",
            "primary_artist": "Juun Đăng Dũng",
            "primary_artist_id": "same-artist",
            "album_name": "Single",
            "track_duration_ms": 210000,
            "view_count": 10_000_000,
            "year": 2025,
        },
    ]

    df = _run_filter(rows, tmp_path)

    assert set(df["track_id"]) == {"official-high-view"}
