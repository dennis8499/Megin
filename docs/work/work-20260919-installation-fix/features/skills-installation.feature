Feature: Skills-only installation and CI integrity

  Scenario: Install the bundle in a supported user-wide Skills root
    Given the corrected archive is extracted into CODEX_HOME/skills
    When Codex rescans the Skills directory
    Then the megin and megin-code-review Skills are discoverable
    And all twelve megin Skill directories are present

  Scenario: Reject an incomplete or drifted archive
    Given an archive is missing, duplicated, extra, or byte-different from a canonical bundle file
    When the Skills validator checks the archive
    Then validation fails with the affected entry reported

  Scenario: Validate the repository-local installation
    Given the canonical megin* folders are under the repository .agents/skills directory
    When the Skills validator checks the source tree
    Then all Skill frontmatter and implicit invocation metadata pass

  Scenario: Check whitespace in the actual change set
    Given a pull request or dispatch commit contains trailing whitespace
    When the portability workflow runs its diff check
    Then the workflow fails instead of checking only a clean checkout
