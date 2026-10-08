import unittest

from spotidal.model.helpers.soulseek_selection import (
    Candidate,
    SelectionConfig,
    TrackRequest,
    evaluate,
    hard_filters,
    select_automatic,
)


def make_candidate(**overrides):
    defaults = dict(
        username="user1",
        remote_path="/music/Artist - Title.flac",
        filename="Artist - Title.flac",
        extension="flac",
        size_bytes=30 * 1024 * 1024,
        bitrate=None,
        duration_seconds=200,
        availability=True,
        speed_estimate=500_000,
        artist_guess="Artist",
        title_guess="Title",
    )
    defaults.update(overrides)
    return Candidate(**defaults)


def make_request(**overrides):
    defaults = dict(artist="Artist", title="Title", duration_seconds=200)
    defaults.update(overrides)
    return TrackRequest(**defaults)


class HardFiltersTests(unittest.TestCase):
    def test_disallowed_extension_is_rejected(self):
        config = SelectionConfig()
        candidate = make_candidate(extension="wav")
        reasons = hard_filters(candidate, make_request(), config)
        self.assertTrue(any("unsupported format" in r for r in reasons))

    def test_low_mp3_bitrate_is_rejected(self):
        config = SelectionConfig()
        candidate = make_candidate(extension="mp3", bitrate=192)
        reasons = hard_filters(candidate, make_request(), config)
        self.assertTrue(any("bitrate" in r for r in reasons))

    def test_mp3_bitrate_at_minimum_passes(self):
        config = SelectionConfig()
        candidate = make_candidate(extension="mp3", bitrate=320)
        reasons = hard_filters(candidate, make_request(), config)
        self.assertEqual(reasons, [])

    def test_size_outside_bounds_is_rejected(self):
        config = SelectionConfig(min_size_mb=1, max_size_mb=10)
        candidate = make_candidate(size_bytes=50 * 1024 * 1024)
        reasons = hard_filters(candidate, make_request(), config)
        self.assertTrue(any("size" in r for r in reasons))

    def test_duration_outside_tolerance_is_rejected(self):
        config = SelectionConfig(duration_tolerance_seconds=5)
        candidate = make_candidate(duration_seconds=220)
        reasons = hard_filters(candidate, make_request(duration_seconds=200), config)
        self.assertTrue(any("duration" in r for r in reasons))

    def test_duration_within_tolerance_passes(self):
        config = SelectionConfig(duration_tolerance_seconds=10)
        candidate = make_candidate(duration_seconds=205)
        reasons = hard_filters(candidate, make_request(duration_seconds=200), config)
        self.assertEqual(reasons, [])

    def test_unknown_metadata_default_policy_does_not_reject(self):
        # Default policy is manual_review: missing metadata is not a hard
        # rejection, it's handled via Evaluation.needs_review instead.
        config = SelectionConfig()
        candidate = make_candidate(bitrate=None, extension="mp3")
        reasons = hard_filters(candidate, make_request(), config)
        self.assertEqual(reasons, [])

    def test_unknown_metadata_reject_policy_rejects(self):
        config = SelectionConfig(unknown_metadata_policy="reject")
        candidate = make_candidate(size_bytes=None)
        reasons = hard_filters(candidate, make_request(), config)
        self.assertTrue(any("missing size" in r for r in reasons))


class EvaluateTests(unittest.TestCase):
    def test_accepted_candidates_rank_above_rejected(self):
        config = SelectionConfig()
        good = make_candidate(filename="good.flac")
        bad = make_candidate(filename="bad.wav", extension="wav")
        evaluations = evaluate([bad, good], make_request(), config)
        self.assertFalse(evaluations[0].rejected)
        self.assertTrue(evaluations[1].rejected)

    def test_exact_match_outranks_title_only_match(self):
        config = SelectionConfig()
        exact = make_candidate(filename="exact.flac", artist_guess="Artist", title_guess="Title")
        partial = make_candidate(filename="partial.flac", artist_guess="Someone Else", title_guess="Title")
        evaluations = evaluate([partial, exact], make_request(), config)
        self.assertEqual(evaluations[0].candidate.filename, "exact.flac")
        self.assertGreater(evaluations[0].score, evaluations[1].score)

    def test_preferred_format_outranks_non_preferred(self):
        config = SelectionConfig(preferred_format_order=("flac", "mp3"))
        flac = make_candidate(filename="a.flac", extension="flac", bitrate=None)
        mp3 = make_candidate(filename="b.mp3", extension="mp3", bitrate=320)
        evaluations = evaluate([mp3, flac], make_request(), config)
        self.assertEqual(evaluations[0].candidate.filename, "a.flac")

    def test_tie_break_is_deterministic_and_lexical(self):
        config = SelectionConfig()
        c1 = make_candidate(filename="zz.flac")
        c2 = make_candidate(filename="aa.flac")
        evaluations = evaluate([c1, c2], make_request(), config)
        # Identical scores -> stable lexical tie-break, not insertion order.
        self.assertEqual(evaluations[0].candidate.filename, "aa.flac")

    def test_rejection_reasons_are_exposed(self):
        config = SelectionConfig()
        candidate = make_candidate(extension="wav")
        evaluations = evaluate([candidate], make_request(), config)
        self.assertNotEqual(evaluations[0].rejection_reasons, [])


class SelectAutomaticTests(unittest.TestCase):
    def test_selects_best_candidate_above_threshold(self):
        config = SelectionConfig(minimum_score=10)
        candidate = make_candidate()
        evaluations = evaluate([candidate], make_request(), config)
        selected = select_automatic(evaluations, config)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.candidate, candidate)

    def test_does_not_select_below_threshold(self):
        config = SelectionConfig(minimum_score=1000)
        candidate = make_candidate()
        evaluations = evaluate([candidate], make_request(), config)
        self.assertIsNone(select_automatic(evaluations, config))

    def test_does_not_auto_select_when_review_required(self):
        config = SelectionConfig(minimum_score=0, unknown_metadata_policy="manual_review")
        candidate = make_candidate(bitrate=None, duration_seconds=None, size_bytes=None)
        evaluations = evaluate([candidate], make_request(duration_seconds=None), config)
        self.assertIsNone(select_automatic(evaluations, config))

    def test_returns_none_when_all_candidates_rejected(self):
        config = SelectionConfig()
        candidate = make_candidate(extension="wav")
        evaluations = evaluate([candidate], make_request(), config)
        self.assertIsNone(select_automatic(evaluations, config))


if __name__ == "__main__":
    unittest.main()
