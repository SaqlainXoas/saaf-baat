# Saaf Baat - Claude Code Skills

This directory contains project-specific skills for Claude Code development.

## Structure

```
.claude/
├── plugin.json              # Skill configuration for this project
├── skills/
│   └── karpathy-guidelines/ # Coding best practices
│       ├── SKILL.md         # Guidelines for reducing LLM coding mistakes
│       └── EXAMPLES.md      # Real-world examples from the repo
└── README.md                # This file
```

## What Are Skills?

Skills are reusable prompts that teach Claude specific behaviors or provide guidelines for coding. They help maintain consistent coding standards and avoid common mistakes.

## Available Skills

### 1. Karpathy Guidelines (`karpathy-guidelines`)

Based on Andrej Karpathy's observations about LLM coding pitfalls, this skill teaches Claude to:

**The Four Core Principles:**

1. **Think Before Coding** - Surface assumptions and confusion rather than proceeding silently
2. **Simplicity First** - Write minimum code without speculative features
3. **Surgical Changes** - Only modify necessary code, avoid unrelated improvements
4. **Goal-Driven Execution** - Define verifiable success criteria

**Source:** https://github.com/forrestchang/andrej-karpathy-skills

## How It Works

When you work in this project, Claude automatically:

1. Reads `CLAUDE.md` for project-specific context (Saaf Baat architecture, workflows, etc.)
2. Loads skills from `.claude/plugin.json`
3. Applies the Karpathy guidelines when writing code

This gives you the best of both worlds:
- **Project knowledge:** What Saaf Baat is, how it works
- **Coding principles:** How to write clean, maintainable code

## Why This Setup?

**Separation of Concerns:**
- `CLAUDE.md` = Project documentation (what this project does)
- `.claude/skills/` = Coding guidelines (how to code well)

**Scalability:**
Add more skills later without cluttering `CLAUDE.md`:
```
.claude/skills/
├── karpathy-guidelines/
├── testing-strategies/
├── security-checklist/
└── documentation-helper/
```

**Project-Specific:**
These skills only apply to the Saaf Baat project. They won't affect other projects you work on.

## Adding New Skills

1. Create a new directory in `.claude/skills/`
2. Add a `SKILL.md` file with your guidelines
3. Update `plugin.json` to include the new skill:

```json
{
  "skills": [
    "skills/karpathy-guidelines/SKILL.md",
    "skills/your-new-skill/SKILL.md"
  ]
}
```

## References

- **Karpathy Guidelines:** https://github.com/forrestchang/andrej-karpathy-skills
- **Claude Code Documentation:** https://claude.ai/code
- **Examples:** See `.claude/skills/karpathy-guidelines/EXAMPLES.md`

---

**Note:** This setup is explicit to this project folder only. It does not affect global Claude Code behavior or other projects.
