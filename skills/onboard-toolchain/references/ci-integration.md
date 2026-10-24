# CI integration without disturbing what exists

Rules that apply on every platform:

1. Extend the existing job that already runs Terraform. Adding a second workflow that also plans creates two sources of truth.
2. Every added step is named. Every pre-existing unnamed step gets a name describing what it already does; its command does not change.
3. Steps are inserted in dependency order: install tools, auth, init, fmt, validate, lint, plan, plan JSON, scan, policy, docs check. Apply steps, if any exist, stay where they are.
4. Tool versions come from the repo's version file, not from a literal in the workflow. Read it in a step and pass it to the setup action or installer.
5. Keep the trigger set the repo already has. Add `schedule` only for the drift job the user asked for.
6. Do not change `permissions:`, `concurrency:`, `environment:`, or secrets references except for the specific row the user approved (usually the OIDC swap).

Before writing, confirm the current flags of every tool from its `--help` output. Several of these renamed flags across releases.

## GitHub Actions

### Extending an existing job

Read the workflow, find the job that runs `terraform plan` (or the orchestrator equivalent), and insert steps into its `steps:` list. Preserve YAML style (quotes, indentation, key order) so the diff stays reviewable.

Shape of an inserted block, after the existing init step and before the existing plan step:

```yaml
      - name: Format check
        run: terraform fmt -check -recursive
      - name: Validate
        run: terraform validate
      - name: Install tflint
        uses: terraform-linters/setup-tflint@v4
        with:
          tflint_version: ${{ env.TFLINT_VERSION }}
      - name: Lint
        run: tflint --init && tflint --recursive
```

After the existing plan step:

```yaml
      - name: Export plan JSON
        run: terraform show -json tfplan > plan.json
      - name: Scan plan
        run: trivy config --exit-code 1 --severity HIGH,CRITICAL plan.json
      - name: Policy check
        run: conftest test --policy policy plan.json
```

Set `TFLINT_VERSION` and friends at job or workflow `env:` by reading the version file in an earlier named step, or by referencing the value the user already keeps there.

### OIDC replacement (only when approved)

Replace static credential env entries with a role assumption step and add `id-token: write` to the job's permissions. Keep `contents: read`. Do not widen anything else.

```yaml
    permissions:
      id-token: write
      contents: read
      pull-requests: write
    steps:
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.PLAN_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}
```

GCP uses `google-github-actions/auth` with `workload_identity_provider`; Azure uses `azure/login` with `client-id`, `tenant-id`, `subscription-id` and federated credentials. The IAM trust on the cloud side is a follow-up for the user.

### Plan on PR

If the job already plans on PR, leave its structure alone and insert the gate steps around it. If it does not, add a named plan step that writes `tfplan` and `plan.json`. Do not add an apply step under any circumstances; an existing apply step is preserved byte for byte.

Posting the plan as a PR comment: if the repo already uses an action for this, keep it. Otherwise add a named step that writes `terraform show -no-color tfplan` into a comment via `actions/github-script` or the action the user prefers.

### Drift detection

Add a `schedule` trigger and a step that fails when the plan is non-empty:

```yaml
on:
  schedule:
    - cron: '0 6 * * *'
```

```yaml
      - name: Detect drift
        if: github.event_name == 'schedule'
        run: terraform plan -detailed-exitcode -input=false
```

Exit code 2 means changes present; the job fails and the user's existing failure notifications carry the alert.

### Reusable workflows

If the org has a central `.github` repository with reusable workflows, prefer `uses: org/.github/.github/workflows/terraform.yml@main` over inline steps, and put repo-specific values in `with:`. Confirm the central workflow exists before referencing it.

## GitLab CI

Extend the existing stage that runs plan. Add jobs with explicit `stage:` and `needs:` so ordering is visible. Auth via `id_tokens:` with the cloud's audience; the runner exchanges the token in a `before_script`. Artifacts carry `tfplan` and `plan.json` between jobs. Keep the existing `variables:` block intact.

## Azure Pipelines

Extend the existing stage/job; each `- script:` or `- task:` gets `displayName:`. Use a service connection with workload identity federation rather than a secret variable group for cloud auth.

## Jenkins, Bitbucket, CircleCI, other

Same ordering. Every stage or step is labeled. Version pins are read from the repo's version file in the first step. If the platform has no OIDC path to the cloud, say so in the report and leave auth as is; do not remove working credentials without a replacement.

## Local mirror

Whatever CI runs, the task runner runs with the same flags:

```make
fmt:
	terraform fmt -check -recursive
validate:
	terraform init -backend=false -input=false && terraform validate
lint:
	tflint --init && tflint --recursive
plan-json:
	terraform plan -out=tfplan -input=false && terraform show -json tfplan > plan.json
scan: plan-json
	trivy config --exit-code 1 --severity HIGH,CRITICAL plan.json
policy: plan-json
	conftest test --policy policy plan.json
policy-verify:
	conftest verify --policy policy
check: fmt validate lint policy-verify
```

A CI step whose command differs from the local target is a bug; fix one to match the other.
