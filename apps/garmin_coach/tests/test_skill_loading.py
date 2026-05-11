"""Tests for ADK filesystem skill loading contract."""

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "garmin_coach" / "src"))
sys.path.insert(1, str(REPO_ROOT / "src"))

from coach_adk.agent import REQUIRED_SKILL_DIRS, _load_skills_or_fail  # noqa: E402


def test_required_skills_load_successfully() -> None:
    skills_dir = REPO_ROOT / "apps" / "garmin_coach" / "skills"
    skills = _load_skills_or_fail(skills_dir)
    loaded_names = [skill.name for skill in skills]
    assert loaded_names == REQUIRED_SKILL_DIRS
