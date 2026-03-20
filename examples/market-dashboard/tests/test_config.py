# tests/test_config.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ROOT, SKILLS_ROOT, SKILL_REGISTRY, SIGNAL_PANEL_SKILLS, DETAIL_ROUTES


def test_skills_root_exists():
    assert SKILLS_ROOT.exists(), f"SKILLS_ROOT not found: {SKILLS_ROOT}"


def test_all_signal_panel_skills_in_registry():
    for skill in SIGNAL_PANEL_SKILLS:
        assert skill in SKILL_REGISTRY, f"{skill} missing from registry"


def test_all_detail_routes_in_registry():
    for route, skill in DETAIL_ROUTES.items():
        assert skill in SKILL_REGISTRY, f"detail/{route} maps to {skill} which is not in registry"


def test_skills_with_scripts_exist():
    """Scripts listed in registry must exist on disk."""
    for name, cfg in SKILL_REGISTRY.items():
        script = cfg.get("script")
        if script is None:
            continue
        path = SKILLS_ROOT / script
        assert path.exists(), f"{name}: script not found at {path}"
