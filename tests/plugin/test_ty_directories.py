import asyncio
import tomllib
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def ty_directory_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('section', 'key'),
        [
            pytest.param('environment', 'root', id='environment-root'),
            pytest.param('src', 'include', id='src-include'),
        ],
    )


@pytest.fixture
def ty_config(pytestconfig: pytest.Config) -> dict[str, dict[str, list[str]]]:
    with pytestconfig.rootpath.joinpath('ty.toml').open('rb') as fd:
        return tomllib.load(fd)


async def list_tracked_files(root: Path, directory: str) -> list[str]:
    process = await asyncio.create_subprocess_exec(
        'git',
        'ls-files',
        '--',
        directory,
        cwd=root,
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    return stdout.decode().splitlines()


def tracked_files(root: Path, directory: str) -> list[str]:
    return asyncio.run(list_tracked_files(root, directory))


@pytest.mark.integration
@ty_directory_cases()
def test_ty_directories_have_tracked_files(
    pytestconfig: pytest.Config,
    ty_config: dict[str, dict[str, list[str]]],
    section: str,
    key: str,
) -> None:
    for directory in ty_config[section][key]:
        assert tracked_files(pytestconfig.rootpath, directory), (
            f'ty.toml [{section}].{key} names {directory!r}, which has no file tracked '
            'by git; an empty directory is missing from a fresh clone and breaks ty check'
        )
