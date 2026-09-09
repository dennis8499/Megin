
# Full-test runner revision evidence

- Work ID: work-20260908-tgrep-index-4f6a8a9c
- Evidence source: implementation run 299d340e2614f68184015cf1ecdcb5686f210dde1727b07235dd2516f12d82b8, attempt-002, command sequence 008.
- Previous exact command: python -X utf8 -B -m unittest discover -s .agents/skills/project-knowledge/scripts -p "test_*.py"
- Previous result: exit 1; 105 tests started; errors=152; skipped=0.
- Previous stdout: 0 bytes, SHA-256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855.
- Previous stderr: 109359 bytes, SHA-256 330fd08af61a48d357042b8eaed46088eb284f6d29f2542627e0becd24bc3f5f.
- Failure class: direct unittest discovery bypassed the existing full-suite fixture initialization; representative errors reported missing scenario_function and fixture_root.
- Existing runner contract: run_full_suite.py accepts --scope all, --profile local, --fixture-root, --jobs and --evidence-root; it creates a disposable fixture root, schedules the owner suites, emits knowledge-suite-report/v1, and writes validation-evidence/v1.
- Revised exact command: python -X utf8 -B .agents/skills/project-knowledge/scripts/run_full_suite.py --scope all --profile local --fixture-root .knowledge-test-tmp/fixtures --jobs 1 --evidence-root .knowledge-test-tmp/evidence
- Binding: the governed executor sets IMPLEMENTATION_READY_PAYLOAD_SHA256 to the current Ready handoff payload before execution. The command stays free of a circular literal digest.
- Scope classification: global-baseline, because CMD-TEST-FULL-001 is a full validation command and the new execution baseline applies to every work package.
