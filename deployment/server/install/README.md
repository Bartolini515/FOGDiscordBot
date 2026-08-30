# FogBot manual-installation templates

These are static review examples. They **must not be installed verbatim**.
They contain deliberate placeholders and generic illustrative absolute paths only.

Before any installation, perform approved read-only server inspection to establish
the service account/group, ownership, the immutable release/shared/state layout,
available capacity, existing systemd unit, current symlink convention, and the
root-owned helper location. Fill placeholders only from that inspection, review the
rendered files, and obtain a separate approval for each server-side change.

The unit keeps runtime configuration outside `current`, uses release-local Python,
has finite start/stop bounds, and does not invoke a shell. The sudoers template
permits only the root-owned deployment helper's strict `current`, `status`, and
`submit` grammar; it does not grant general root or arbitrary systemctl access.
The optional sysusers/tmpfiles examples establish only restrictive directory shape.

No deployment is automatic: this repository deliberately includes no CD workflow.
Do not add tokens, keys, IP addresses, production account names, secret contents,
or production paths to these templates.
