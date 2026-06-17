"""
Brightify – SQLAlchemy ORM Models
PostgreSQL database schema for Vietnamese music AI recommendation.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime,
    ForeignKey, Index, UniqueConstraint, SmallInteger, JSON,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


# ============================================================================
# CORE TABLES
# ============================================================================

class Artist(Base):
    """Artist – one row per unique Spotify artist."""
    __tablename__ = "artists"

    artist_id = Column(String(64), primary_key=True, comment="Spotify artist ID")
    name = Column(String(512), nullable=False)
    genres = Column(JSON, default=list, comment="Genre list from Spotify")
    followers = Column(Integer, default=0)
    popularity = Column(SmallInteger, default=0)
    image_url = Column(Text)
    has_image = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    songs = relationship("SongArtist", back_populates="artist")

    __table_args__ = (
        Index("ix_artist_name",      "name"),           # renamed from ix_dim_artist_name (018)
        Index("ix_artist_name_trgm", "name",
              postgresql_using="gin",
              postgresql_ops={"name": "gin_trgm_ops"}),
    )


class Album(Base):
    """Album – one row per unique Spotify album."""
    __tablename__ = "albums"

    album_id = Column(String(64), primary_key=True, comment="Spotify album ID")
    name = Column(String(512), nullable=False)
    album_type = Column(String(32))  # album, single, compilation
    release_date = Column(String(16), comment="YYYY or YYYY-MM-DD")
    release_year = Column(SmallInteger)
    total_tracks = Column(SmallInteger)
    image_url_large = Column(Text)
    image_url_medium = Column(Text)
    image_url_small = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    songs = relationship("Song", back_populates="album")

    __table_args__ = (
        Index("ix_album_name",         "name"),           # renamed from ix_dim_album_name (018)
        Index("ix_album_release_year", "release_year"),   # renamed from ix_dim_album_release_year (018)
    )


class Mood(Base):
    """Mood – Russell's Circumplex quadrants + fine-grained moods."""
    __tablename__ = "moods"

    mood_id = Column(Integer, primary_key=True, autoincrement=True)
    quadrant = Column(String(32), nullable=False, comment="Q1-Q4 with label")
    quadrant_name = Column(String(64), nullable=False)
    mood_label = Column(String(64), unique=True)
    valence_center = Column(Float)
    energy_center = Column(Float)

    songs = relationship("Song", back_populates="mood")

    __table_args__ = (
        Index("ix_mood_mood_label", "mood_label"),  # renamed from ix_dim_mood_mood_label (018)
    )


class Song(Base):
    """Song – the central entity. Every track with audio features."""
    __tablename__ = "songs"

    track_id = Column(String(64), primary_key=True, comment="Spotify track ID")
    track_name = Column(String(512), nullable=False)
    album_id = Column(String(64), ForeignKey("albums.album_id"))
    primary_artist_id = Column(String(64), ForeignKey("artists.artist_id"))
    primary_artist_name = Column(String(512))

    # Spotify metadata
    popularity = Column(SmallInteger, default=0)
    duration_ms = Column(Integer)
    explicit = Column(Boolean, default=False)
    track_url = Column(Text)

    # Album art
    image_url_large = Column(Text)
    image_url_medium = Column(Text)
    image_url_small = Column(Text)
    has_art = Column(Boolean, default=False)

    # Audio features (from ReccoBeats / Spotify)
    danceability = Column(Float)
    energy = Column(Float)
    key = Column(SmallInteger)
    loudness = Column(Float)
    loudness_lufs = Column(Float, nullable=True, comment="Integrated loudness in LUFS (ITU-R BS.1770) — Smart Crossfade")
    mode = Column(SmallInteger)
    # Smart Crossfade Phase 3 — cue points + beat grid
    fade_out_cue_s = Column(Float, nullable=True, comment="Outro start (s) — last structural boundary before silence")
    fade_in_cue_s = Column(Float, nullable=True, comment="Intro end (s) — first structural boundary after silence")
    downbeat_times_json = Column(Text, nullable=True, comment="JSON array of downbeat timestamps for beat-aligned mixing")
    # Smart Crossfade Tier 3 — vocal regions (Demucs stem separation) for vocal-aware mixing
    vocal_start_s = Column(Float, nullable=True, comment="First vocal onset (s) — end of instrumental intro")
    vocal_end_s = Column(Float, nullable=True, comment="Last vocal offset (s) — start of instrumental outro")
    speechiness = Column(Float)
    acousticness = Column(Float)
    instrumentalness = Column(Float)
    liveness = Column(Float)
    valence = Column(Float)
    tempo = Column(Float)
    time_signature = Column(SmallInteger)

    # ML-predicted features (Essentia-TF models)
    # arousal: DEAM (preferred); backfilled from energy when DEAM extraction was skipped
    arousal = Column(Float, nullable=False, comment="DEAM arousal (0-1); falls back to energy")
    timbre_bright = Column(Float, comment="Timbre brightness (0=dark, 1=bright)")

    # Lyrics
    plain_lyrics = Column(Text)
    synced_lyrics = Column(Text)
    instrumental = Column(Boolean, default=False)
    has_lyrics = Column(Boolean, default=False, index=True)
    lyrics_cleaned = Column(Text)

    # Processed features (from process_data.py)
    # color_hex encodes V-A position as perceptual color (Russell's circumplex)
    color_hex = Column(String(8), nullable=False)

    sentiment_compound = Column(Float)
    sentiment_positive = Column(Float)
    sentiment_neutral = Column(Float)
    sentiment_negative = Column(Float)
    sentiment_category = Column(String(16))

    # mood_quadrant: Q1 Happy/Excited | Q2 Angry/Tense | Q3 Sad/Depressed | Q4 Calm/Peaceful
    mood_quadrant = Column(String(32), nullable=False)
    mood_id = Column(Integer, ForeignKey("moods.mood_id"))

    # Media availability
    has_mp3 = Column(Boolean, default=False)
    mp3_filename = Column(String(512))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    album = relationship("Album", back_populates="songs")
    primary_artist = relationship("Artist", foreign_keys=[primary_artist_id])
    mood = relationship("Mood", back_populates="songs")
    artists = relationship("SongArtist", back_populates="song")
    embedding = relationship("SongEmbedding", back_populates="song", uselist=False)

    __table_args__ = (
        # Renamed from ix_dim_song_* (migration 018)
        Index("ix_song_track_name",        "track_name"),
        Index("ix_song_album_id",          "album_id"),
        Index("ix_song_primary_artist_id", "primary_artist_id"),
        Index("ix_song_popularity",        "popularity"),
        Index("ix_song_has_lyrics",        "has_lyrics"),
        # Feature indexes
        Index("ix_song_mood",              "mood_quadrant"),
        Index("ix_song_color",             "color_hex"),
        Index("ix_song_valence_energy",    "valence", "energy"),
        Index("ix_song_track_name_trgm",   "track_name",
              postgresql_using="gin",
              postgresql_ops={"track_name": "gin_trgm_ops"}),
        Index("ix_song_has_mp3",           "has_mp3",
              postgresql_where="has_mp3 = TRUE"),
    )


# ============================================================================
# ASSOCIATION TABLES (many-to-many)
# ============================================================================

class SongArtist(Base):
    """Song ↔ Artist (a track can have multiple artists)."""
    __tablename__ = "song_artists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    track_id = Column(String(64), ForeignKey("songs.track_id"), nullable=False, index=True)
    artist_id = Column(String(64), ForeignKey("artists.artist_id"), nullable=False, index=True)
    is_primary = Column(Boolean, default=False)

    song = relationship("Song", back_populates="artists")
    artist = relationship("Artist", back_populates="songs")

    __table_args__ = (
        UniqueConstraint("track_id", "artist_id", name="uq_song_artist"),
    )


# ============================================================================
# VECTOR TABLE (pgvector)
# ============================================================================

class SongEmbedding(Base):
    """PhoBERT 768-dim lyrics embedding for similarity search."""
    __tablename__ = "song_embeddings"

    track_id = Column(String(64), ForeignKey("songs.track_id"), primary_key=True)
    embedding = Column(Vector(768), nullable=False)
    model_name = Column(String(128), default="vinai/phobert-base")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    song = relationship("Song", back_populates="embedding")
