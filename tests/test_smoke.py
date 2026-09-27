import json

import pytest

from gazemap import cli
from gazemap.saliency.deepgaze import WEIGHT_FILES, default_model_dir

pytestmark = pytest.mark.smoke

needs_weights = pytest.mark.skipif(
    not all((default_model_dir() / name).exists() for name in WEIGHT_FILES),
    reason="DeepGaze IIE weights not downloaded",
)


@needs_weights
def test_top_hotspot_is_the_only_button_on_a_plain_page(fixture_server, tmp_path):
    url = f"{fixture_server}/button.html"
    assert cli.main(["analyze", url, "--viewport", "both", "--out", str(tmp_path), "--no-report"]) == 0
    for viewport in ("desktop", "mobile"):
        record = json.loads((tmp_path / cli.slugify_url(url) / viewport / "hotspots.json").read_text())
        top = record["hotspots"][0]
        assert top["element"]["selector"] == "#cta", (viewport, record["hotspots"])
        assert record["runtime_seconds"]["inference"] > 0


@needs_weights
def test_pdf_run_prints_no_unclosed_object_warning(resume_pdf, tmp_path):
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "gazemap.cli", "analyze", str(resume_pdf), "--out", str(tmp_path), "--no-report"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    assert "still open" not in result.stderr
    assert "JANE EXAMPLE" in result.stdout
