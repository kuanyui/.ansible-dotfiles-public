# roles/_shared/

A virtual role that holds **byte-identical fragments** shared between multiple
real roles (`dotfiles`, `zsh`, `container_templates`, ...).

## Why the `_` prefix?

Real roles run tasks; this directory has no `tasks/` and is never invoked as
`- role: _shared` in any playbook. The underscore signals "internal utility,
not a regular role".

## How it's consumed

Ansible's Jinja loader does NOT search across role boundaries, so we can't
`{% include 'roles/_shared/...' %}` from inside another role's template. Instead,
[`group_vars/all.yml`](../../group_vars/all.yml) declares vars whose values come
from `lookup('template', '<absolute path to file under _shared/templates/>')`.

Each shared block becomes a string variable (`shared_zsh_history` etc.) that
any role's template can drop in via `{{ shared_zsh_history }}`.

## When to add a fragment here

Only when **multiple roles already render the exact same byte sequence**, AND
you want a single edit to update all of them. If the content differs (even
trivially), keep it in each role's own template - the abstraction cost
outweighs the drift risk for small fragments.
