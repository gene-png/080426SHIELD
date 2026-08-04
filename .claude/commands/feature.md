---
description: Plan and scaffold a new feature TDD-first. Produces a test file and a skeleton implementation before writing any real logic.
argument-hint: <feature name and short description>
allowed-tools: Read, Write, Bash(find:*), Bash(ls:*)
---

We are starting a new feature. Plan it before writing any code.

## Feature
$ARGUMENTS

## Step 1 — Understand the context
Read the relevant parts of the codebase: existing tests (`apps/api/tests/`, `e2e/smoke/`), the module layout under `apps/api/app/` or `apps/web/src/`, and any related modules. Do not assume — look first.

## Step 2 — Write a test plan
Before creating any files, describe:
- What behaviours need to be tested
- What the test file will be named and where it will live
- What each test case will assert (in plain English — no code yet)

Present this plan and wait for confirmation before proceeding.

## Step 3 — Create the test file
Write the test file with all planned test cases. Each test should be complete and meaningful — not just `expect(true).toBe(true)` placeholders. The tests must fail at this point because the implementation doesn't exist yet.

## Step 4 — Create a skeleton implementation
Create the implementation file(s) with the right exports and function signatures — but with bodies that throw `new Error('not implemented')`. This confirms the tests can find and import the code, and that they fail for the right reason.

## Step 5 — Run the tests and confirm they fail
Run `npx playwright test` (or relevant command) and show the failure output. Confirm each test is failing because the implementation is not done — not because of import errors or typos.

## Step 6 — Hand off
Report what files were created and what the next implementation step is.

**Your next command depends on what you want to do:**
- To implement all the scaffolded functions in one go as part of a planned sprint: run `/execute`
- To implement one specific function at a time with a guided TDD cycle: run `/tdd <function name>`
- To plan out all function signatures and process steps before building: run `/planfunction` first

The skeleton is ready. Nothing real is implemented yet — all function bodies currently throw `new Error('not implemented')`.
