# Expert Profile: Native-Speaker Financial Translators

**Project:** Uvalu — stock screening and portfolio tool for solo retail investors
**Priority:** Medium–High — before launching in each language

---

## Why Uvalu needs these experts

Uvalu ships in six languages, and every language already has reviewed translations. This job is a specialist check of the financial terms, not translating from scratch. Financial terminology is precise and differs by language and market: a literal translation of "fair value", "margin of safety", "free cash flow" or "VaR" can be wrong, confusing, or even legally misleading. Disclaimers and legal texts must also match the approved wording in each language. One native-speaker specialist per target language is needed.

> Languages: English (source) plus Dutch, French, German, Spanish and Italian. That is five target languages, one translator each, all using the requirements below.

## Required expertise (per translator)

- **Native speaker** of the target language, translating from English
- Specialisation in **financial / investment translation** (annual reports, fund documents, broker research, financial websites)
- Familiarity with the local investment vocabulary used by retail investors and brokers in the target market (e.g. Flemish vs. Netherlands Dutch; Belgian vs. French French where relevant)
- Experience with **software localisation**: UI strings, placeholders, string-length constraints, plurals, number/date/currency formatting
- Ability to work with translation files (JSON/YAML/PO) and a CAT tool or localisation platform
- Bonus: certification (e.g. sworn translator, membership of a professional translators' association) and experience with legal texts

## Scope of work

1. **Terminology glossary:** start from `locales/glossary.csv` and `locales/review.csv`, then agree on one approved translation for each key term (fair value, intrinsic value, margin of safety, EV/EBITDA, EPV, composite score, quality screen, drawdown, VaR, CVaR, factor exposure, concentration, etc.)
2. **UI strings:** all screens, signal labels, tooltips, error messages, emails
3. **Methodology page** and help content
4. **Legal texts:** disclaimers, terms, privacy notice — translated from the lawyer-approved versions, then checked by the lawyer where required
5. **Formatting:** decimal separators, thousands separators, currency symbols, percentages, dates
6. **In-context review:** review translations inside the running app for truncation and context errors
7. **Marketing copy** (optional)

## Expected deliverables

- Shared multilingual glossary (term, definition, approved translation per language, notes)
- Translated string files
- In-context review notes and corrections
- Style guide per language (tone, formal vs. informal address, e.g. "u" vs. "je", "vous" vs. "tu")

## Material to prepare

- `locales/messages.pot` and the per-language `.po` files, with context (screen, max length, screenshots)
- The existing glossary (`locales/glossary.csv`) with definitions
- Brand guidelines (tone of voice)
- Staging environment with language switcher

## Questions to ask when selecting

- Show examples of financial or investment translations you have done
- Which localisation tools and file formats do you work with?
- How do you handle a term that has no established equivalent in your language?

## Red flags

- General translator without financial specialisation
- Relies on machine translation without disclosure or thorough post-editing
- Not a native speaker of the target language

## Where to find

- Professional translator associations (e.g. the Belgian Chamber of Translators and Interpreters, national associations per language)
- Localisation agencies with a finance vertical (for multiple languages at once)
- Freelance platforms filtered by financial specialisation and native language
