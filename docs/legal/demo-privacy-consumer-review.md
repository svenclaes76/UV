# Demo review: privacy and consumer law

18 Oct 2026 · First-pass review with the legal counsel persona ([`docs/experts/legal-counsel-persona.md`](../experts/legal-counsel-persona.md)), scoped by expert profile [02](../experts/02-privacy-consumer-law-lawyer.md). It does not replace a review by a licensed Belgian privacy and consumer lawyer.

Reviewed: the demo privacy notice and data-sources page drafts in [`policies/demo/`](policies/demo/); the demo as built on `feature/demo-mode` (`01612a6`), checked in a local demo run and against the code (`uvalu/demo/workspace.py`, `uvalu/shell.py`, `.streamlit/config.toml`, `logging.config.json`); [`docs/demo-mode-plan.md`](../demo-mode-plan.md) §3 and DM-D10/D12. Background: [privacy and consumer review #2](privacy-consumer-review.md), [briefing 02](../experts/briefings/02-privacy-consumer-brief.md).

## Conclusion

- **Uvalu's own processing in the demo: low.** No account, no name or email asked, edits only in temporary storage for the session, no cookies of Uvalu's own. That is about as little as an app can process.
- **Hosting and access on Streamlit Community Cloud: medium.** The personal data in the demo sits mostly with Streamlit: the invite list, sign-in, IP addresses, usage statistics and a viewer list that **every invited viewer can see**. Uvalu chooses the host and who is invited, so it can't simply point to Streamlit's policy. Three things in the draft notice aren't accurate yet (§1), and one setting sends usage data to Streamlit that the notice doesn't mention (§2a).
- **Consumer law: low.** A free demo with no contract formed. The beta terms, which assume an account, don't fit and need a short demo version (§4).

## 1. The draft notice against what the demo does

| # | Draft says | What happens | Fix |
|---|---|---|---|
| a | "Uvalu sets no cookies of its own" | True for cookies. The theme toggle stores Light/Dark in the browser's localStorage. | Say so: "a theme preference in your browser's local storage, if you switch it". Strictly necessary for a function you ask for, so no consent (art. 5(3) ePrivacy, settled) |
| b | Technical logs "kept for 31 days" | Locally the demo writes to the repo's `logs/` folder (`logging.config.json` isn't redirected by the demo workspace). On Community Cloud the file vanishes on restart, but the console log goes to Streamlit's log viewer, whose retention Uvalu doesn't control. | Point the demo's file log into the workspace (L35) and reword: "kept while the demo runs; the hosting log is kept by Streamlit under its policy" |
| c | Viewers sign in "through Google, GitHub or a link by email" | Plausible for Community Cloud, but not checked against the current Streamlit sign-in options. | Verify on the deployed app before publishing |
| d | Transfers rely on "the EU–US Data Privacy Framework or standard contractual clauses" | Not checked which one Snowflake uses for Community Cloud. | Check Snowflake's current DPF listing and Community Cloud terms; name the one that applies |
| e | Section 4 feedback form `[TBD]` | No form chosen yet (DM-D10). | Fill in before the link goes live; the banner only shows "Give feedback" once `UVALU_FEEDBACK_URL` is set, which matches |

## 2. Findings

**a. Streamlit usage statistics (settled that it must be disclosed or switched off).** `.streamlit/config.toml` doesn't set `browser.gatherUsageStats`, so Streamlit's default applies and each visitor's browser sends usage statistics to Streamlit. This is a third-party transfer the demo notice (and the beta notice, for the Hetzner app) doesn't mention. **Recommendation:** set `gatherUsageStats = false` in the committed config. It costs nothing, removes the issue in both modes, and fits the "no tracking" stance (L34).

**b. The viewer list shows testers to each other (interpretation; transparency is settled).** On Community Cloud every viewer added to an app can open its analytics and see the last 20 viewers by email address (Streamlit docs, checked 18 Oct 2026). By inviting several people to one private app, Uvalu discloses each tester's email address to the others. The draft notice says so (§3), but a notice shown after sign-in is too late for the first visit. **Recommendation:** say it in the invitation itself ("other invited testers can see that you opened the demo"), keep the group small, or later move to a public app with a shared access code inside Uvalu, so nobody's email is involved (L36).

**c. Roles with Streamlit (unclear).** Whether Streamlit acts as Uvalu's processor or as an independent controller for viewer sign-in and analytics depends on the Community Cloud terms, which are written for the publisher as a consumer of a free service. In practice Uvalu can't sign a DPA for the free tier. **Recommendation:** describe Streamlit as a separate controller for sign-in, hosting logs and analytics (as the draft does), and ask the lawyer whether that holds (briefing 02, demo addendum).

**d. No age or residence check (interpretation).** The beta's consent step asks for EEA residence and 18+. The demo asks nothing. For a demo without an account or contract, that's acceptable; the terms should still say the demo is meant for adults in the EEA. **Recommendation:** one line in the demo terms (§4).

**e. Sample data, not real holdings (settled data minimisation).** The notice asks visitors not to enter real holdings. The app can't stop them. Because nothing persists beyond the session and nothing identifies the visitor, the risk is low. **No change**, beyond the sentence already in the draft.

**f. Feedback and later analytics.** The feedback form will be a processor or separate controller depending on the provider; pick an EU-hosted one and add it to §4 of the notice. Uvalu's own anonymous page events (DM-D10, before backers) must be added to the notice when built: what is recorded, that there's no name or IP, retention. Done right, no consent is needed (no access to the terminal, no identifier), but it must be described (art. 13 GDPR).

## 3. Paperwork

- **Record of processing (art. 30):** add one row for the demo: purposes, Streamlit as recipient, US transfer, retention.
- **Legitimate-interest note:** one paragraph for "showing the demo to invited testers and backers".
- **DPIA:** not needed (no special categories, no profiling, small scale); write the one-line conclusion next to the existing DPIA screening (L15).

## 4. Consumer law: demo terms

The demo links to the beta terms, which describe invitations, accounts, a consent step and account deletion; none of that exists in the demo. **Settled:** a free service still needs clear terms for liability and permitted use to be relied on; the Consumer Rights Directive's pre-contract duties mostly don't apply without a price. **Recommendation:** a one-page `policies/demo/terms-of-use.md`: what the demo is (sample data, nine stocks), not investment advice, no warranty and the usual liability limits, permitted use (no scraping or redistribution), adults in the EEA, Belgian law (L37). Picked first in demo mode, like the privacy notice.

## 5. Recommended changes

| # | Change | Where | Before |
|---|---|---|---|
| 1 | `gatherUsageStats = false` (L34) | `.streamlit/config.toml` | Testers |
| 2 | Demo file log into the workspace; notice reworded (L35) | `uvalu/demo/workspace.py`, `policies/demo/privacy-notice.md` | Testers |
| 3 | Notice: localStorage line; verify sign-in options and transfer basis on the deployed app | `policies/demo/privacy-notice.md` | Testers |
| 4 | Invitation text says other testers can see who opened the demo (L36) | Invitation email | Testers |
| 5 | Demo terms of use (L37) | `policies/demo/terms-of-use.md` | Testers |
| 6 | Record-of-processing row, legitimate-interest note, DPIA line | Paperwork (L15) | Testers |
| 7 | Feedback provider in the notice; page events described when built | Notice §4 | When the link / events go live |

## 6. Open items added

- **L34** Streamlit usage statistics off (§2a).
- **L35** Demo logs: file log into the workspace, notice wording (§1b).
- **L36** Viewer list visible to every invited tester (§2b).
- **L37** Demo terms of use (§4).
