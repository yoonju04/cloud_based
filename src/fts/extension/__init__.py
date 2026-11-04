"""Optional review-priority extension. It cannot change a safety verdict."""

from fts.extension.prioritizer import annotate, score_candidate, suggest_followups

__all__ = ["annotate", "score_candidate", "suggest_followups"]
