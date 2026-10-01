# Legal Notice for AI-Powered Electronics Design Platform

**IMPORTANT: This is NOT legal advice. Consult with a qualified attorney before any distribution or commercial use.**

## Executive Summary

This project is an **independent, open-source implementation** that **does NOT** copy, fork, or derive from Flux.ai or any proprietary EDA software. We use existing open-source tools in accordance with their licenses.

## Patent Freedom to Operate Statement

As of September 2024, **no patents have been identified** that would prevent the core functionality described in this project.

However, **patent landscapes are dynamic**. If Flux.ai holds any active patents, they would need to be evaluated on a case-by-case basis.

### Pending Patent Searches

The maintainers have **not conducted a comprehensive patent search** for Flux.ai-related intellectual property. The following should be performed before:

1. Commercial distribution
2. Public release
3. Fundraising activities

## Trademark Notice

Flux, Flux.ai, and related marks are trademarks of Flux Lab Inc.

**This project:**
- Does NOT use the Flux brand
- Does NOT claim affiliation with Flux Lab Inc.
- References Flux.ai **only** for technical analysis and educational purposes

## License Compliance

### Core Architecture (GPL-Compatible)

This project uses:

| Component | License | Integration Method | Risk |
|-----------|---------|-------------------|------|
| KiCad | GPL-3.0 | Subprocess via kicad-cli | Low (separate process) |
| FreeRouting | GPL-3.0 | Subprocess via Docker/CLI | Low (separate process) |
| ngspice | BSD-3-Clause | Subprocess | None |
| Circuit JSON | MIT | Direct use | None |
| SKiDL | MIT | Direct use | None |

### Important: Subprocess Architecture

To maintain license compliance:

```
[Your Code (MIT/GPL)] 
    ↓ (subprocess call)
[KiCad (GPL-3.0)]
[FreeRouting (GPL-3.0)]
```

**DO NOT** link GPL code directly into your binaries. Use subprocess calls instead.

## Patent Risk Mitigation

### Safe Practices Implemented

1. **Independent Implementation**
   - All code is written from scratch
   - No code copied from proprietary sources
   - Algorithms re-implemented independently

2. **Process Separation**
   - External tools called as subprocesses
   - No static linking with GPL-incompatible code

3. **Documentation**
   - Development decisions documented
   - Design choices explained
   - Source attribution maintained

### Practices to Avoid

1. DO NOT copy Flux.ai's UI design
2. DO NOT use "Flux" in your project name
3. DO NOT claim to be "Flux.ai open source"
4. DO NOT implement their exact algorithms

## Recommended Actions Before Release

1. **Conduct Patent Search** (see flux-ai-patent-search.md)
2. **Review License Compatibility** (see LEGAL_DISCLAIMER.md)
3. **Document Your Independent Development**
4. **Consider Legal Insurance** for commercial distribution
5. **Get Legal Review** from an IP attorney

## How to Cite Flux.ai in Your Documentation

**ALLOWED:**
```
This project was inspired by Flux.ai and uses similar architectural concepts.
Flux.ai is a trademark of Flux Lab Inc. This project is not affiliated with Flux Lab Inc.
```

**NOT ALLOWED:**
```
This is a Flux.ai clone
This is Flux.ai open source
```

## Component Analysis

### Components That CAN Be Used

| Project | License | Commercial Use | Distribution |
|---------|---------|---------------|------------|
| KiCad | GPL-3.0 | ✅ Yes | ✅ Yes (with GPL compliance) |
| ngspice | BSD-3-Clause | ✅ Yes | ✅ Yes |
| FreeRouting | GPL-3.0 | ✅ Yes | ✅ Yes (with GPL compliance) |
| Circuit JSON | MIT | ✅ Yes | ✅ Yes |
| SKiDL | MIT | ✅ Yes | ✅ Yes |

### Components Requiring Caution

| Project | License | Risk | Notes |
|---------|---------|------|-------|
| Konnect | AGPL-3.0 | High | SaaS distribution requires source disclosure |
| circuitjson-toolkit | AGPL-3.0 | High | Avoid in hosted services |
| yaqwsx/jlcparts data | Unknown | Medium | Redistribution unclear |

## Security Notice

This project involves generating and modifying electronic design files. Be aware of:

1. **Safety** - Improper designs can cause hardware failures
2. **Verification** - Always validate designs independently
3. **Testing** - Test physical prototypes before deployment

## Disclaimer Language for Distribution

```
THIS SOFTWARE IS PROVIDED FOR REFERENCE AND EDUCATIONAL PURPOSES ONLY.
THE AUTHORS ASSUME NO LIABILITY FOR ANY PATENT INFRINGEMENT.
USERS SHOULD CONDUCT THEIR OWN PATENT AND LICENSE ANALYSIS.
```

## Contact for Legal Matters

- Document any patent concerns you discover
- Report license compatibility issues
- Keep development records for evidence of independent creation

## Revision History

| Date | Change | Author |
|------|--------|--------|
| 2024-09-30 | Initial legal notice | AI Assistant |

---

*This document should be reviewed by a qualified attorney before any public release or commercial use.*

## Related Documents

- `LEGAL_DISCLAIMER.md` - General legal guidance
- `research/flux-ai-patent-search.md` - Patent search instructions
- `LICENSE` - Project license (GPL-3.0)