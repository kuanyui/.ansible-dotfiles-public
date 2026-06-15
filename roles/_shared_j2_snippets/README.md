# roles/_shared_j2_snippets/

Internal `_` role: **byte-identical Jinja shell-rc snippets** shared across roles
(no `tasks/`; never run as `- role:`).

- **Holds**: `templates/*.j2` - PS1 prompt lines, ls/cd aliases, zsh history + compinit
- **How**: `group_vars/all.yml` does `lookup('template', ...)` -> `shared_*` vars; a role's
  template drops them in via `{{ shared_zsh_history }}` etc. (Jinja can't `include` across roles)
- **Used by**: `bash`, `zsh`
- **Add one only** when 2+ roles render the EXACT same bytes - else keep it inline
