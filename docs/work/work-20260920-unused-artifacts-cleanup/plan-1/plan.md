# Plan 1: unused local artifact cleanup

## Implementation

1. Revalidate the workspace root, branch, HEAD, exact eight `v2-test-*` names, directory/link
   attributes, empty `plugins/`, ignored status, and absence of tracked target paths.
2. Move each exact target to the Windows Recycle Bin with
   `Microsoft.VisualBasic.FileIO.FileSystem.DeleteDirectory` and
   `RecycleOption.SendToRecycleBin`. Stop on any failure; never fall back to permanent deletion.
3. Confirm targets are absent, protected evidence and product files remain, and the tracked product
   snapshot is unchanged.
4. Run the approved archive validator and `git diff --check`, then hand off for fresh review and
   human acceptance.

## Forbidden changes

Do not remove or edit current installation-fix evidence, Skills package scratch, tracked source,
documentation, archives, binaries, historical work/knowledge records, Git configuration, or branch
state.
