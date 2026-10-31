# Mint Toolbox v0.5.0 desktop acceptance

1. Run `bash install-and-open.sh` as a normal user. The System extensions window should use English.
2. Inspect the tool table, search field, status filter, separate description and execution log.
   The distribution currently contains one real extension; multiple-row behavior is covered by GUI fixtures in CI.
3. Enable ZIP and Trash. Confirm that the full apt simulation and installation commands, live output,
   exit codes and final dpkg state appear. Test cancelling administrator authorization as well.
4. In Nemo, select disposable test files/folders containing spaces and Unicode filenames.
   Choose **Compress to ZIP and delete**. Its execution window must show zip, unzip, verification and GIO stages.
   Check the ZIP and Trash, restore test files, and repeat to check collision-safe archive names.
   Also test relative links, a dangling link and a directory link: the ZIP should preserve links, not copy their targets.
5. Disable the extension and check its status and menu removal. Re-enable it using **Build from source...**.
   The log must show source verification, a regular-user build, the generated deb path, apt commands and state readback.
6. Use **Copy log** and **Save log...**. The completed log must remain visible and automatically saved on disk.
7. Open the main toolbox, confirm English labels and manuals, and check existing tool filters and user registrations.

If the menu does not refresh, reopen Nemo windows or sign out and back in.
The program moves originals to Trash, never permanently deletes them. Use disposable data for acceptance.
