# Public release validation runner output

These are actual local test-runner outputs on the reviewed public branch, not independently attested results. Python3.12.14 host, digest-pinned Python3.11.17 sandbox, Docker28.4.0, Node24.19.0. Dependency pins and commands are in ../../PHASE15.md and ../../PUBLIC_HISTORY.md.

All six selected suites exited0 without failures, errors or skips. The one-command fresh-setup/scripted-cycle demo and existing Bureau browser smoke also exited0. The browser cleanup harness initially mistook TCP TIME_WAIT for an active debugger listener; connection refusal subsequently confirmed shutdown. No model calls, paid API use, hosting or deployment. Public evidence validated7/7, preserving historical negative outcomes.

Original db0356f was separately reproduced unchanged:25 tests in197.199s. Its private Git bundle and original runner output remain outside the public repository because its commit metadata contains a private address. Source-tree identity before review fixes is recorded in ../../PUBLIC_HISTORY.md.
