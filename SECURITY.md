# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Report them privately through
GitHub: **Security → Report a vulnerability** on this repository.

Include the Warden and CTFd versions, the steps to reproduce, and the impact you expect. You should
get a first answer within a week. Once a fix is released you will be credited in the changelog,
unless you prefer not to be.

## Scope

In scope: anything in this repository, for example a way for a player to reach an admin page,
read other players' data through a Warden endpoint, bypass a lockout or a challenge block
server-side, or break CTFd for other players through Warden.

Out of scope:

- Hiding from the detection signals (changing your User-Agent, clearing the device cookie,
  removing `navigator.webdriver`). Warden documents these as hints, not proof.
- Vulnerabilities in CTFd itself; report those to the
  [CTFd project](https://github.com/CTFd/CTFd/security).

## Supported versions

Only the latest release receives fixes.
