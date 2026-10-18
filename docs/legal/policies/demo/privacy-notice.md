<!--
Uvalu public legal page — DEMO version (demo-mode plan DM-5, docs/demo-mode-plan.md).
Shown instead of the beta notice when UVALU_DATA_MODE=demo (uvalu/pages_/legal.py looks in demo/ first).
Draft 18 October 2026, for the DM-7 legal-persona review (DM-D21); log, local-storage and usage-statistics wording updated after the demo privacy review (L34, L35). Describes only what the demo does:
no account, no sign-in to Uvalu, a per-session sample portfolio in temporary storage, hosting on Streamlit
Community Cloud (USA), the host's built-in viewer analytics (DM-D10), an optional feedback form.
Open before publishing:
- the feedback form provider and its location (section 4), once chosen (DM-D10);
- check Streamlit's current privacy policy and the cookies it sets on an invite-only app (section 6), in a
  browser on the deployed demo;
- the privacy mailbox provider (open item L5) is still [TBD] in the beta notice;
- Uvalu's own anonymous page events (DM-D10, before backers) are NOT described here; add them when built.
-->

# Privacy notice — demo

**Version:** demo 1.0 · **Effective from:** [date of first publication]

This notice covers the Uvalu demo: a preview of the app on 9 European stocks with a sample portfolio. The demo has no accounts. It explains which personal data is processed when you open it, by whom, and what your rights are.

## 1. Who is responsible

The controller for the demo is **Sven Claes**, trading under the name Uvalu, Pol Heynsstraat 7, 2200 Herentals, Belgium. Registration with the Crossroads Bank for Enterprises: pending.

Privacy contact: privacy@uvalu.app

## 2. What Uvalu itself processes

| Data | Purpose | Legal basis (GDPR art. 6) | Kept for |
| --- | --- | --- | --- |
| The changes you make to the sample portfolio and watchlist, and your language choice | Letting you try the app | Legitimate interest (showing how Uvalu works) | Until your browser session ends; a page reload or "Reset sample" starts again from the sample. Temporary storage is wiped when the demo restarts |
| Technical logs: the pages opened, errors and timings, under a random code for the session; no name, email or IP address | Keeping the demo working and fixing errors | Legitimate interest | Uvalu's own log file: while the demo runs, at most 31 days; it is deleted when the demo restarts. The hosting log is kept by Streamlit (section 3) |

Uvalu asks for no name, email address or password in the demo, and sets no cookies of its own. If you switch between the light and dark theme, your browser keeps that choice in its local storage. The sample portfolio is fictional; please don't enter real holdings.

## 3. Who hosts the demo

The demo runs on **Streamlit Community Cloud**, a service of Snowflake Inc. (USA). To show you the app, Streamlit's servers process technical data such as your IP address and browser type. The demo is invite-only: Streamlit asks you to sign in with the email address the founder invited (through Google, GitHub or a link by email) and processes that address to check your access. Streamlit does this under its own privacy policy (streamlit.io/privacy-policy).

**Viewer list.** Streamlit shows the demo's owner, and every other invited viewer, the total number of viewers and the last 20 viewers with the time of their last visit. For an invite-only app viewers are shown by the email address they signed in with. Uvalu uses this only to see whether invited testers opened the demo.

## 4. Feedback

If you use the "Give feedback" link, what you enter is processed by [TBD: FORM PROVIDER, LOCATION] and read by the founder to improve Uvalu. Kept for 2 years. Don't include personal data you don't want to share.

## 5. Transfers outside the European Economic Area

Streamlit Community Cloud runs in the United States. Transfers rely on the safeguards Snowflake offers under its own policy (such as the EU–US Data Privacy Framework or standard contractual clauses).

## 6. Cookies

Uvalu sets no cookies in the demo. The theme switch stores your light or dark choice in your browser's local storage; it is needed for a function you ask for, so no consent is asked. Streamlit sets cookies needed to run the app and to keep you signed in to the invite-only demo; see Streamlit's privacy policy. The demo doesn't send usage statistics to Streamlit.

## 7. Your rights

You have the right to access, correct and delete your personal data, to object to processing based on legitimate interest, and to complain to the Belgian Data Protection Authority (Gegevensbeschermingsautoriteit / Autorité de protection des données, www.dataprotectionauthority.be). For the demo, Uvalu holds almost nothing that identifies you; for what Streamlit holds, contact Streamlit. Write to privacy@uvalu.app; we answer within one month.

## 8. Not investment advice

The demo's scores, fair values and model signals are model outputs on sample data. They are not based on a profile of you and are not advice.

## 9. Changes

We may change this notice when the demo changes. The version and date at the top show which text applies.
