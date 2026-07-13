---
name: AI Rules Bridge
alwaysApply: true
---

# AI Rules Bridge

`AI_RULES.md` là rule trung tâm của project và phải được ưu tiên khi có mâu thuẫn.

## Khi làm task code

Đọc và tuân thủ:

- `AI_RULES.md`
- `.clinerules/01_GOAL.md`
- `.clinerules/02_PROJECT_CONTEXT.md`
- `.clinerules/03_ARCHITECTURE.md`
- `.clinerules/07_CURRENT_TASK.md`

## Khi làm task UI/UX

Đọc thêm:

- `.clinerules/05_UI_UX_GOAL.md`

## Khi làm task deploy/env

Đọc thêm:

- `.clinerules/06_RAILWAY_DEPLOY.md`

## Rule quan trọng

- Không tạo controller/service/repository/dto không cần thiết.
- Không refactor ngoài phạm vi task.
- Ưu tiên sửa trực tiếp trong file domain hiện tại.
- Sau mỗi implementation task, cập nhật `.clinerules/07_CURRENT_TASK.md`.
