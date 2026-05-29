"""
Brightify – SQLAlchemy ORM Models
PostgreSQL database schema for Vietnamese music AI recommendation.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, BigInteger, Float, Boolean, Text, DateTime,
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
    name = Column(String(512), nullable=False, index=True)
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
        Index("ix_artist_name_trgm", "name",
              postgresql_using="gin",
              postgresql_ops={"name": "gin_trgm_ops"}),
    )


class Album(Base):
    """Album – one row per unique Spotify album."""
    __tablename__ = "albums"

    album_id = Column(String(64), primary_key=True, comment="Spotify album ID")
    name = Column(String(512), nullable=False, index=True)
    album_type = Column(String(32))  # album, single, compilation
    release_date = Column(String(16), comment="YYYY or YYYY-MM-DD")
    release_year = Column(SmallInteger, index=True)
    total_tracks = Column(SmallInteger)
    image_url_large = Column(Text)
    image_url_medium = Column(Text)
    image_url_small = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    songs = relationship("Song", back_populates="album")


class Genre(Base):
    """Genre for analytical slicing."""
    __tablename__ = "genres"

    genre_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    artists = relationship("ArtistGenre", back_populates="genre")


class Mood(Base):
    """Mood – Russell's Circumplex quadrants + fine-grained moods."""
    __tablename__ = "moods"

    mood_id = Column(Integer, primary_key=True, autoincrement=True)
    quadrant = Column(String(32), nullable=False, comment="Q1-Q4 with label")
    quadrant_name = Column(String(64), nullable=False)
    mood_label = Column(String(64), unique=True, index=True)
    valence_center = Column(Float)
    energy_center = Column(Float)

    songs = relationship("Song", back_populates="mood")


class Song(Base):
    """Song – the central entity. Every track with audio features."""
    __tablename__ = "songs"

    track_id = Column(String(64), primary_key=True, comment="Spotify track ID")
    track_name = Column(String(512), nullable=False, index=True)
    album_id = Column(String(64), ForeignKey("albums.album_id"), index=True)
    primary_artist_id = Column(String(64), ForeignKey("artists.artist_id"), index=True)
    primary_artist_name = Column(String(512))

    # Spotify metadata
    isrc = Column(String(16))
    track_number = Column(SmallInteger)
    disc_number = Column(SmallInteger)
    popularity = Column(SmallInteger, default=0, index=True)
    duration_ms = Column(Integer)
    explicit = Column(Boolean, default=False)
    track_url = Column(Text)
    preview_url = Column(Text)
    available_markets_count = Column(SmallInteger)

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
    speechiness = Column(Float)
    acousticness = Column(Float)
    instrumentalness = Column(Float)
    liveness = Column(Float)
    valence = Column(Float)
    tempo = Column(Float)
    time_signature = Column(SmallInteger)
    has_audio_features = Column(Boolean, default=False)

    # ML-predicted features (Essentia-TF models)
    arousal = Column(Float, comment="DEAM arousal (0-1)")
    timbre_bright = Column(Float, comment="Timbre brightness (0=dark, 1=bright)")
    mood_tags = Column(JSON, comment="MTG-Jamendo mood/theme predictions")
    instrument_tags = Column(JSON, comment="MTG-Jamendo instrument predictions")
    voice_gender = Column(String(16), comment="male | female")
    voice_gender_confidence = Column(Float, comment="Gender classifier confidence")

    # Lyrics
    lrclib_id = Column(BigInteger)
    plain_lyrics = Column(Text)
    synced_lyrics = Column(Text)
    instrumental = Column(Boolean, default=False)
    has_lyrics = Column(Boolean, default=False, index=True)
    lyrics_cleaned = Column(Text)

    # Processed features (from process_data.py)
    color_hue = Column(Float)
    color_saturation = Column(Float)
    color_lightness = Column(Float)
    color_hex = Column(String(8))

    sentiment_compound = Column(Float)
    sentiment_positive = Column(Float)
    sentiment_neutral = Column(Float)
    sentiment_negative = Column(Float)
    sentiment_category = Column(String(16))

    mood_score = Column(Float)
    mood_quadrant = Column(String(32))
    mood_id = Column(Integer, ForeignKey("moods.mood_id"))
    dance_score = Column(Float)
    acoustic_score = Column(Float)
    combined_positivity = Column(Float)
    energy_level = Column(String(16))
    tempo_category = Column(String(16))

    # Media availability
    has_mp3 = Column(Boolean, default=False)
    mp3_filename = Column(String(512))
    mp3_path = Column(Text)
    mp3_source = Column(String(32), comment="youtube_music | youtube_lyrics | youtube_mv | youtube_general")
    mp3_duration_s = Column(Integer)
    mp3_quality = Column(String(16), comment="clean | has_extra | low")
    youtube_music_id = Column(String(32))
    youtube_id = Column(String(32))

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
        Index("ix_song_mood", "mood_quadrant"),
        Index("ix_song_color", "color_hex"),
        Index("ix_song_valence_energy", "valence", "energy"),
        Index("ix_song_track_name_trgm", "track_name",
              postgresql_using="gin",
              postgresql_ops={"track_name": "gin_trgm_ops"}),
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


class ArtistGenre(Base):
    """Artist ↔ Genre."""
    __tablename__ = "artist_genres"

    id = Column(Integer, primary_key=True, autoincrement=True)
    artist_id = Column(String(64), ForeignKey("artists.artist_id"), nullable=False, index=True)
    genre_id = Column(Integer, ForeignKey("genres.genre_id"), nullable=False, index=True)

    artist = relationship("Artist")
    genre = relationship("Genre", back_populates="artists")

    __table_args__ = (
        UniqueConstraint("artist_id", "genre_id", name="uq_artist_genre"),
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


# ============================================================================
# ANALYTICS TABLES
# ============================================================================

class Recommendation(Base):
    """A recommendation was generated (for backtest analysis)."""
    __tablename__ = "recommendations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    track_id = Column(String(64), ForeignKey("songs.track_id"), nullable=False, index=True)
    rec_type = Column(String(32), nullable=False, comment="color, mood, lyrics, image, context, dna, radio")
    similarity_score = Column(Float)
    rank_position = Column(SmallInteger)
    query_params = Column(JSON, comment="Input params that generated this rec")
    was_played = Column(Boolean, default=False)
    was_liked = Column(Boolean, default=False)
    recommended_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    song = relationship("Song")


class SearchLog(Base):
    """Search query log for analytics."""
    __tablename__ = "search_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    query = Column(String(512), nullable=False)
    result_count = Column(Integer, comment="Number of results returned")
    searched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


# ============================================================================
# BACKWARD COMPATIBILITY ALIASES
# ============================================================================

DimArtist = Artist
DimAlbum = Album
DimGenre = Genre
DimMood = Mood
DimSong = Song
FactRecommendation = Recommendation
FactSearch = SearchLog
BridgeSongArtist = SongArtist
BridgeArtistGenre = ArtistGenre
