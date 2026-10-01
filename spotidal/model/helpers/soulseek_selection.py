"""Pure selection logic for Soulseek candidates.

Normalization, hard filters, scoring, and tie-breaking live here with no
network or filesystem I/O, so they can be unit tested without a running
`slskd` instance. `soulseek_downloader.py` (orchestration) and
`slskd_client.py` (the API adapter) are the only callers.
"""

import re
import unicodedata
from dataclasses import dataclass, field


def _norm(text):
    text = re.sub(r"[^\w]+", " ", text or "")
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


@dataclass
class TrackRequest:
    artist: str
    title: str
    album: str = None
    year: int = None
    duration_seconds: int = None


@dataclass
class Candidate:
    username: str
    remote_path: str
    filename: str
    extension: str
    size_bytes: int = None
    bitrate: int = None
    duration_seconds: int = None
    availability: bool = None
    speed_estimate: float = None
    # Parsed out of filename/path by the caller before evaluation.
    artist_guess: str = None
    title_guess: str = None
    album_guess: str = None
    year_guess: int = None


@dataclass
class SelectionConfig:
    allowed_formats: tuple = ("flac", "mp3")
    preferred_format_order: tuple = ("flac", "mp3")
    minimum_mp3_bitrate: int = 320
    min_size_mb: float = 1
    max_size_mb: float = 150
    duration_tolerance_seconds: int = 8
    # "reject" | "allow" | "manual_review" -- see PLAN-SOULSEEK.md section 6.
    unknown_metadata_policy: str = "manual_review"
    minimum_score: float = 70


@dataclass
class Evaluation:
    candidate: Candidate
    score: float
    score_breakdown: dict
    rejected: bool
    rejection_reasons: list = field(default_factory=list)
    needs_review: bool = False


# Starting-default weights from PLAN-SOULSEEK.md section 6; configurable
# later, not a universal quality metric.
WEIGHTS = {
    "artist_title": 30,
    "format": 25,
    "quality": 20,
    "album_year": 10,
    "availability": 10,
    "speed": 5,
}


def _unknown_metadata_reasons(config, field_name):
    # "allow" and "manual_review" both pass the hard filter here; the
    # difference between them is handled by _needs_review, not rejection.
    if config.unknown_metadata_policy == "reject":
        return [f"missing {field_name} (unknown metadata rejected by policy)"]
    return []


def hard_filters(candidate, request, config):
    """Return rejection reasons for `candidate`; an empty list means it passes."""
    reasons = []
    extension = (candidate.extension or "").lower().lstrip(".")
    if extension not in config.allowed_formats:
        reasons.append(f"unsupported format: {extension or 'unknown'}")

    if extension == "mp3":
        if candidate.bitrate is None:
            reasons.extend(_unknown_metadata_reasons(config, "bitrate"))
        elif candidate.bitrate < config.minimum_mp3_bitrate:
            reasons.append(
                f"bitrate {candidate.bitrate} below minimum {config.minimum_mp3_bitrate}"
            )

    if candidate.size_bytes is None:
        reasons.extend(_unknown_metadata_reasons(config, "size"))
    else:
        size_mb = candidate.size_bytes / (1024 * 1024)
        if not (config.min_size_mb <= size_mb <= config.max_size_mb):
            reasons.append(
                f"size {size_mb:.1f}MB outside [{config.min_size_mb}, {config.max_size_mb}]MB"
            )

    if request.duration_seconds is not None:
        if candidate.duration_seconds is None:
            reasons.extend(_unknown_metadata_reasons(config, "duration"))
        elif abs(candidate.duration_seconds - request.duration_seconds) > config.duration_tolerance_seconds:
            reasons.append(
                f"duration {candidate.duration_seconds}s outside "
                f"{request.duration_seconds}s +/-{config.duration_tolerance_seconds}s"
            )

    return reasons


def _needs_review(candidate, config):
    if config.unknown_metadata_policy != "manual_review":
        return False
    extension = (candidate.extension or "").lower().lstrip(".")
    # Bitrate is only a meaningful "unknown" for lossy formats -- FLAC is
    # lossless regardless of whether slskd reported a bitrate for it.
    bitrate_missing = extension == "mp3" and candidate.bitrate is None
    return (
        bitrate_missing
        or candidate.duration_seconds is None
        or candidate.size_bytes is None
    )


def score_candidate(candidate, request, config):
    """Return (total_score, breakdown) for a candidate that already passed hard filters."""
    breakdown = {}
    extension = (candidate.extension or "").lower().lstrip(".")

    artist_title_score = 0
    if candidate.title_guess:
        title_match = _norm(candidate.title_guess) == _norm(request.title)
        artist_match = bool(candidate.artist_guess) and _norm(candidate.artist_guess) == _norm(request.artist)
        if title_match and artist_match:
            artist_title_score = WEIGHTS["artist_title"]
        elif title_match:
            # Title alone matching is a real but weaker signal than both --
            # Soulseek usernames/paths rarely carry a reliable artist field.
            artist_title_score = WEIGHTS["artist_title"] * 0.6
    breakdown["artist_title"] = round(artist_title_score, 1)

    format_score = 0
    if extension in config.preferred_format_order:
        rank = config.preferred_format_order.index(extension)
        format_score = WEIGHTS["format"] * (1 - rank / len(config.preferred_format_order))
    breakdown["format"] = round(format_score, 1)

    quality_score = 0
    if extension == "flac":
        # Lossless regardless of whether slskd reported a bitrate for it.
        quality_score = WEIGHTS["quality"]
    elif extension == "mp3" and candidate.bitrate:
        quality_score = WEIGHTS["quality"] * min(candidate.bitrate / 320, 1)
    breakdown["quality"] = round(quality_score, 1)

    album_year_score = 0
    if request.album and candidate.album_guess and _norm(candidate.album_guess) == _norm(request.album):
        album_year_score += WEIGHTS["album_year"] * 0.6
    if request.year and candidate.year_guess and candidate.year_guess == request.year:
        album_year_score += WEIGHTS["album_year"] * 0.4
    breakdown["album_year"] = round(album_year_score, 1)

    breakdown["availability"] = WEIGHTS["availability"] if candidate.availability else 0

    speed_score = 0
    if candidate.speed_estimate:
        # Normalized against a generous 1 MB/s reference; slskd's own speed
        # units/scale need confirming against a live instance (see M0).
        speed_score = min(WEIGHTS["speed"], WEIGHTS["speed"] * candidate.speed_estimate / 1_000_000)
    breakdown["speed"] = round(speed_score, 1)

    return round(sum(breakdown.values()), 1), breakdown


def _tie_break_key(evaluation):
    candidate = evaluation.candidate
    exact_match = evaluation.score_breakdown.get("artist_title", 0) >= WEIGHTS["artist_title"]
    preferred_format = evaluation.score_breakdown.get("format", 0) > 0
    return (
        -evaluation.score,
        not exact_match,
        not preferred_format,
        candidate.duration_seconds is None,
        not bool(candidate.availability),
        candidate.filename.casefold(),
    )


def evaluate(candidates, request, config):
    """Evaluate candidates against `request`/`config`.

    Returns every candidate as an Evaluation, accepted ones first (ranked
    best-first by score then deterministic tie-breakers), rejected ones
    last -- so callers can show "why rejected" without a second pass.
    """
    evaluations = []
    for candidate in candidates:
        reasons = hard_filters(candidate, request, config)
        rejected = bool(reasons)
        if rejected:
            score, breakdown = 0, {}
        else:
            score, breakdown = score_candidate(candidate, request, config)
        evaluations.append(Evaluation(
            candidate=candidate,
            score=score,
            score_breakdown=breakdown,
            rejected=rejected,
            rejection_reasons=reasons,
            needs_review=(not rejected) and _needs_review(candidate, config),
        ))
    accepted = sorted((e for e in evaluations if not e.rejected), key=_tie_break_key)
    rejected = [e for e in evaluations if e.rejected]
    return accepted + rejected


def select_automatic(evaluations, config):
    """Return the top evaluation if it clears the automatic threshold, else None.

    Only ever considers the single best-ranked candidate -- falling back to
    the next one on a later transfer failure is a separate, explicit retry
    step (see PLAN-SOULSEEK.md section 17), not silent substitution here.
    """
    accepted = [e for e in evaluations if not e.rejected]
    if not accepted:
        return None
    best = accepted[0]
    if best.needs_review:
        return None
    if best.score >= config.minimum_score:
        return best
    return None
