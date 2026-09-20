Feature: concise Skills-only repository and local integration

  Scenario: The retained bundle contains the current twelve Skills
    Given the repository contains the current Megin Skills source
    When the Skills validator checks the source and distributable archive
    Then all twelve Skills pass frontmatter and metadata checks
    And the archive has exactly the source files with matching bytes

  Scenario: Corrupt archive variants are rejected
    Given an archive is missing, extra, duplicated, or byte-different from a source file
    When the archive negative checks run
    Then validation rejects the affected archive

  Scenario: Retired content is absent after cleanup
    Given the cleanup manifest names retired records, tools, and scratch paths
    When the final repository manifest is inspected
    Then those paths are absent and the retained delivery record remains readable

  Scenario: Local main contains the verified cleanup
    Given review, automated verification, and human acceptance passed for the same snapshot
    When local delivery and integration run
    Then one cleanup commit is fast-forwarded into main
    And every deleted local branch is an ancestor of main
