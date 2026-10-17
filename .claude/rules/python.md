---
paths:
  - '**/*.py'
  - '**/*.pyi'
  - '**/pyproject.toml'
---

# Python

Ruff and ty enforce every mechanical rule. This file holds the judgment a linter cannot see.
Apply the reason behind each rule, not its surface shape. Examples show the target shape;
copy the shape, never the names.

## Workflow

- `uv` only: `uv init` to scaffold, `uv add` and `uv remove` for dependencies, `uv run python`. Never bare `python`, `python3` or `pip`, and never hand-edit dependency tables.
- Use the project's ruff and ty config when it has one and never weaken it.
- Before calling work done, run `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` and `uv run pytest`.
- Target the project's `requires-python`, default 3.14. Check current stdlib docs instead of trusting memory.
- When a requirement is missing, ask instead of guessing. When a pattern has no clean equivalent, say so.
- When editing existing code, keep its names and patterns. More code for the same result with no readability gain is never acceptable.
- No em dashes anywhere, including strings and docs.

## Design spine

- Make illegal states unrepresentable: narrow types, `Literal` aliases, enums and frozen values so wrong code fails to typecheck. Spend rigor there, never on micro-optimizations.
- Count semantic units (things that can independently be wrong), not lines. Separate named expressions beat dense one-liners and nested comprehensions.
- Abstract only when it buys a guarantee or a testing seam. Ask what the abstraction costs to change later.
- Procedural OO: frozen public data and policy types define the domain, module-level functions move values through it, dependencies are built at the edge and injected, side effects are pushed outward.
- Push each decision to the layer that holds the information it needs.
- Never hand-roll what the stdlib, an installed package or the codebase's own helpers already own (pathlib, textwrap, contextlib, shutil, Pydantic or msgspec validation). Never override a default without a demonstrated issue.
- File names carry the layer, with the same roles in every concept package: `domain.py`, `schemas.py`, `store.py` or `repository.py`, `services.py` or `use_cases.py`, `policy.py`, `errors.py`, `util.py`. Any of them may grow into a package. No Python file over 300 lines.

## Classes and values

- Pick the type by boundary: internal values are `@dataclass(slots=True, kw_only=True, frozen=True)`; values that cross a wire or are allocated per item on a hot path are `msgspec.Struct` with `frozen=True, kw_only=True`, plus `gc=False` when it can never sit in a reference cycle; untrusted input is validated by Pydantic.
- Three kinds of class:
  - Data: public fields plus a few derived properties.
  - Policy: everything one concept knows about its own validity. Built from the value it checks plus injected options, it exposes derived values and predicates as properties, helpers over that state, and one or more verdict methods (`get_<noun>_problem()` or `get_<noun>_issues()`), each walking several facets with guard clauses and returning the first error or `None`. The call site raises.
  - Orchestration: a frozen dataclass holding injected collaborators (use cases, services, unit of work). It raises directly on what a collaborator reports, such as a record that already exists; conditions computed from the value itself belong to a policy.

```python
class UploadTooLargeError(VaultError):
    def __init__(self, *, filename: str, limit: int) -> None:
        self.filename = filename
        self.limit = limit
        super().__init__(f'{filename} exceeds {limit} bytes')


type UploadStorageIssue = EmptyUploadError | UploadTooLargeError | UnsupportedUploadTypeError


@dataclass(slots=True, kw_only=True, frozen=True)
class Upload:
    filename: str
    size: int

    @property
    def suffix(self) -> str:
        return PurePath(self.filename).suffix.lower()


@dataclass(slots=True, kw_only=True, frozen=True)
class UploadOptions:
    max_bytes: int = 10_000_000
    allowed_suffixes: tuple[str, ...] = ('.png', '.jpg')


@dataclass(slots=True, kw_only=True, frozen=True)
class UploadPolicy:
    upload: Upload
    options: UploadOptions = field(default_factory=UploadOptions)

    @property
    def is_empty(self) -> bool:
        return self.upload.size == 0

    @property
    def is_oversized(self) -> bool:
        return self.upload.size > self.options.max_bytes

    @property
    def has_allowed_type(self) -> bool:
        return self.upload.suffix in self.options.allowed_suffixes

    def get_storage_issues(self) -> UploadStorageIssue | None:
        if self.is_empty:
            return EmptyUploadError(filename=self.upload.filename)

        if self.is_oversized:
            return UploadTooLargeError(
                filename=self.upload.filename,
                limit=self.options.max_bytes,
            )

        if not self.has_allowed_type:
            return UnsupportedUploadTypeError(suffix=self.upload.suffix)

        return None
```

```python
@runtime_checkable
class UploadRepository(Protocol):
    def save(self, upload: Upload) -> StoredUpload: ...

    def get_by_file_name(self, name: str) -> StoredUpload | None: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class UploadService:
    storage: UploadRepository
    options: UploadOptions = field(default_factory=UploadOptions)

    def store(self, upload: Upload) -> StoredUpload:
        if existing := self.storage.get_by_file_name(upload.filename):
            raise UploadAlreadyExistsError(filename=existing.name)

        policy = UploadPolicy(upload=upload, options=self.options)
        if problem := policy.get_storage_issues():
            raise problem

        return self.storage.save(upload)
```

- The factory that builds the real backend lives in its own module at the edge, so the service only knows the Protocol. Unit tests construct the service with a fake; integration tests call the factory with their own root and options.

```python
def create_upload_service(root: Path, options: UploadOptions | None = None) -> UploadService:
    options = options or UploadOptions()
    storage = DirectoryUploadRepository(root=root)
    return UploadService(storage=storage, options=options)
```

- A method belongs on a class only if it reads that instance's fields; otherwise it is a module-level function.
- Named presets of one concrete type are `@classmethod`s. A factory that returns a Protocol is a module-level function, so callers never see the implementing type.
- No hand-written `__init__` except for exception classes (see Errors) and genuinely abstract concepts; abstract concepts always declare `__slots__`.
- No `__post_init__`: validation lives in a policy or a standalone helper testable in isolation. Never `object.__setattr__` on a frozen dataclass.
- No `ClassVar` on dataclasses.
- Inherit only from the application's exception hierarchy, `Protocol`, `StrEnum` or `IntEnum`, and `msgspec.Struct` or `BaseModel` (one project base may set shared config such as `rename='camel'`). Everything else is composition.
- Public by default. Hide through the interface, never through underscores: when a caller could misuse an implementation, a factory hands it a Protocol, so nothing beyond the Protocol reaches the caller while the implementation stays public and testable on its own. Where no interface is needed, a frozen container plus a public function does the job. No underscore-prefixed classes; immutability over underscore-prefixed members.
- Keep Protocols minimal; only resource-owning implementations are context managers. Always `@runtime_checkable`; it catches renamed or missing members at `isinstance`, not changed signatures, which ty catches at `repo: Repository = MemoryRepository()`.
- Behavior handed to another object is a class with a verb method (`handler.handle(job)`) typed by a Protocol, never a `__call__` Protocol, a closure or a lambda. When an API itself takes a callable, pass a bound verb method or a factory function (`map(router.dispatch, names)`, `field(default_factory=create_storage)`).
- Values with different lifetimes live in different objects (per-line state apart from per-document state). Group state by concern, never one god object.
- A behaviorless set of related strings is a `Literal` alias. Use a `StrEnum` with `auto()` only when members carry behavior as properties or `.format()` templates (`@property def slash(self) -> str: return f'/{self}'`), and `IntEnum` when order means something. No enums carrying data.
- Tunables live in a frozen options dataclass with defaults and derived properties, injected via `field(default_factory=...)` or `X | None` falling back to `X()`. When several parameters thread through helpers, collapse them into an options object or a class that holds it.
- Lookup tables are dicts keyed by a `Literal` alias (an enum only when the key carries behavior), owned by a class with a clear lifecycle and filled through an intent method, never at module level. Values share one Protocol with a verb method.

```python
type CommandName = Literal['join', 'leave']


@runtime_checkable
class CommandHandler(Protocol):
    def handle(self, user: str) -> str: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class JoinHandler:
    room: Room

    def handle(self, user: str) -> str:
        return f'{user} joined {self.room.name}'


type CommandHandlers = dict[CommandName, CommandHandler]


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandRouter:
    handlers: CommandHandlers = field(default_factory=dict)

    def dispatch(self, name: CommandName, user: str) -> str:
        return self.handlers[name].handle(user)

    def mount(self, commands: CommandHandlers) -> Self:
        self.handlers.update(commands)
        return self


def create_command_router(room: Room) -> CommandRouter:
    return CommandRouter().mount({
        'join': JoinHandler(room=room),
        'leave': LeaveHandler(room=room),
    })
```

- No module-level mutable reference types, import-time I/O, constructors doing real work, generic setters, or `del` (use `dict.pop`).
- A frozen class may own a mutable container as long as only its own intent methods change it (`mount()` above). Design those methods around the use case so a caller never has a reason to reach for the attribute.
- Operators in runtime code, defined or consumed, must be guessable by a reader who does not know the operand types. `path /= other` makes no sense, so use `Path.joinpath()` instead of `/`. Type expressions such as `X | None` are exempt.

## Resources

- A managed resource has a lifecycle visible at a glance: a context manager owns acquire and release. Compose dynamic sets with `AsyncExitStack` and run concurrent work in `asyncio.TaskGroup`.
- Expose intent methods such as `cancel()` or `terminate()` instead of handing callers the raw resource or signals. Never yield a handle to an internal object a caller could poke.
- Decorators use `functools.wraps`.

## Typing

- Declare long, repeated or constrained types once as PEP 695 `type` aliases, `Annotated[...]` included (`type Port = Annotated[int, Field(gt=0)]`, `type Pair[T] = tuple[T, T]`). Never write `Annotated[...]` inline in a field or parameter.
- Annotate contextmanager functions as `Generator[...]`.
- Project-local msgspec or Pydantic base classes go in ruff's `runtime-evaluated-base-classes`.

## Control flow

- The walrus operator is welcome where it removes a repeated call.
- Pipelines: a class holding the shared options, a method that selects items and a function that maps one item, composed with `map`, `filter` and `operator.attrgetter`. Functions that need no instance state stay at module level.
- Search with `next(<generator>, default)`. A loop that does work runs to completion: no `return` and no `break` inside it.
- Never `while True`. Write the real exit condition, usually with a walrus, or expose an intent control such as `terminate()`.

```python
type UploadChain = Iterable[Upload]


def describe_upload(upload: Upload) -> str:
    return f'{upload.filename}\t{upload.size}'


def get_upload_by_name(uploads: UploadChain, filename: str) -> Upload | None:
    return next((upload for upload in uploads if upload.filename == filename), None)


@dataclass(slots=True, kw_only=True, frozen=True)
class UploadPipeline:
    options: UploadOptions = field(default_factory=UploadOptions)

    def create_policy(self, upload: Upload) -> UploadPolicy:
        return UploadPolicy(options=self.options, upload=upload)

    def select_oversized(self, uploads: UploadChain) -> UploadChain:
        policies = map(self.create_policy, uploads)
        pipeline = filter(attrgetter('is_oversized'), policies)
        return map(attrgetter('upload'), pipeline)

    def describe_oversized(self, uploads: UploadChain) -> list[str]:
        oversized_pipeline = self.select_oversized(uploads)
        oversized_pipeline = map(describe_upload, oversized_pipeline)
        return list(oversized_pipeline)

    def are_all_oversized(self, uploads: UploadChain) -> bool:
        policies = map(self.create_policy, uploads)
        return all(map(attrgetter('is_oversized'), policies))


async def drain(inbox: asyncio.Queue[Job | None], handler: JobHandler) -> None:
    while job := await inbox.get():
        await handler.handle(job)
```

- Avoid `match`; guards or a dict dispatch read better.
- `else` appears only in a standalone one-line ternary, `name = a if cond else b`. Never `else` or `elif` blocks, `for`/`else`, `try`/`else`, or a ternary nested inside a call or f-string. Restructure with guard clauses, early returns, inverted conditions or extraction, and separate consecutive `if` blocks with a blank line.
- Truthy checks by default: `x = x or make_default()` and walrus truthiness. Test `is None` where 0, `''`, an empty container or any object defining `__len__` or `__bool__` (fakes, repositories, collections) is a legitimate value, because an injected empty fake is falsy and would be silently replaced.

## Errors

- One exception class per failure, defined in the application's own exception hierarchy, never on invented category bases such as `NotFoundError`. Its hand-written `__init__` builds the message from typed keyword fields. No `__slots__` on exceptions.
- Raise as close to the cause as possible. Translate with `raise NewError(...) from err`.
- A function that exists solely to raise is always wrong: return the exception instance, or `None` when there is no error, so tests assert on fields and the call site's `raise` makes control flow explicit.
- Make the safe path the only path: anything that must run inside a guard is handed out only by that guard.

```python
def sqlite_connection(path: Path) -> AbstractContextManager[sqlite3.Connection]:
    return closing(sqlite3.connect(path, autocommit=False))


@contextmanager
def open_ledger(path: Path) -> Generator[Ledger]:
    with sqlite_connection(path) as connection:
        try:
            yield Ledger(connection=connection)
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise DuplicateEntryError(path=path) from error

        connection.commit()
```

- `main()` returns an exit code; the module guard does `raise SystemExit(main())`.

## Comments and docstrings

- Zero comments. A module docstring is the only prose allowed in code. If you need a comment to explain the code, the implementation is wrong by design.
- The user marks notes with `::<marker-name>::` delimiters for grepping. Leave them in place and never add your own.
- Docstrings are allowed only when a framework turns them into metadata (FastAPI routes, MCP tools).
- Every lint or type suppression states its reason.
