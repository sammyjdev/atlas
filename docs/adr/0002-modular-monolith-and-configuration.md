# ADR 0002: Modular monolith, environment configuration and staged infrastructure

**Status:** Accepted
**Date:** 2026-09-17

## Context

ADR 0001 set the repository shape and the module boundaries but never named the
architectural style, and it assumed a `~/.atlas/config.toml` and independent
package releases. Phase 2a moves a running product into the workspace, so the
gaps had to be settled: what style the repository follows, how a module finds
its state when it runs on a laptop today and in a container later, how the
packages are versioned, and when infrastructure becomes code.

The modules are batch jobs with one author and one host. They do not need
independent scaling or independent deployment, and their triggers already differ
(a local scheduled agent for MERIT, a scheduled workflow for SAGE).

## Decision

1. ATLAS is a modular monolith: one repository, one image when a host needs one,
   one CLI facade. Boundaries are enforced by import-linter, not by a network.
   Modules integrate only through core contracts and the exchange.
2. Ports and adapters apply only at seams with more than one real
   implementation: LLM providers, the exchange store, and ORBIT's capture
   sources. Everywhere else, plain functions.
3. Configuration comes from environment variables. `ATLAS_HOME`, defaulting to
   `~/.atlas`, is the single anchor for module state. A configuration file
   arrives only when something cannot be expressed in the environment; this
   supersedes the `~/.atlas/config.toml` sentence in ADR 0001.
4. Every package carries the same version and is released together.
5. Infrastructure as code arrives with the infrastructure it describes: Compose
   and Ansible when the self hosted runner exists, OpenTofu when a cloud
   provider is chosen. Host specific files live in the private operations
   repository, never in this one.

## Consequences

- A module can be moved from a laptop to a container, a VPS or a scheduled cloud
  agent by changing environment variables and the trigger, without touching
  module code.
- Lockstep versioning means a change to a single module still publishes every
  package. That is the price of one coherent release, and it is cheap while one
  author ships all of them.
- The style is now falsifiable in review: a pull request that adds a network call
  between modules, an interface with one implementation, or a configuration file
  for a value the environment can carry, contradicts a recorded decision.
- ADR 0001's configuration sentence is superseded. Its exchange, boundary and
  repository decisions stand.
