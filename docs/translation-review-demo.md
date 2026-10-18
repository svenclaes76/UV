# Translation review: demo texts

18 Oct 2026 · First pass in the role of expert profile [09](experts/09-financial-translators.md) (financial translator, checking terminology and consistency, not re-translating), like the [translation review of 13 Oct](translation-review.md). It doesn't replace the five native-speaker specialists (TR4).

**Reviewed:** the 20 demo texts in `nl`, `fr`, `de`, `it` and `es` (`feature/demo-mode`, after `a885955`), against `locales/glossary.csv`, the approved wording elsewhere in the catalogs (disclaimers, data-source rows, Methodology) and the house rule of informal address (G-04; the French *vous* question stays open under TR2).

**Also in scope (Sven, 18 Oct):** the price vendor's name appeared in two user texts outside the source lists. Both now say "end-of-day prices" without the name; the Data sources rows and the demo data-sources page keep it, where attribution belongs (open item L41).

## Conclusion

The drafts read well and follow the glossary. One terminology error matters: **"weekday" became a word that includes Saturday** in German, Italian and Spanish (§1). Three texts don't match wording already approved elsewhere (§2), and four small wording points are worth fixing (§3). All changes below are applied as **drafts (fuzzy)** for approval in Poedit.

## 1. "Weekday" (medium)

The refresh runs Monday to Friday. *Werktag* (de) includes Saturday in German law and common usage; *giorni feriali* (it) are all non-holiday days, Saturday included; *día laborable* (es) often includes Saturday. *Weekdag* (nl) is Monday–Friday and stays.

| | Was | Now |
|---|---|---|
| de | jeden Werktagabend | jeden Abend von Montag bis Freitag |
| it | ogni sera dei giorni feriali | ogni sera dal lunedì al venerdì |
| es | cada tarde de día laborable | cada noche de lunes a viernes |
| fr | chaque soir de semaine (colloquial) | chaque soir du lundi au vendredi |

In the Prices data-source row and the Methodology answer. Spanish also *noche* instead of *tarde*: 21:00 UTC is 22:00–23:00 in Spain.

## 2. Match approved wording

- **"Not investment advice" in the notice.** The approved disclaimer uses *conseil(s) en investissement* (fr) and *consulenza sugli investimenti* (it). The drafts said *un conseil en investissement* and *consulenza finanziaria*. Now: fr *pas de conseil en investissement*, it *non è consulenza sugli investimenti*. nl, de and es already matched.
- **Dividends row.** The approved Yahoo row reads *Uitkeringshistoriek van …* (nl), *Zahlungshistorie von …* (de), *Storico dei pagamenti di …* (it). The demo drafts used a compound (*EODHD-uitkeringshistoriek*, *EODHD-Ausschüttungshistorie*) or dropped *di*. Now aligned.
- **Reset in French.** The app says *Réinitialiser* for reset everywhere (*Réinitialiser le mot de passe*). *Rétablir l'exemple* → *Réinitialiser l'exemple*.

## 3. Smaller points

- **Reset tooltip** (fr, it, es): "d'exemple / di esempio / de ejemplo" at the end attached only to the watchlist. Now on the portfolio: *le portefeuille d'exemple et la liste de suivi*, *il portafoglio di esempio e la watchlist*, *la cartera de ejemplo y la lista de seguimiento*.
- **"Give feedback"** (it): *Lascia un commento* reads as "leave a comment" under an article. Now *Invia un feedback →*.
- **Page names in the Methodology answer**: the new sentence points to the Data sources page by its translated name (*Gegevensbronnen, Sources de données, Datenquellen, Fonti dei dati, Fuentes de datos*), as on the Legal page.
- **Checked, no change:** *slotkoers(en) / cours de clôture / Schlusskurs(e) / prezzo/i di chiusura / precio(s) de cierre*; *fundamentele gegevens / données fondamentales / Fundamentaldaten / dati fondamentali / datos fundamentales* (as the Data sources rows); *Branchenmultiplikatoren* (as in the Methodology); informal address (*je, du, puoi, puedes*; French impersonal); placeholders intact in all languages.

## 4. For the native-speaker specialists (TR4)

- Whether *Démo* / *Demo-Besucher* / *Visitante de la demo* should be capitalised or styled as the product's own term.
- Belgian French: *chaque soir du lundi au vendredi* is fine; check *rapports annuels* vs. *rapports de gestion* for Belgian companies.
- Flemish: *uitkeringshistoriek* is Belgian Dutch (Netherlands Dutch prefers *uitkeringsgeschiedenis*); keep, as the rest of the app uses it.
