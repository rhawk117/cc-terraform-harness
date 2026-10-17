"""
Plugin Level & Repository Tests, not for application tests
"""

import functools
import json
from dataclasses import dataclass
from operator import attrgetter
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Self

import pytest
import yaml

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping
    from pathlib import Path


def read_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text('utf-8'))


@functools.lru_cache(maxsize=128)
def read_markdown_frontmatter(
    path: Path,
    *,
    max_bytes: int = 16 * 1_024,
    trim_offset: int = 4,
) -> Mapping[str, Any]:
    with path.open('rb') as fd:
        content = fd.read(max_bytes)

    if not content.startswith(b'---\n'):
        return MappingProxyType({})

    end = content.find(b'\n---\n', 3)
    if end == -1:
        msg = f'Invalid or oversized frontmatter: {path}'
        raise ValueError(msg)

    contents = yaml.safe_load(content[trim_offset:end])
    return MappingProxyType(contents or {})


@dataclass(slots=True, frozen=True)
class PluginManifestFile:
    path: Path
    contents: Mapping[str, Any]

    @classmethod
    def read(cls, path: Path) -> Self:
        return cls(path, read_json_file(path))

    def required_key(self, key: str) -> Any:
        return self.contents[key]


@dataclass(slots=True, frozen=True, kw_only=True)
class SkillInventory:
    skills_root: Path

    @property
    def skill_files(self) -> Iterable[Path]:
        return self.skills_root.rglob('SKILL.md')

    def scan_skill_dirs(self) -> Iterator[Path]:
        yield from (skill_file.parent for skill_file in self.skill_files)

    def defined_skill_names(self) -> set[str]:
        skill_names = map(attrgetter('name'), self.scan_skill_dirs())
        return set(skill_names)

    def given_frontmatters(self) -> dict[str, Mapping[str, Any]]:
        return {skill.parent.name: read_markdown_frontmatter(skill) for skill in self.skill_files}


@dataclass(slots=True, frozen=True, kw_only=True)
class SubagentInventory:
    agents_dir: Path

    @property
    def agent_files(self) -> Iterator[Path]:
        return self.agents_dir.rglob('*.md')

    def agent_names(self) -> set[str]:
        agents = map(attrgetter('stem'), self.agent_files)
        return set(agents)

    def given_frontmatters(self) -> dict[str, Mapping[str, Any]]:
        return {path.stem: read_markdown_frontmatter(path) for path in self.agent_files}


@dataclass(slots=True, frozen=True, kw_only=True)
class PluginInventory:
    manifest: PluginManifestFile
    mcp: PluginManifestFile
    hooks: PluginManifestFile
    skills: SkillInventory
    subagents: SubagentInventory


@pytest.fixture
def claude_plugin(repository_root: Path) -> PluginInventory:
    plugin_paths = {
        'manifest': repository_root.joinpath('.claude-plugin', 'plugin.json'),
        'mcp': repository_root.joinpath('.mcp.json'),
        'hooks': repository_root.joinpath('hooks', 'hooks.json'),
    }
    plugin_files = {key: PluginManifestFile.read(path) for key, path in plugin_paths.items()}

    return PluginInventory(
        **plugin_files,
        skills=SkillInventory(skills_root=repository_root.joinpath('skills')),
        subagents=SubagentInventory(agents_dir=repository_root.joinpath('agents')),
    )
