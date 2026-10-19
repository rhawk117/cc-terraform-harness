from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.policies.containment import PathContainmentPolicy, resolve_project_path
from tf_harness_mcp.policies.errors import PathOutsideRootError

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

pytestmark = pytest.mark.unit


@dataclass(slots=True, kw_only=True, frozen=True)
class Layout:
    root: Path
    outside: Path


@dataclass(slots=True, kw_only=True, frozen=True)
class PathCase:
    name: str
    path: str
    issue_type: type[object]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def refused_path_cases() -> pytest.MarkDecorator:
    cases = [
        PathCase(name='parent-traversal', path='../outside/x', issue_type=PathOutsideRootError),
        PathCase(name='nested-traversal', path='a/../../x', issue_type=PathOutsideRootError),
        PathCase(name='absolute-outside', path='/etc/passwd', issue_type=PathOutsideRootError),
        PathCase(name='escaping-symlink', path='link-out/x', issue_type=PathOutsideRootError),
        PathCase(name='escaping-symlink-itself', path='link-out', issue_type=PathOutsideRootError),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


def accepted_path_cases() -> pytest.MarkDecorator:
    cases = [
        PathCase(name='plain', path='inside/x', issue_type=type(None)),
        PathCase(name='inside-symlink', path='link-in/x', issue_type=type(None)),
        PathCase(name='root-itself', path='.', issue_type=type(None)),
        PathCase(name='traversal-staying-inside', path='inside/../inside/x', issue_type=type(None)),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


class TestPathContainmentPolicy:
    @pytest.fixture
    def layout(self, project_root: Path, tmp_path_factory: pytest.TempPathFactory) -> Layout:
        outside = tmp_path_factory.mktemp('outside')
        project_root.joinpath('inside').mkdir()
        project_root.joinpath('link-in').symlink_to(project_root.joinpath('inside'))
        project_root.joinpath('link-out').symlink_to(outside)
        return Layout(root=project_root, outside=outside)

    def find_path_problem(self, layout: Layout, case: PathCase) -> object | None:
        policy = PathContainmentPolicy(root=layout.root, path=Path(case.path))
        return policy.get_path_problem()

    @refused_path_cases()
    def test_path_leaving_the_root_is_refused(self, layout: Layout, case: PathCase) -> None:
        problem = self.find_path_problem(layout, case)

        assert type(problem) is case.issue_type

    @accepted_path_cases()
    def test_path_staying_inside_the_root_is_accepted(self, layout: Layout, case: PathCase) -> None:
        assert self.find_path_problem(layout, case) is None

    def test_absolute_path_inside_the_root_is_accepted(self, layout: Layout) -> None:
        policy = PathContainmentPolicy(root=layout.root, path=layout.root.joinpath('inside'))

        assert policy.get_path_problem() is None

    def test_resolve_returns_the_symlink_target_inside_the_root(self, layout: Layout) -> None:
        resolved = resolve_project_path(layout.root, Path('link-in/x'))

        assert resolved == layout.root.resolve().joinpath('inside', 'x')

    def test_resolve_raises_for_an_escaping_symlink(self, layout: Layout) -> None:
        with pytest.raises(PathOutsideRootError):
            resolve_project_path(layout.root, Path('link-out/x'))

    def test_resolve_returns_an_absolute_path_inside_the_root(self, layout: Layout) -> None:
        inside = layout.root.joinpath('inside', 'x')

        assert resolve_project_path(layout.root, inside) == inside.resolve()

    def test_resolve_raises_for_an_absolute_path_outside_the_root(self, layout: Layout) -> None:
        with pytest.raises(PathOutsideRootError):
            resolve_project_path(layout.root, layout.outside)
