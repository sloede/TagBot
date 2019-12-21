import os.path
import textwrap

from datetime import datetime, timedelta
from unittest.mock import Mock, call

import yaml

from github.Issue import Issue
from github.PullRequest import PullRequest

from tagbot.repo import Repo


def _changelog(*, name="", registry="", token="", template=""):
    r = Repo(name, registry, token, template)
    return r._changelog


def test_previous_release():
    c = _changelog()
    mocks = []
    c._repo._repo.get_releases = lambda: mocks
    for t in ["ignore", "v1.2.4-ignore", "v1.2.3", "v1.2.2", "v1.0.2", "v1.0.10"]:
        mocks.append(Mock(tag_name=t))
    assert c._previous_release("v1.0.0") is None
    assert c._previous_release("v1.0.2") is None
    assert c._previous_release("v1.2.5").tag_name == "v1.2.3"
    assert c._previous_release("v1.0.3").tag_name == "v1.0.2"


def test_version_end():
    c = _changelog()
    c._repo._git = Mock(return_value="2019-10-05T13:45:17+07:00")
    assert c._version_end("abcdef") == datetime(2019, 10, 5, 6, 45, 17)
    c._repo._git.assert_called_once_with("show", "-s", "--format=%cI", "abcdef")


def test_first_sha():
    c = _changelog()
    c._repo._git = Mock(return_value="abc\ndef\nghi")
    assert c._first_sha() == "ghi"
    c._repo._git.assert_called_once_with("log", "--format=%H")


def test_issues_and_pulls():
    pass


def test_issues_pulls():
    c = _changelog()
    mocks = []
    for i in range(0, 20, 2):
        mocks.append(Mock(spec=Issue, number=i))
        mocks.append(Mock(spec=PullRequest, number=i + 1))
    c._issues_and_pulls = Mock(return_value=mocks)
    assert all(isinstance(x, Issue) and not x.number % 2 for x in c._issues(0, 1))
    c._issues_and_pulls.assert_called_with(0, 1)
    assert all(isinstance(x, PullRequest) and x.number % 2 for x in c._pulls(2, 3))
    c._issues_and_pulls.assert_called_with(2, 3)


def test_registry_pr():
    c = _changelog()
    c._repo._Repo__project = {"name": "PkgName", "uuid": "abcdef0123456789"}
    registry = c._repo._registry = Mock(owner=Mock(login="Owner"))
    now = datetime.now()
    owner_pr = Mock(merged=True, merged_at=now)
    registry.get_pulls.return_value = [owner_pr]
    assert c._registry_pr("v1.2.3") is owner_pr
    registry.get_pulls.assert_called_once_with(
        head="Owner:registrator/pkgname/abcdef01/v1.2.3", state="closed",
    )
    registry.get_pulls.side_effect = [[], [Mock(closed_at=now - timedelta(days=10))]]
    assert c._registry_pr("v2.3.4") is None
    calls = [
        call(head="Owner:registrator/pkgname/abcdef01/v2.3.4", state="closed"),
        call(state="closed"),
    ]
    registry.get_pulls.assert_has_calls(calls)
    good_pr = Mock(
        closed_at=now - timedelta(days=2),
        merged=True,
        head=Mock(ref="registrator/pkgname/abcdef01/v3.4.5"),
    )
    registry.get_pulls.side_effect = [[], [good_pr]]
    assert c._registry_pr("v3.4.5") is good_pr
    calls = [
        call(head="Owner:registrator/pkgname/abcdef01/v3.4.5", state="closed"),
        call(state="closed"),
    ]
    registry.get_pulls.assert_has_calls(calls)


def test_custom_release_notes():
    c = _changelog()
    notes = """
    blah blah blah
    <!-- BEGIN RELEASE NOTES -->
    > Foo
    > Bar
    <!-- END RELEASE NOTES -->
    blah blah blah
    """
    notes = textwrap.dedent(notes)
    c._registry_pr = Mock(side_effect=[None, Mock(body="foo"), Mock(body=notes)])
    assert c._custom_release_notes("v1.2.3") is None
    c._registry_pr.assert_called_with("v1.2.3")
    assert c._custom_release_notes("v2.3.4") is None
    c._registry_pr.assert_called_with("v2.3.4")
    assert c._custom_release_notes("v3.4.5") == "Foo\nBar"
    c._registry_pr.assert_called_with("v3.4.5")


def test_format_user():
    c = _changelog()
    m = Mock(html_url="url", login="username")
    m.name = "Name"
    assert c._format_user(m) == {"name": "Name", "url": "url", "username": "username"}


def test_format_issue_pull():
    c = _changelog()
    m = Mock(
        user=Mock(html_url="url", login="username"),
        closed_by=Mock(html_url="url", login="username"),
        merged_by=Mock(html_url="url", login="username"),
        body="body",
        labels=[Mock(), Mock()],
        number=1,
        title="title",
        html_url="url",
    )
    m.user.name = "User"
    m.closed_by.name = "Closer"
    m.merged_by.name = "Merger"
    m.labels[0].name = "label1"
    m.labels[1].name = "label2"
    assert c._format_issue(m) == {
        "author": {"name": "User", "url": "url", "username": "username"},
        "body": "body",
        "labels": ["label1", "label2"],
        "closer": {"name": "Closer", "url": "url", "username": "username"},
        "number": 1,
        "title": "title",
        "url": "url",
    }
    assert c._format_pull(m) == {
        "author": {"name": "User", "url": "url", "username": "username"},
        "body": "body",
        "labels": ["label1", "label2"],
        "merger": {"name": "Merger", "url": "url", "username": "username"},
        "number": 1,
        "title": "title",
        "url": "url",
    }


def test_collect_data():
    pass


def test_render():
    path = os.path.join(os.path.dirname(__file__), "..", "action.yml")
    with open(path) as f:
        action = yaml.safe_load(f)
    default = action["inputs"]["changelog"]["default"]
    c = _changelog(template=default)
    expected = """
    ## PkgName v1.2.3

    [Diff since v1.2.2](https://github.com/Me/PkgName.jl/compare/v1.2.2...v1.2.3)

    Custom release notes

    **Closed issues:**
    - Issue title (#1)

    **Merged pull requests:**
    - Pull title (#3) (@author)
    """
    data = {
        "compare_url": "https://github.com/Me/PkgName.jl/compare/v1.2.2...v1.2.3",
        "custom": "Custom release notes",
        "issues": [
            {"number": 1, "title": "Issue title", "labels": []},
            {"number": 2, "title": "Other issue title", "labels": ["changelog-skip"]},
        ],
        "package": "PkgName",
        "previous_release": "v1.2.2",
        "pulls": [
            {
                "number": 3,
                "title": "Pull title",
                "labels": [],
                "author": {"username": "author"},
            },
            {
                "number": 4,
                "title": "Other pull title",
                "labels": ["changelog-skip"],
                "author": {"username": "author"},
            },
        ],
        "version": "v1.2.3",
        "version_url": "https://github.com/Me/PkgName.jl/tree/v1.2.3",
    }
    assert c._render(data) == textwrap.dedent(expected).strip()
    del data["pulls"]
    assert "**Merged pull requests:**" not in c._render(data)
    del data["issues"]
    assert "**Closed issues:**" not in c._render(data)


def test_get():
    c = _changelog(template="{{ version }}")
    c._collect_data = Mock(return_value={"version": "v1.2.3"})
    assert c.get("v1.2.3", "abc") == "v1.2.3"
    c._collect_data.assert_called_once_with("v1.2.3", "abc")
