---
name: AI Rules
alwaysApply: true
---

# AI Rules

## Goal

Build a Yoga/Gym Management System optimized for AI-assisted development.

## Tech Stack

- Python 3.13+
- FastAPI
- NiceGUI
- SQLite / PostgreSQL
- bcrypt (thay thế passlib)
- PyJWT

## General Rules

1. Do not over-engineer.
2. Do not use Clean Architecture.
3. Do not use DDD.
4. Do not use Microservices.
5. Do not create unnecessary files.
6. Do not refactor unrelated code.
7. Do not modify files outside the current task.
8. Always explain before creating new files.
9. Prefer business domain over technical layers.

## File Rules

Do NOT create:

- controllers
- services
- repositories
- dto
- interfaces
- mappers
- validators

Use business domains instead.

Example:

- customer.py
- drink.py
- ingredient.py
- product.py
- transaction.py
- package.py
- audit.py

## File Size Rules

- <300 lines = ideal
- 300-500 lines = good
- > 800 lines = split required

## Response Rules

For every task:

1. Implementation Plan
2. Files To Modify
3. Changes Made
4. Next Suggested Task

## Terminal Rules

- Never run long-lived commands.
- Never execute uvicorn.
- Never execute npm run dev.
- Never execute npm start.
- Never keep a server running.
- Only provide commands for me to execute manually.
