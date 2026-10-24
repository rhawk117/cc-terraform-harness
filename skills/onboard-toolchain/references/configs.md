# Configuration snippets

Starting points, not drop-ins. Adapt paths, providers, and versions to the repository's pins or the user's answers. When a file already exists, merge the relevant entries into it and keep everything that was there.

## .pre-commit-config.yaml

```yaml
repos:
  - repo: https://github.com/antonbabenko/pre-commit-terraform
    rev: <pinned pre-commit-terraform tag>
    hooks:
      - id: terraform_fmt
      - id: terraform_validate
        args:
          - --hook-config=--retry-once-with-cleanup=true
      - id: terraform_tflint
        args:
          - --args=--config=__GIT_WORKING_DIR__/.tflint.hcl
      - id: terraform_trivy
        args:
          - --args=--severity=HIGH,CRITICAL
      - id: terraform_docs
        args:
          - --args=--config=.terraform-docs.yml
```

Merging into an existing file: add missing hook ids under the existing `pre-commit-terraform` repo entry; do not add a second entry for the same repo. Keep any `args:`, `exclude:`, or `files:` the existing hooks carry.

## .tflint.hcl

```hcl
tflint {
  required_version = ">= <pinned tflint minor>"
}

config {
  call_module_type = "local"
}

plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "aws" {
  enabled = true
  version = "<pinned ruleset tag without v>"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}
```

Module repos add the curated `rule` blocks from `toolchain.md`. Existing `rule` blocks, including `enabled = false`, stay as written.

## trivy.yaml and .trivyignore

```yaml
severity:
  - HIGH
  - CRITICAL
misconfiguration:
  terraform:
    exclude-downloaded-modules: false
```

Migrating from tfsec: each `#tfsec:ignore:<id>` inline comment becomes `#trivy:ignore:<AVD id>`; the mapping is in Trivy's check documentation. Existing `.tfsec` config files are carried into `trivy.yaml` and listed in the plan.

## .checkov.yaml (when checkov is the mandated scanner)

```yaml
framework:
  - terraform_plan
quiet: true
soft-fail: false
```

Existing `skip-check:` lists are preserved verbatim.

## policy/ layout for conftest

```
policy/
  main.rego          # package main; deny[msg] rules
  lib/
    tags.rego
    network.rego
policy_test/
  main_test.rego     # conftest verify
```

First rule to ship, because it proves the plumbing before the interesting rules exist:

```rego
package main

deny contains msg if {
  some resource in input.resource_changes
  resource.type == "aws_s3_bucket"
  resource.change.after.acl == "public-read"
  msg := sprintf("%s must not be public-read", [resource.address])
}
```

Run `conftest verify` in the same CI step as `conftest test` so policy tests gate the policy.

## .terraform-docs.yml

```yaml
formatter: markdown table
output:
  file: README.md
  mode: inject
sort:
  enabled: true
  by: required
settings:
  lockfile: false
```

README needs `<!-- BEGIN_TF_DOCS -->` and `<!-- END_TF_DOCS -->` markers where the table should land.

## Version files

aqua.yaml:

```yaml
registries:
  - type: standard
    ref: <pinned aqua registry tag>
packages:
  - name: hashicorp/terraform@<version>
  - name: terraform-linters/tflint@<version>
  - name: aquasecurity/trivy@<version>
  - name: terraform-docs/terraform-docs@<version>
  - name: open-policy-agent/conftest@<version>
```

mise.toml:

```toml
[tools]
terraform = "<version>"
tflint = "<version>"
trivy = "<version>"
terraform-docs = "<version>"
conftest = "<version>"
```

`.terraform-version` holds only the Terraform version and is read by tenv/tfenv. Keep it in sync with the tool file; Renovate can manage both.

## renovate.json

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended"],
  "terraform": { "enabled": true },
  "asdf": { "enabled": true },
  "mise": { "enabled": true },
  "aqua": { "enabled": true },
  "pre-commit": { "enabled": true },
  "packageRules": [
    { "matchManagers": ["terraform"], "matchDepTypes": ["provider", "required_provider"], "groupName": "terraform providers" },
    { "matchManagers": ["github-actions"], "groupName": "github actions" }
  ]
}
```

Existing `packageRules` and `ignoreDeps` are kept; new rules are appended.

## AGENTS.md section

```markdown
## Terraform toolchain

Run before every commit: `make check` (fmt, validate, lint). Run `make scan` and `make policy` before opening a PR; both need a plan, which needs cloud credentials or `-backend=false` with a local override.

Tool versions live in `mise.toml` (or `aqua.yaml`); never install a different version ad hoc.

CI mirrors these targets exactly. If a CI step and a make target disagree, fix the mismatch rather than working around it.
```

Merge into an existing agent file under a new heading; do not restructure the file.

## .gitignore additions

```
.terraform/
*.tfstate
*.tfstate.*
*.tfplan
tfplan
plan.json
crash.log
override.tf
override.tf.json
*_override.tf
*_override.tf.json
```

Append only the lines that are missing.

## CODEOWNERS

```
*                  @org/platform-team
/policy/           @org/security-team
/.github/workflows/ @org/platform-team @org/security-team
```

Ask the user for the team handles; do not invent them.
