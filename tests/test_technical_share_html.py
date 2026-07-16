from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "docs" / "personal-model-technical-share.html"


def _html() -> str:
    return HTML.read_text(encoding="utf-8")


def test_technical_share_html_is_self_contained() -> None:
    text = _html()

    assert text.startswith("<!doctype html>")
    assert '<html lang="zh-CN">' in text
    assert "<style>" in text
    assert "<script>" in text
    assert 'src="http' not in text
    assert 'href="http' not in text
    assert "https://" not in text


def test_technical_share_html_contains_narrative_spine() -> None:
    text = _html()

    for phrase in (
        "Personal Memory 是什么、为什么需要它",
        "Memory Formation",
        "Memory Recall",
        "走一个实例",
        "小张",
        "小李",
        "项目 A",
        "整条技术主线只做三件事",
    ):
        assert phrase in text


def test_technical_share_html_has_stable_sections() -> None:
    text = _html()

    for section_id in (
        "opening",
        "flow",
        "example",
        "collection",
        "state",
        "formation",
        "recall",
        "delivery",
        "evaluation",
        "outlook",
    ):
        assert f'id="{section_id}"' in text


def test_technical_share_html_embeds_interactive_memory_flow() -> None:
    text = _html()

    assert 'data-lane="formation"' in text
    assert 'data-lane="recall"' in text
    assert "stageDetails" in text
    assert "selectStage" in text
    assert "scrollIntoView" in text
    for stage in (
        "collect",
        "filter",
        "normalize",
        "state",
        "delta",
        "sediment",
        "present",
        "heads",
        "fuse",
        "chains",
        "deliver",
    ):
        assert f'data-stage="{stage}"' in text


def test_technical_share_html_has_presentation_and_print_contracts() -> None:
    text = _html()

    assert 'class="toc"' in text
    assert "IntersectionObserver" in text
    assert "@media (max-width:" in text
    assert "@media print" in text
    assert "<details" in text
    assert "事实引用 1" in text
    assert "事实引用 2" in text
    assert "事实引用 3" in text
