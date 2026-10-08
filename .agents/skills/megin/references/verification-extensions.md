# Fixed inputs and observable verification

The existing v1 quality contracts accept optional `verification_inputs`,
`scenario_ids`, `behavior_trace` and `runner_preflight`. Omitting them preserves
the existing snapshot format and gate behavior. Approve additions as part of the
exact plan before capturing evidence.

## Fixed input bytes

Each input selects committed regular files from this Repo only:

```json
{
  "verification_inputs": [{
    "commit": "<full commit SHA from this Repo>",
    "files": [{"path": "tests/fixtures/input.json", "sha256": "<SHA-256 of committed bytes>"}],
    "check_ids": ["unit"]
  }]
}
```

Paths are canonical Repo-relative paths. Branch names, live working files,
symlinks, sibling Repos and unknown check IDs are rejected. The snapshot includes
the committed blobs as `@verification/<commit>/<path>`. Its
`verification_inputs_sha256` hashes the normalized inputs, including Git mode
and blob SHA. Each selected check result must record that digest and cite the
exact raw line `Verification inputs SHA-256: <digest>` through
`output.claims.verification_inputs`. A changed input invalidates downstream evidence.

```text
python .agents/skills/megin/scripts/verification_inputs.py --repo <Repo> --work-id <Work ID> --destination <empty-directory-outside-Repo>
```

The helper validates all inputs before writing and materializes exact Git bytes
under `<destination>/<commit>/<path>`. Use those files in the approved command;
do not silently substitute live fixtures. Preserve the returned digest in raw
output and structured results.

## Scenarios and runner probes

Declare both `scenario_ids` and `behavior_trace` together:

```json
{
  "scenario_ids": ["SCN-01"],
  "behavior_trace": [{
    "scenario_id": "SCN-01",
    "observable": "The user sees the accepted result",
    "assertion": "assert result == 'accepted'",
    "check_id": "unit",
    "implementation_paths": ["src/result.py"]
  }],
  "runner_preflight": [{"id": "python", "argv": ["python", "--version"], "cwd": "."}]
}
```

Every scenario has exactly one row, an observable result, an assertion, a known
check and Repo-relative implementation paths. The structural gate checks
completeness; the independent reviewer still verifies that assertions exercise
the promised behavior and failure cases.

```text
python .agents/skills/megin/scripts/behavior_trace.py --repo <Repo> --work-id <Work ID>
```

Use read-only, approved probes before test execution. Exact argv runs without a
shell in its declared Repo working directory, with a 30-second timeout. Results
distinguish `passed`, nonzero `failed`, and missing runner/timeout
`environment_error`. Save stdout as predeclared evidence and resolve failures
before continuing. Probes do not replace approved tests, test counts, independent
review or human acceptance.
