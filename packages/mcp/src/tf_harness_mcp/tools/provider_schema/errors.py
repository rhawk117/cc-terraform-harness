"""Problems the provider_schema tool reports beyond those of the schema cache."""

from tf_harness_mcp.errors import HarnessError


class InvalidBlockPathError(HarnessError):
    def __init__(self, *, block: str) -> None:
        self.block = block
        super().__init__(f'block path is not dot separated block or attribute names: {block!r}')


class BlockPathNotFoundError(HarnessError):
    def __init__(self, *, type_name: str, block: str) -> None:
        self.type_name = type_name
        self.block = block
        super().__init__(f'{type_name} has no nested block or nested attribute at {block!r}')
