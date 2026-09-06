def test_summary_names_the_gap_count(render_summary):
    summary = render_summary()
    assert "of 3 gaps" in summary
