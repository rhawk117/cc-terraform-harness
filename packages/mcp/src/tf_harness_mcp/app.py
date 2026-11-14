"""The tf-harness MCP server: its identity, its lifespan and the tools it serves."""

import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import wraps
from importlib.metadata import version
from typing import TYPE_CHECKING, Annotated, Any

from mcp.server.mcpserver import (  # noqa: TC002 - the MCP SDK evaluates the resolver annotations
    Context,
    MCPServer,
    RequestStateSecurity,
    Resolve,
)
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from tf_harness_mcp.errors import HarnessError
from tf_harness_mcp.policies import containment  # noqa: TC001 - the MCP SDK evaluates the tool annotations
from tf_harness_mcp.provider_schemas.domain import SchemaKind  # noqa: TC001 - the MCP SDK evaluates the tool annotations
from tf_harness_mcp.runner.process import create_command_runner
from tf_harness_mcp.settings import load_settings
from tf_harness_mcp.tools.change_impact.services import (
    ChangeImpactTool,
    create_change_impact_tool,
)
from tf_harness_mcp.tools.describe.services import DescribeTool, create_describe_tool
from tf_harness_mcp.tools.diagnostics.services import DiagnosticsTool, create_diagnostics_tool
from tf_harness_mcp.tools.plan_digest.services import PlanDigestTool, create_plan_digest_tool
from tf_harness_mcp.tools.provider_schema.services import (
    ProviderSchemaTool,
    create_provider_schema_tool,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    from tf_harness_mcp.runner.domain import CommandRunner
    from tf_harness_mcp.settings import Settings

SERVER_NAME = 'tf-harness-mcp'
SERVER_TITLE = 'Terraform Harness'
SERVER_DESCRIPTION = (
    'Read-only Terraform tools: module diagnostics, module and file summaries, plan digests, '
    'provider schema lookups and git change impact.'
)
SERVER_WEBSITE = 'https://github.com/rhawk117/cc-terraform-harness'
SERVER_INSTRUCTIONS = """\
Terraform harness tools for the project this server was started on.

- describe: summarize a module directory, a .tf file or a .tfvars file.
- diagnostics: run the terraform fmt check, terraform validate and tflint on one module.
- plan_digest: summarize a plan rendered by `terraform show -json <planfile>`.
- provider_schema: read one level of a provider, resource or data source schema.
- change_impact: report the Terraform blocks a git diff changed and the root modules it reaches.

Every path is relative to the project root or absolute inside it; a path outside the root is
refused. No tool changes the project, state or infrastructure: none runs plan, apply, init or
import. provider_schema writes only its provider schema cache, outside the project.
Results larger than the server's output budget are cut down or refused with an error.
"""
REQUEST_STATE_TTL_SECONDS = 300.0


@dataclass(slots=True, kw_only=True, frozen=True)
class AppServices:
    diagnostics: DiagnosticsTool
    plan_digest: PlanDigestTool
    describe: DescribeTool
    provider_schema: ProviderSchemaTool
    change_impact: ChangeImpactTool


def create_services(settings: Settings, runner: CommandRunner) -> AppServices:
    return AppServices(
        diagnostics=create_diagnostics_tool(runner, settings),
        plan_digest=create_plan_digest_tool(settings),
        describe=create_describe_tool(settings),
        provider_schema=create_provider_schema_tool(runner, settings),
        change_impact=create_change_impact_tool(runner, settings),
    )


def load_services() -> AppServices:
    settings = load_settings(sys.argv[1:], os.environ)
    return create_services(settings, create_command_runner())


@asynccontextmanager
async def lifespan(_server: MCPServer[AppServices]) -> AsyncGenerator[AppServices]:
    yield load_services()


mcp: MCPServer[AppServices] = MCPServer(
    SERVER_NAME,
    title=SERVER_TITLE,
    description=SERVER_DESCRIPTION,
    instructions=SERVER_INSTRUCTIONS,
    website_url=SERVER_WEBSITE,
    version=version(SERVER_NAME),
    lifespan=lifespan,
    request_state_security=RequestStateSecurity.ephemeral(
        ttl=REQUEST_STATE_TTL_SECONDS, audience=SERVER_NAME
    ),
)


def read_only(title: str) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )


def cache_writing(title: str) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )


def translate_harness_errors[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(fn)
    async def translated(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await fn(*args, **kwargs)
        except HarnessError as err:
            raise ToolError(str(err)) from err

    return translated


async def get_diagnostics_tool(ctx: Context[AppServices]) -> DiagnosticsTool:
    return ctx.request_context.lifespan_context.diagnostics


async def get_plan_digest_tool(ctx: Context[AppServices]) -> PlanDigestTool:
    return ctx.request_context.lifespan_context.plan_digest


async def get_describe_tool(ctx: Context[AppServices]) -> DescribeTool:
    return ctx.request_context.lifespan_context.describe


async def get_provider_schema_tool(ctx: Context[AppServices]) -> ProviderSchemaTool:
    return ctx.request_context.lifespan_context.provider_schema


async def get_change_impact_tool(ctx: Context[AppServices]) -> ChangeImpactTool:
    return ctx.request_context.lifespan_context.change_impact


ResolvedDiagnostics = Annotated[DiagnosticsTool, Resolve(get_diagnostics_tool)]
ResolvedPlanDigest = Annotated[PlanDigestTool, Resolve(get_plan_digest_tool)]
ResolvedDescribe = Annotated[DescribeTool, Resolve(get_describe_tool)]
ResolvedProviderSchema = Annotated[ProviderSchemaTool, Resolve(get_provider_schema_tool)]
ResolvedChangeImpact = Annotated[ChangeImpactTool, Resolve(get_change_impact_tool)]


@mcp.tool(title='Check a Terraform module', annotations=read_only('Check a Terraform module'))
@translate_harness_errors
async def diagnostics(
    directory: containment.ProjectPath,
    tool: ResolvedDiagnostics,
) -> dict[str, Any]:
    """Check one Terraform module directory without changing it.

    Runs the terraform fmt check, terraform validate and tflint in the directory and returns
    each check's status (passed, failed or skipped) with its findings, each carrying the file
    and line when the tool reports one. A check whose binary is not on PATH is skipped with
    the reason. The directory is relative to the project root or absolute inside it.
    """
    return await tool.diagnostics(directory)


@mcp.tool(title='Digest a Terraform plan', annotations=read_only('Digest a Terraform plan'))
@translate_harness_errors
async def plan_digest(
    path: containment.ProjectPath,
    tool: ResolvedPlanDigest,
) -> dict[str, Any]:
    """Summarize one plan JSON document without changing anything.

    Reads a plan rendered by `terraform show -json <planfile>` and returns the count of
    resources per action (a replacement counts as replace), each changed resource with its
    address and actions (replacements marked, no-op resources left out) and the output
    changes, plus risk facts: per resource `forced_by` (attributes forcing a replacement),
    `sensitive_attributes` (names only) and `flags`, and top level `moves`, `imports`,
    `drifted` addresses and `plan_flags`. The path is relative to the project root or absolute
    inside it.
    A binary plan file or state JSON is refused; render it with `terraform show -json` first.
    """
    return await tool.plan_digest(path)


@mcp.tool(
    title='Describe Terraform configuration',
    annotations=read_only('Describe Terraform configuration'),
)
@translate_harness_errors
async def describe(
    path: containment.ProjectPath,
    tool: ResolvedDescribe,
) -> dict[str, Any]:
    """Summarize one Terraform module, `.tf` file or `.tfvars` file without changing anything.

    For a module directory or a `.tf` file, lists the variables (type, whether a default
    exists, description, sensitive), outputs, resources, data sources, module calls with
    their sources and required providers with source and version constraint, each with its
    file and line range. For a `.tfvars` file, lists the variables it assigns, split into
    those declared by the module in the same directory and those that are not. Files that
    cannot be read or do not parse are reported under problems. The path is relative to the
    project root or absolute inside it.
    """
    return await tool.describe(path)


@mcp.tool(
    title='Read a provider schema',
    annotations=cache_writing('Read a provider schema'),
)
@translate_harness_errors
async def provider_schema(  # noqa: PLR0913, PLR0917 - the MCP tool arguments are its schema
    path: containment.ProjectPath,
    type: str,  # noqa: A002 - the MCP tool argument is named type
    kind: SchemaKind,
    tool: ResolvedProviderSchema,
    block: str = '',
) -> dict[str, Any]:
    """Read one level of a provider, resource or data source schema without changing anything.

    Give the module directory, the type (a resource or data source type such as aws_instance,
    or the provider's local name such as aws when kind is provider) and the kind (resource,
    data_source or provider). The provider comes from the module's required_providers, or is
    hashicorp/<prefix> when undeclared. Returns the locked provider version beside the
    configuration's version constraint, the level's attributes (type, required, optional,
    computed, sensitive, deprecated, description) and one summary per nested block (nesting
    mode, min and max items, attribute and block counts). Pass block as a dotted path such
    as ebs_block_device or a.b to read a nested block or nested attribute instead of the top
    level. Needs the module initialized, with a .terraform.lock.hcl entry for the provider.
    The path is relative to the project root or absolute inside it.
    """
    return await tool.provider_schema(path, type, kind, block)


@mcp.tool(
    title='Trace Terraform change impact',
    annotations=read_only('Trace Terraform change impact'),
)
@translate_harness_errors
async def change_impact(
    path: containment.ProjectPath,
    tool: ResolvedChangeImpact,
    base_ref: str = 'HEAD',
) -> dict[str, Any]:
    """Report what a git diff changed in Terraform and which root modules it reaches.

    Give a directory inside the project and a base ref (default HEAD). Changes are the
    working tree, staged and untracked .tf files under that directory against the merge base
    of the ref and HEAD. Returns the changed blocks (added, modified or removed, a removed
    block located at its base file and line), each changed module's variable and output
    changes (added, removed, type or default changed, as expression text with whitespace
    collapsed) and every root module in the whole project that reaches a changed module with
    its shortest module call path. Reads only git and the files; no plan or state.
    The path is relative to the project root or absolute inside it.
    """
    return await tool.change_impact(path, base_ref)
