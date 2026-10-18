from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from tf_harness_mcp.structure.services import build_module_graph

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import ParameterSet
    from tf_harness_mcp.structure.domain import ModuleGraph

pytestmark = pytest.mark.unit

EMPTY_MODULE = 'variable "x" {}\n'


def module_call(source: str) -> str:
    return f'module "m" {{\n  source = "{source}"\n}}\n'


@dataclass(slots=True, kw_only=True, frozen=True)
class SourceCase:
    name: str
    source: str
    followed: bool

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def module_source_cases() -> pytest.MarkDecorator:
    cases = [
        SourceCase(name='sibling-directory', source='./net', followed=True),
        SourceCase(name='parent-directory', source='../shared', followed=True),
        SourceCase(name='registry', source='hashicorp/consul/aws', followed=False),
        SourceCase(name='git', source='git::https://example.com/net.git', followed=False),
        SourceCase(name='github', source='github.com/org/net', followed=False),
        SourceCase(name='interpolated', source='./${var.name}', followed=False),
        SourceCase(name='leaves-the-root', source='../../../elsewhere', followed=False),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


class TestModuleGraph:
    @pytest.fixture
    def caller_dir(self, project_root: Path) -> Path:
        caller = project_root.joinpath('envs', 'prod')
        caller.mkdir(parents=True)
        project_root.joinpath('envs', 'net').mkdir()
        project_root.joinpath('envs', 'net', 'main.tf').write_text(EMPTY_MODULE)
        project_root.joinpath('envs', 'shared').mkdir()
        project_root.joinpath('envs', 'shared', 'main.tf').write_text(EMPTY_MODULE)
        return caller

    def build_graph(self, project_root: Path, caller_dir: Path, source: str) -> ModuleGraph:
        caller_dir.joinpath('main.tf').write_text(module_call(source))
        return build_module_graph(project_root)

    @module_source_cases()
    def test_only_literal_local_sources_inside_the_root_are_followed(
        self, project_root: Path, caller_dir: Path, case: SourceCase
    ) -> None:
        graph = self.build_graph(project_root, caller_dir, case.source)
        caller = next(m for m in graph.modules if m.index.directory == caller_dir.resolve())

        assert bool(caller.calls) is case.followed

    def test_followed_source_resolves_to_the_target_directory(
        self, project_root: Path, caller_dir: Path
    ) -> None:
        graph = self.build_graph(project_root, caller_dir, '../net')

        assert graph.called_directories == {project_root.joinpath('envs', 'net').resolve()}

    def test_root_modules_are_directories_no_literal_source_points_at(
        self, project_root: Path, caller_dir: Path
    ) -> None:
        graph = self.build_graph(project_root, caller_dir, '../net')
        expected = {
            caller_dir.resolve(),
            project_root.joinpath('envs', 'shared').resolve(),
        }

        assert set(graph.root_modules) == expected

    def test_dot_directories_are_never_walked(self, project_root: Path, caller_dir: Path) -> None:
        copy = project_root.joinpath('envs', 'prod', '.terraform', 'modules', 'vpc')
        copy.mkdir(parents=True)
        copy.joinpath('main.tf').write_text(EMPTY_MODULE)
        graph = self.build_graph(project_root, caller_dir, '../net')

        assert copy.resolve() not in {m.index.directory for m in graph.modules}
        assert copy.resolve() not in graph.root_modules
