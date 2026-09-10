# Documentation

| Doc | For whom | What's in it |
| --- | --- | --- |
| **[OVERVIEW.md](OVERVIEW.md)** | Anyone — no tech background needed | What the project is, what each part does, how information flows through it, a glossary. Start here. |
| **[TECHNICAL.md](TECHNICAL.md)** | Developers | What's already built: stack, repo layout, every subsystem with key files and contracts, data model, API list, the signal-rule grammar, known stubs. |
| **[WORKFLOW.md](WORKFLOW.md)** | Developers (living doc) | How to set up and run it, the daily dev loop, step-by-step recipes for adding features, the "after new development" update checklist, and a change log. |
| **[CONFIGURATION.md](CONFIGURATION.md)** | Operators / developers | Every environment variable: default, effect, failure mode. Plus a minimal offline `.env`. |
| **[RULES.md](RULES.md)** | Anyone writing strategies | Copy-paste signal-rule expressions (RSI, crossovers, breakouts, combined) + gotchas. |
| **[DATA_FORMATS.md](DATA_FORMATS.md)** | Anyone feeding data in | Exact file/column/date formats each input connector expects; auth config for crawler & API. |

Project one-screen summary: [../README.md](../README.md)

---

### Reading order

- **New to the project?** OVERVIEW → then TECHNICAL if you'll be coding.
- **Setting it up?** WORKFLOW §1, then CONFIGURATION for the `.env`.
- **Adding a feature?** WORKFLOW §4 (recipes) and §7 (what to update after).
- **Feeding in data / writing rules?** DATA_FORMATS and RULES.
- **Need to know if something exists?** TECHNICAL (status legend: ✅ / 🟡 / ⬜).

### Keeping docs current

WORKFLOW §7 is the checklist. In short: a change that alters behaviour updates
the matching recipe, the relevant TECHNICAL section, and adds a line to the
WORKFLOW change log.
