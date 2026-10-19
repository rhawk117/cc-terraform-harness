# Risk heuristics

What the `plan_digest` tool flags and why. Each flag is a prompt to look, not a verdict. The explanation you write should say what the plan actually shows, and downgrade a flag when the surrounding evidence makes it routine.

## Action-level flags

| Flag | Fires when | Why it matters |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `replace-delete-first` | A resource is replaced and Terraform will delete the old one before creating the new one | The resource does not exist for the duration of the create. For anything serving traffic or holding data this is an outage or a loss. |
| `replace-create-first` | Replacement with `create_before_destroy` | Usually safe for stateless things. Still worth naming the attribute that forced it, because the author may not have intended a replacement at all. |
| `destroy-stateful` | A stateful resource type (see list) is destroyed or delete-first replaced | Data, keys or secrets go with it. Ask whether a backup, snapshot, or `prevent_destroy` exists. |
| `mass-destroy` | 10 or more destroys and replacements, or at least 3 that together make up 30% or more of the resources in the plan | Looks like a wrong workspace, a wrong `-target`, a renamed module without `moved` blocks, or a lost state file. Check the intent before anything else. |
| `import` | A resource is being imported | Imports rarely hurt, but a plan that imports and then immediately changes the same resource is a sign the config does not match reality yet. |
| `drift` | The plan JSON reports resource drift | Someone changed something outside Terraform. The plan may be reverting a manual hotfix. |
| `unsupported-action` | The plan carries an action the digest does not classify | The digest cannot say what that action does. Read the plan entry yourself and say so in the explanation. |

## Stateful resource types

Destroying or delete-first replacing any of these loses data, keys, or identity that cannot be recreated by re-running apply. Matched by substring on the resource type.

- Databases and caches: `db_instance`, `rds_cluster`, `dynamodb_table`, `sql_database_instance`, `cosmosdb`, `elasticache`, `redis`, `memorystore`, `documentdb`, `neptune`, `spanner`, `bigtable`, `mssql`, `postgresql`, `mysql`, `mariadb`, `redshift`
- Object and block storage: `s3_bucket`, `storage_bucket`, `storage_account`, `storage_container`, `ebs_volume`, `compute_disk`, `managed_disk`, `persistent_volume`, `efs_file_system`, `fsx`, `filestore`
- Keys and secrets: `kms_key`, `kms_crypto_key`, `key_vault`, `secretsmanager_secret`, `secret_manager_secret`, `ssm_parameter`, `tls_private_key`, `acm_certificate`, `certificate`
- Queues and streams: `sqs_queue`, `kinesis_stream`, `pubsub_topic`, `pubsub_subscription`, `servicebus`, `eventhub`, `msk_cluster`, `kafka`
- Identity: `iam_user`, `iam_role`, `service_account`, `cognito_user_pool`, `identity_pool`
- Cluster control planes: `eks_cluster`, `container_cluster`, `kubernetes_cluster`, `gke`, `aks`

## Security-relevant attribute patterns

Flagged when they appear in the after-state of a created or updated resource.

| Flag | Pattern | Why |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `open-cidr` | `0.0.0.0/0` or `::/0` appears in an ingress, source range, or allowed CIDR field | Internet exposure. Correct for a public load balancer, wrong for nearly everything else. |
| `public-flag` | `publicly_accessible`, `public_network_access_enabled`, `map_public_ip_on_launch`, `assign_public_ip` set to true; `acl` set to `public-read` or `public-read-write` | Same as above, for resources that expose themselves without a firewall rule. |
| `deletion-protection-off` | `deletion_protection`, `prevent_destroy`, `enable_deletion_protection`, `purge_protection_enabled` transitioning true -> false | Often the first step of an accidental destroy in a later plan. |
| `encryption-off` | `storage_encrypted`, `encrypted`, `encryption_enabled`, `kms_key_id` transitioning to false or null | Compliance regression, and on some providers it forces a replacement. |
| `iam-change` | Resource type contains `iam`, `policy`, `role_binding`, `role_assignment`, `permission`, `access_control` | Privilege changes deserve a sentence even when small. Wildcards (`*`) in the after value get a second look. |
| `security-rule-change` | Resource type contains `security_group`, `firewall`, `network_acl`, `nsg`, `network_policy` | The blast radius is whatever sits behind the rule. |

## Judgement calls the tool cannot make

- Whether a destroy is intentional decommissioning. A plan that removes an entire module cleanly, with the PR title saying so, is fine. Say what is lost anyway; the reviewer decides.
- Whether `create_before_destroy` on a stateful resource is safe. A new RDS instance created before the old one is deleted still starts empty unless it is a read replica or restored from snapshot.
- Whether `(known after apply)` on an identity attribute (ARN, ID, name with a random suffix) will cascade replacements into dependents on the next plan. Mention it when the dependents are stateful.
- Cost. The tool does not price anything. Call out instance class, node count, storage size, and provisioned throughput changes as "cost likely changes" and leave the number to the reviewer.
