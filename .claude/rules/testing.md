---
paths:
  - '**/tests/**/*.py'
  - '**/test_*.py'
  - '**/conftest.py'
---

# Python tests

These rules add to the Python rules, which still apply in full.

## Shape

- Test behavior, not the current code. Arrangement lives in fixtures, never in the test body, so the code under test can change without rewriting the test.
- A fixture lives in the narrowest scope that uses it: inside the test class when only that class needs it, at module level when several classes in one file do, in the nearest `conftest.py` beyond that.
- A value that a fixture or a single test reads sits as an immutable class attribute; the situation computed from it (collaborators, a harness) is a fixture. Parametrize cases live in cases functions (see Scenarios).
- Bundle collaborators into a frozen dataclass fixture. Use `@pytest.mark.usefixtures` for fixtures the body never references.
- Fake repositories over mocks. `monkeypatch` is a last resort for process state the code reads directly; inject the value instead, since `monkeypatch.chdir()` means the code should take a root path.
- No side effects, no races, no inline imports of the code under test.
- Test support modules (fakes, strategies, fixture plugins) live in `src/<package>/<concept>/tests`, load through conftest plugins and stay out of the wheel. Tests live in top-level `tests/`.

## Helpers

- A repeated act-and-assert becomes a helper method on the class, named for the outcome it proves, so each test body reads as one scenario and one expectation.
- A helper takes the scenario and the harness as arguments; building collaborators stays in fixtures or in a module-level factory the fixtures share.
- A helper that only acts is named for what it returns and leaves the assert to the test (`find_storage_issue` below).

```python
@dataclass(slots=True, kw_only=True, frozen=True)
class UploadHarness:
    storage: MemoryUploadStorage
    service: UploadService


def create_harness(storage: MemoryUploadStorage) -> UploadHarness:
    return UploadHarness(storage=storage, service=UploadService(storage=storage))


def invalid_upload_cases() -> pytest.MarkDecorator:
    empty = Upload(filename='blank.png', size=0)
    oversized = Upload(filename='scan.png', size=20_000_000)
    return pytest.mark.parametrize(
        'upload',
        [pytest.param(empty, id='empty'), pytest.param(oversized, id='oversized')],
    )


class TestStoreUpload:
    photo = Upload(filename='photo.png', size=2_048)

    @pytest.fixture
    def harness(self) -> UploadHarness:
        return create_harness(MemoryUploadStorage())

    @pytest.fixture
    def stocked_harness(self) -> UploadHarness:
        stocked = MemoryUploadStorage(uploads={self.photo.filename: self.photo})
        return create_harness(stocked)

    def assert_rejected_without_change(self, harness: UploadHarness, upload: Upload) -> None:
        stored_before = len(harness.storage)
        with pytest.raises(VaultError):
            harness.service.store(upload)
        assert len(harness.storage) == stored_before

    @invalid_upload_cases()
    def test_invalid_upload_is_rejected(self, harness: UploadHarness, upload: Upload) -> None:
        self.assert_rejected_without_change(harness, upload)

    def test_duplicate_upload_is_rejected(self, stocked_harness: UploadHarness) -> None:
        self.assert_rejected_without_change(stocked_harness, self.photo)
```

## Scenarios

- Test classes never inherit from each other. To run the same tests over several inputs or implementations, parametrize over scenarios.
- Every parametrize set lives in a module-level `<subject>_<kind>_cases()` function that builds its cases and returns the `pytest.mark.parametrize` decorator. When the cases derive from options the class holds, the function takes them as an argument (`@upload_policy_size_boundary_cases(options)`), so the coupling is visible.
- A case with more than one value is a Scenario class: a frozen dataclass with a `name`, the case's inputs and expected outcome, a `marks` tuple, and a `param` property returning `pytest.param(self, id=self.name, marks=self.marks)`. A single-value case stays a plain `pytest.param`.
- Annotate `param` as `ParameterSet`, imported from `_pytest.mark` under `TYPE_CHECKING`; pytest exposes no public name for it.
- A scenario that touches a real backend (filesystem, database, network) sets `marks=(pytest.mark.integration,)`, so one suite covers both kinds and `-m 'not integration'` is the unit run.

```python
@dataclass(slots=True, kw_only=True, frozen=True)
class SizeBoundary:
    name: str
    upload: Upload
    issue_type: type[object]
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)


def upload_policy_size_boundary_cases(options: UploadOptions) -> pytest.MarkDecorator:
    empty = SizeBoundary(
        name='empty',
        upload=Upload(filename='blank.png', size=0),
        issue_type=EmptyUploadError,
    )
    at_limit = SizeBoundary(
        name='at-limit',
        upload=Upload(filename='scan.png', size=options.max_bytes),
        issue_type=NoneType,
    )
    one_over_limit = SizeBoundary(
        name='one-over-limit',
        upload=Upload(filename='scan.png', size=options.max_bytes + 1),
        issue_type=UploadTooLargeError,
    )
    return pytest.mark.parametrize('boundary', [empty.param, at_limit.param, one_over_limit.param])
```

## Hypothesis or pytest.param

- `@given` when the claim holds for every value of a kind: state it as a property over a strategy. Strategies sit as class attributes beside the test, built from the domain types with `st.builds`.
- Cases functions for named boundaries a reader should see by name (`empty`, `at-limit`, `one-over-limit`), never for sampling an input space by hand.
- A regression is pinned with `@example(...)` on the property test that covers it, and that test is marked `@pytest.mark.regression`. When no property covers it yet, write the property first.
- `@given` tests take no function-scoped fixtures: Hypothesis reuses them across examples and fails its `function_scoped_fixture` health check. Build per-example state in a helper method instead.

```python
class TestUploadPolicy:
    options = UploadOptions(max_bytes=100)
    allowed_uploads = st.builds(
        Upload,
        filename=st.sampled_from(('photo.png', 'scan.jpg')),
        size=st.integers(min_value=1, max_value=100),
    )
    oversized_uploads = st.builds(
        Upload,
        filename=st.just('scan.png'),
        size=st.integers(min_value=101),
    )

    def find_storage_issue(self, upload: Upload) -> VaultError | None:
        return UploadPolicy(upload=upload, options=self.options).get_storage_issues()

    @pytest.mark.regression
    @given(upload=allowed_uploads)
    @example(upload=Upload(filename='scan.PNG', size=50))
    def test_allowed_upload_has_no_issue(self, upload: Upload) -> None:
        assert not self.find_storage_issue(upload)

    @given(upload=oversized_uploads)
    def test_upload_over_the_limit_is_too_large(self, upload: Upload) -> None:
        assert isinstance(self.find_storage_issue(upload), UploadTooLargeError)

    @upload_policy_size_boundary_cases(options)
    def test_size_boundary(self, boundary: SizeBoundary) -> None:
        assert type(self.find_storage_issue(boundary.upload)) is boundary.issue_type
```

## Markers

- Custom markers are registered and unknown ones fail collection:

```toml
[tool.pytest]
strict_markers = true
markers = [
    'regression: pins a case that once broke',
    'integration: touches a real backend',
]
```

## Functions

- A module-level test function is right only for a pure function tested through its parameters or `@given` alone: no fixtures, no scenarios, no helpers.
- Once a test needs any of those, it moves into a class, as `TestStoreUpload` above does.

```python
@given(upload=st.builds(Upload))
def test_description_starts_with_the_filename(upload: Upload) -> None:
    assert describe_upload(upload).startswith(upload.filename)
```
