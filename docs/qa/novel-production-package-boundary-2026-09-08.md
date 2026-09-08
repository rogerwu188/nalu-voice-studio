# Novel source / professional package boundary

While inspecting new-version production, found the package excluded interactive
history but still included the project-bible namespace containing full downloaded
novel chapters and queue state. Removed that local namespace from the production
snapshot without altering SQLite. Approved episode script, style and other project
data remain. The bounded writer source path is unchanged.

Added actual public production-start API regression using isolated SQLite:
package excludes unselected novel and unapproved interview markers, contains the
approved script/style, and source database remains identical.12 production
authorization tests passed in5.40s; ruff passes. Dry-run package boundary only,
not real generation or end-to-end acceptance. Existing immutable packages are
not rewritten. New-version repair workflow remains unimplemented.
