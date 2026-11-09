import json
from pathlib import Path

from scripts.generate_synthetic_pdfs import FOOTER, generate


def test_generator_covers_required_cases_deterministically(tmp_path: Path) -> None:
    manifest = generate(tmp_path / "a")
    pdfs = sorted((tmp_path / "a").glob("*.pdf"))

    assert 10 <= len(pdfs) <= 15
    assert len(manifest) == len(pdfs)
    for pdf in pdfs:
        assert pdf.read_bytes().startswith(b"%PDF-")

    tags = {tag for entry in manifest for tag in entry["tags"]}  # type: ignore[union-attr]
    assert {"renamed_test", "ambiguous_date", "prompt_injection", "multi_page"} <= tags
    mmol_reports = [e for e in manifest if "unit:mmol/L" in e["tags"]]  # type: ignore[operator]
    assert len(mmol_reports) >= 2
    assert {e["patient"] for e in manifest} == {"asha", "ravi"}  # two patients for isolation tests
    assert json.loads((tmp_path / "a" / "manifest.json").read_text()) == manifest

    generate(tmp_path / "b")
    for pdf in pdfs:  # byte-for-byte reproducible (needed for future hash-dedup tests)
        assert pdf.read_bytes() == (tmp_path / "b" / pdf.name).read_bytes()
    assert "SYNTHETIC" in FOOTER
