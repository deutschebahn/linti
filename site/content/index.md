---
title: LinTi
description: Lint TM1 TurboIntegrator scripts with actionable findings.
---

::u-page-hero
#title
Lint your TurboIntegrator code

#description
LinTi checks TM1 TurboIntegrator scripts for formatting mistakes, naming conventions, and subtle code-quality issues. The playground, the rule reference, and the configurator run entirely in your browser.

#links
  :::u-button
  ---
  to: /playground
  size: xl
  icon: i-lucide-square-terminal
  ---
  Lint a process in your browser
  :::

  :::u-button
  ---
  to: /rules
  size: xl
  variant: outline
  icon: i-lucide-list-filter
  ---
  Explore the rules
  :::

  :::u-button
  ---
  to: /config
  size: xl
  variant: outline
  icon: i-lucide-sliders-horizontal
  ---
  Configure LinTi
  :::

  :::u-button
  ---
  to: https://github.com/deutschebahn/linti
  target: _blank
  size: xl
  color: neutral
  variant: outline
  icon: i-simple-icons-github
  ---
  Source on GitHub
  :::
::

::u-page-section
#title
What LinTi checks

#description
Every rule has a stable ID, an explanation, and examples you can edit and run.

#body
  :::u-page-grid
    ::::u-page-card
    ---
    title: Code quality
    description: Catch misplaced TI functions, empty blocks, unreachable code, and other logic smells.
    icon: i-lucide-shield-check
    to: /rules?group=C
    spotlight: true
    ---
    ::::

    ::::u-page-card
    ---
    title: Formatting
    description: Keep keyword casing, whitespace, and indentation consistent across processes.
    icon: i-lucide-align-left
    to: /rules?group=F
    spotlight: true
    ---
    ::::

    ::::u-page-card
    ---
    title: Naming conventions
    description: Enforce variable prefixes, consistent casing, and parameter naming.
    icon: i-lucide-tag
    to: /rules?group=N
    spotlight: true
    ---
    ::::

    ::::u-page-card
    ---
    title: External interactions
    description: Flag shell commands, hardcoded secrets, and inefficient ODBC access.
    icon: i-lucide-plug
    to: /rules?group=X
    spotlight: true
    ---
    ::::

    ::::u-page-card
    ---
    title: Auto-fix
    description: Safe findings are fixed for you with linti --auto-fix, or in the browser playground.
    icon: i-lucide-wand-sparkles
    to: /playground
    spotlight: true
    ---
    ::::

    ::::u-page-card
    ---
    title: Runs in your browser
    description: Paste a whole process to lint and auto-fix it with the real Python rules via Pyodide. Code is not sent to a server.
    icon: i-lucide-monitor-play
    to: /playground
    spotlight: true
    ---
    ::::
  :::
::

::u-page-section
#title
Install the CLI

#body
  ```bash
  pip install linti
  linti path/to/process.ti
  ```

  Tune it for your project with the [configurator](/config): pick a use case, adjust the rules, and download the `linti.yaml` next to your processes.
::
