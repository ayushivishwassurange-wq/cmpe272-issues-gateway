from app.main import get_next_page_number, parse_link_header


def test_parse_link_header_extracts_rel_links():
    header = '<https://api.github.com/repos/test/repo/issues?page=2>; rel="next", <https://api.github.com/repos/test/repo/issues?page=1>; rel="prev"'

    links = parse_link_header(header)

    assert links["next"] == "https://api.github.com/repos/test/repo/issues?page=2"
    assert links["prev"] == "https://api.github.com/repos/test/repo/issues?page=1"


def test_get_next_page_number_reads_rel_next():
    header = '<https://api.github.com/repos/test/repo/issues?page=2>; rel="next"'

    assert get_next_page_number(header) == 2
    assert get_next_page_number(None) is None
