# Legal Disclaimer and License Guidance

**IMPORTANT: This document is for informational purposes only and does NOT constitute legal advice. Consult with a qualified attorney for legal matters.**

## Project Philosophy

This project is an independent open-source effort to create an AI-powered electronics design platform. While inspiration from existing projects is acknowledged, this is NOT a fork, derivative, or recreation of any proprietary software.

## Key Legal Principles

### 1. No Infringement of Flux.ai IP

Flux.ai is a proprietary commercial product. This project:

- **DOES NOT** copy or reverse-engineer Flux.ai source code
- **DOES NOT** use Flux.ai trademarks, branding, or UI design
- **DOES NOT** replicate Flux.ai's proprietary features
- **MAY** reference Flux.ai as a technical reference for understanding requirements

**Safe usage pattern:**
- Describe features as "similar to Flux.ai" or "inspired by Flux.ai workflows"
- Do NOT claim to "reproduce Flux.ai" or "clone Flux.ai"
- Do NOT use "Flux", "Flux.ai", or variations in project name, logo, or marketing

### 2. Patent Considerations

To check if Flux.ai has active patents:

**Recommended sources:**
1. **Google Patents** - Search: "Flux.ai" or "Flux Laboratory" at https://patents.google.com
2. **USPTO Patent Database** - https://ppubs.uspto.gov/pubwebapp
3. **European Patent Office (EPO)** - https://worldwide.espacenet.com
4. **GitHub license fields** - Patent grants/restrictions

**Search terms:**
- "Flux.ai"
- "Flux Laboratory"
- "AI circuit design"
- "PCB routing AI"
- "Hardware design automation"

**Important:** Patent searches should be conducted by legal counsel. The absence of obvious patents in public databases does NOT guarantee freedom to operate.

### 3. License Compatibility Matrix

Since this project uses GPL-3.0 for core components, ensure all dependencies are compatible:

| License | GPL-3.0 Compatible? | Notes |
|---------|---------------------|-------|
| MIT | ✅ Yes | No issues |
| Apache-2.0 | ✅ Yes | No issues |
| BSD | ✅ Yes | No issues |
| GPL-3.0 | ✅ Yes | Direct match |
| AGPL-3.0 | ⚠️ Careful | May require service code disclosure |
| LGPL | ✅ Yes | With dynamic linking |
| Apache-1.1 | ❌ No | Incompatible |
| MPL-2.0 | ⚠️ Caution | File-level copyleft |
| Proprietary | ❌ No | Cannot be integrated |

### 4. Third-Party Component Management

**Permitted uses:**
- Using external libraries as separate dependencies (subprocess, not linking)
- Import and execution of GPL-compatible tools
- Use of open-source EDA tools (KiCad, ngspice, etc.)

**Prohibited uses:**
- Static linking with GPL-incompatible libraries
- Bundling proprietary code
- Redistribution of non-redistributable data

### 5. Attribution Requirements

**For GPL-3.0 components:**
- Keep copyright notices intact
- Include LICENSE files when redistributing
- Document modification in changelogs
- Provide source code upon request

**For MIT/Apache components:**
- Include LICENSE file in distribution
- Preserve notices in source files
- No copyleft restrictions

## Safe Development Practices

### Code Separation

```
your-project/
├── src/                  # Your code (GPL-3.0 or compatible)
├── cli/                  # GPL-3.0 wrappers (compatible)
├── agents/               # MIT/BSD orchestration code
├── tests/                # Tests (can have permissive license)
└── LICENSE               # Your main license
```

### External Tools

Treat external EDA tools as **services**, not libraries:

- Call KiCad via `subprocess` or `kicad-cli`
- Do NOT statically link with KiCad libraries
- Use IPC/MCP for communication where appropriate

## Documentation Guidelines

When referencing Flux.ai or similar projects:

**ALLOWED:**
```markdown
"We studied Flux.ai's architecture as a reference for implementing similar functionality."
```

**NOT ALLOWED:**
```markdown
"This is a Flux.ai clone" or "Flax-like" without clarification it's independent.
```

## Recommended Workflow

1. **Phase 1: Research** - Use external/ directory as reference only
2. **Phase 2: Implementation** - Write your own code
3. **Phase 3: Integration** - Use tools via subprocess/MCP, not as dependencies
4. **Phase 4: Review** - License compliance check before distribution

## Disclaimer Template for README

```markdown
## License

This project is licensed under the GNU General Public License v3.0.

**Legal Notice:** This software is an independent open-source project and is not affiliated with, endorsed by, or connected to Flux.ai, KiCad, or any other existing project.

**Patent Notice:** The authors make no representations regarding patent infringement. Users should conduct their own patent searches and consult legal counsel as needed.

## Credits

- KiCad - Copyright © 2008-2025 KiCad Developers (GPL-3.0)
- ngspice - Copyright © 2025 ngspice Developers (BSD-3-Clause)
- SKiDL - Copyright © 2019-2025 Martin Sustainable Development of Electronic Libraries (MIT)

*This project references existing open-source tools for educational and integration purposes only.*
```

## Contact for Legal Issues

If you encounter potential legal issues:
1. Document your analysis and findings
2. Consult with a qualified attorney specializing in software licensing
3. Consider legal insurance for commercial distribution

## Version History

- 2024-09-30 - Initial legal disclaimer draft
- TODO - Legal review by qualified attorney

---

*This document should be reviewed by legal counsel before any commercial distribution or publication.*