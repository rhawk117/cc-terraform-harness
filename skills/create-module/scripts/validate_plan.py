"""Validate a create-module MODULE-PLAN.md before any chunk is handed to terraform-author.

Usage: validate_plan.py [--require-approved] [PATH]

PATH defaults to MODULE-PLAN.md. The plan opens with flat frontmatter (`key: value`, lists as
`[a, b]`, a trailing `# comment` ignored) holding mode, module, sources, callers, terraform,
status and approved_by, then `## ` sections Inventory, Interface, Moved map, Chunks, Expected plan
and Open questions. Chunks is a table with id, title, owned, outcome and status columns; Moved map
is a table with root, from and to columns; Expected plan has one `- ROOT: N to add, N to change,
N to destroy` line per caller. Prints one `path:line: RULE message` line per finding:

- PV1: no frontmatter, or it is not closed by a `---` line.
- PV2: a frontmatter key is missing.
- PV3: mode is not new, extract, dedupe or refactor; status is not draft, approved, in-progress
  or done; approved_by is not user or prompt; or sources or callers is not a `[...]` list.
- PV4: a required section is missing.
- PV5: a caller has no Expected plan line.
- PV6: in extract or dedupe mode, a caller has no Moved map row.
- PV7: the Chunks table has no rows, or its ids are not C1, C2, ... in order.
- PV8: a chunk owns no files.
- PV9: a chunk outcome is not create-only, no-changes, moves-only or review-required.
- PV10: a chunk status is not pending, in-progress, done or failed.
- PV11: with --require-approved, status is not approved, in-progress or done.

Exit status: 0 when the plan is valid, 1 when something was found, 2 on a usage error or a
missing PATH.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from itertools import chain
from operator import attrgetter
from pathlib import Path

KEYS = ('mode', 'module', 'sources', 'callers', 'terraform', 'status', 'approved_by')
LIST_KEYS = ('sources', 'callers')
ALLOWED = {
    'mode': ('new', 'extract', 'dedupe', 'refactor'),
    'status': ('draft', 'approved', 'in-progress', 'done'),
    'approved_by': ('user', 'prompt'),
}
SECTIONS = ('Inventory', 'Interface', 'Moved map', 'Chunks', 'Expected plan', 'Open questions')
OUTCOMES = ('create-only', 'no-changes', 'moves-only', 'review-required')
CHUNK_STATUSES = ('pending', 'in-progress', 'done', 'failed')
ENTRY = re.compile(r'^(?P<key>[\w-]+):\s*(?P<value>"[^"]*"|\[[^\]]*\]|[^#]*?)\s*(?:#.*)?$')
HEADING = re.compile(r'^##\s+(?P<name>[^(]+?)\s*(?:\(.*\))?\s*$')
PLAN_LINE = re.compile(
    r'^\s*[-*]\s*`?(?P<root>[^`:]+?)`?\s*:\s*\d+ to add, \d+ to change, \d+ to destroy'
)
SEPARATOR = re.compile(r'^[\s|:-]+$')


@dataclass(slots=True, kw_only=True, frozen=True)
class Hit:
    path: Path
    line: int
    rule: str
    message: str

    def describe(self) -> str:
        return f'{self.path}:{self.line}: {self.rule} {self.message}'


@dataclass(slots=True, kw_only=True, frozen=True)
class Row:
    line: int
    cells: dict[str, str]

    def get(self, column: str) -> str:
        return self.cells.get(column, '')


def split_cells(text: str) -> list[str]:
    return [cell.strip().strip('`').strip() for cell in text.strip().strip('|').split('|')]


@dataclass(slots=True, kw_only=True, frozen=True)
class Section:
    name: str
    line: int
    lines: tuple[tuple[int, str], ...]

    def rows(self) -> list[Row]:
        table = [(number, text) for number, text in self.lines if text.lstrip().startswith('|')]
        header = [cell.lower() for cell in split_cells(table[0][1])] if table else []
        body = [(number, text) for number, text in table[1:] if not SEPARATOR.match(text)]
        return [
            Row(line=number, cells=dict(zip(header, split_cells(text), strict=False)))
            for number, text in body
        ]

    def plan_roots(self) -> set[str]:
        found = (PLAN_LINE.match(text) for _, text in self.lines)
        return {match['root'].strip() for match in found if match}


def parse_value(raw: str) -> str | tuple[str, ...]:
    if raw.startswith('['):
        items = (item.strip().strip('"\'') for item in raw[1:-1].split(','))
        return tuple(item for item in items if item)

    return raw.strip('"\'')


@dataclass(slots=True, kw_only=True, frozen=True)
class Plan:
    path: Path
    entries: dict[str, tuple[int, str | tuple[str, ...]]]
    closed: bool
    sections: dict[str, Section]

    def text(self, key: str) -> str:
        value = self.entries.get(key, (1, ''))[1]
        return value if isinstance(value, str) else ''

    def items(self, key: str) -> tuple[str, ...]:
        value = self.entries.get(key, (1, ()))[1]
        return value if isinstance(value, tuple) else ()

    def report(self, line: int, rule: str, message: str) -> Hit:
        return Hit(path=self.path, line=line, rule=rule, message=message)

    def line_of(self, key: str) -> int:
        return self.entries.get(key, (1, ''))[0]


def read_entries(lines: list[str]) -> dict[str, tuple[int, str | tuple[str, ...]]]:
    found = ((number, ENTRY.match(text)) for number, text in enumerate(lines, 2))
    return {match['key']: (number, parse_value(match['value'])) for number, match in found if match}


def read_sections(lines: list[str], offset: int) -> dict[str, Section]:
    numbered = list(enumerate(lines, offset))
    starts = [(index, HEADING.match(text)) for index, (_, text) in enumerate(numbered)]
    headings = [(index, match['name'].lower()) for index, match in starts if match]
    ends = [index for index, _ in headings[1:]] + [len(numbered)]
    return {
        name: Section(name=name, line=numbered[index][0], lines=tuple(numbered[index + 1 : end]))
        for (index, name), end in zip(headings, ends, strict=True)
    }


def read_plan(path: Path) -> Plan:
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    opened = bool(lines) and lines[0].strip() == '---'
    close = next((index for index, text in enumerate(lines[1:], 1) if text.strip() == '---'), 0)
    front = lines[1:close] if opened and close else []
    sections = read_sections(lines[close + 1 :], close + 2)
    return Plan(
        path=path, entries=read_entries(front), closed=opened and close > 0, sections=sections
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class PlanChecks:
    plan: Plan
    require_approved: bool

    def check_frontmatter(self) -> list[Hit]:
        if not self.plan.closed:
            return [self.plan.report(1, 'PV1', 'no frontmatter closed by a --- line')]

        missing = [key for key in KEYS if key not in self.plan.entries]
        wrong = [
            key
            for key, allowed in ALLOWED.items()
            if key in self.plan.entries and self.plan.text(key) not in allowed
        ]
        unlisted = [
            key
            for key in LIST_KEYS
            if key in self.plan.entries and isinstance(self.plan.entries[key][1], str)
        ]
        return [
            *(self.plan.report(1, 'PV2', f'frontmatter has no {key}') for key in missing),
            *(
                self.plan.report(
                    self.plan.line_of(key), 'PV3', f'{key} must be one of {", ".join(ALLOWED[key])}'
                )
                for key in wrong
            ),
            *(
                self.plan.report(self.plan.line_of(key), 'PV3', f'{key} must be a [..] list')
                for key in unlisted
            ),
        ]

    def check_approval(self) -> list[Hit]:
        approved = self.plan.text('status') in {'approved', 'in-progress', 'done'}
        if not self.require_approved or approved:
            return []

        return [self.plan.report(self.plan.line_of('status'), 'PV11', 'plan is not approved')]

    def check_sections(self) -> list[Hit]:
        missing = [name for name in SECTIONS if name.lower() not in self.plan.sections]
        return [self.plan.report(1, 'PV4', f'no ## {name} section') for name in missing]

    def check_callers(self) -> list[Hit]:
        callers = self.plan.items('callers')
        plan = self.plan.sections.get('expected plan')
        moved = self.plan.sections.get('moved map')
        unplanned = [caller for caller in callers if plan and caller not in plan.plan_roots()]
        needs_moves = moved is not None and self.plan.text('mode') in {'extract', 'dedupe'}
        roots = {row.get('root') for row in moved.rows()} if moved else set()
        unmoved = [caller for caller in callers if needs_moves and caller not in roots]
        return [
            *(
                self.plan.report(
                    plan.line if plan else 1, 'PV5', f'no expected plan line for {caller}'
                )
                for caller in unplanned
            ),
            *(
                self.plan.report(
                    moved.line if moved else 1, 'PV6', f'no moved map row for {caller}'
                )
                for caller in unmoved
            ),
        ]

    def check_chunk(self, index: int, row: Row) -> list[Hit]:
        problems = [
            ('PV7', row.get('id') != f'C{index}', f'chunk id {row.get("id")!r} should be C{index}'),
            ('PV8', row.get('owned') in {'', '-'}, f'chunk {row.get("id")} owns no files'),
            (
                'PV9',
                row.get('outcome') not in OUTCOMES,
                f'chunk {row.get("id")} outcome must be one of {", ".join(OUTCOMES)}',
            ),
            (
                'PV10',
                row.get('status') not in CHUNK_STATUSES,
                f'chunk {row.get("id")} status must be one of {", ".join(CHUNK_STATUSES)}',
            ),
        ]
        return [
            self.plan.report(row.line, rule, message) for rule, found, message in problems if found
        ]

    def check_chunks(self) -> list[Hit]:
        if (section := self.plan.sections.get('chunks')) is None:
            return []

        if not (rows := section.rows()):
            return [self.plan.report(section.line, 'PV7', 'the Chunks table has no rows')]

        return list(
            chain.from_iterable(self.check_chunk(index, row) for index, row in enumerate(rows, 1))
        )

    def check(self) -> list[Hit]:
        checks = (
            self.check_frontmatter,
            self.check_approval,
            self.check_sections,
            self.check_callers,
            self.check_chunks,
        )
        return list(chain.from_iterable(check() for check in checks))


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--require-approved', action='store_true')
    parser.add_argument(
        'path', nargs='?', type=Path, default=Path('MODULE-PLAN.md'), metavar='PATH'
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    if not args.path.is_file():
        print(f'validate_plan: no such file: {args.path}', file=sys.stderr)
        return 2

    checks = PlanChecks(plan=read_plan(args.path), require_approved=args.require_approved)
    hits = sorted(checks.check(), key=attrgetter('line', 'rule'))
    for hit in hits:
        print(hit.describe())

    return 1 if hits else 0


if __name__ == '__main__':
    raise SystemExit(main())
