Feature: Clean clearly obsolete local artifacts

  Scenario: Move only the approved stale directories to the Recycle Bin
    Given the exact approved target manifest is present under the current workspace
    And the empty plugins directory has no descendants
    When the cleanup operation runs
    Then the approved targets are moved to the Windows Recycle Bin
    And no permanent deletion is attempted
    And protected current-work evidence and Skills package scratch remain present
    And no tracked product path is changed

  Scenario: Abort before mutation when preconditions drift
    Given an approved target is missing, renamed, tracked, linked, or otherwise changed
    When the cleanup preflight runs
    Then the cleanup stops before moving any target
    And the drift is reported for review

  Scenario: Preserve the repository product snapshot
    Given the cleanup has completed
    When the repository and Skills archive checks run
    Then Git reports no product additions, modifications, or deletions
    And the Skills archive validator passes
    And `git diff --check` passes
