# Financial terminology review of the translations

13 Oct 2026 · First pass in the role of expert profile [09](experts/09-financial-translators.md): a financial translator checking terminology, not re-translating. There is no separate persona file for this role. **It doesn't replace the five native-speaker specialists.** It flags terms they should decide on, and gives a suggestion for each.

**Reviewed:**

- `locales/glossary.csv`.
- The five `.po` files: 1,263 entries each, all approved, none fuzzy or empty.
- The terms that carry the most meaning: signal labels, risk bands, fair value, margin of safety, yield and return, and the regulatory lines.

## Conclusion

The files are complete and consistent with the glossary, and the regulatory lines read correctly. Four terminology problems remain. Each one changes what a user understands, and two concern texts the signal label review treats as legal texts:

| # | Problem | Languages | Severity |
|---|---|---|---|
| T1 | Two risk bands have the same, or almost the same, name | fr (identical), it, es | **High** |
| T2 | "Screened out" reads as "removed by *the filter*", so it gets confused with the user's own filters | all five | **High** |
| T3 | "Yield" is translated as the generic word for *return* | all five | Medium–high |
| T4 | "Fair value" means two different things across the languages | nl vs. fr, es, it | Medium |
| T5 | Informal address in legal and disclaimer texts | mainly fr | Medium (a decision) |
| T6 | "Mid score" reads as "average score" | fr, es, it | Low |
| T7 | The glossary is out of date | — | Low |

## T1. Risk bands that can't be told apart (high)

| Band | nl | fr | de | it | es |
|---|---|---|---|---|---|
| Elevated risk | Verhoogd risico | **Risque élevé** | Erhöhtes Risiko | Rischio **elevato** | Riesgo **elevado** |
| High risk | Hoog risico | **Risque élevé** | Hohes Risiko | Rischio **alto** | Riesgo **alto** |

- **French:** two of the five bands carry the **same label**. A portfolio at 60 and one at 80 show the same words in different colours.
- **Italian and Spanish:** *elevato / alto* and *elevado / alto* are near-synonyms. Most readers won't know which band is worse.

**Suggestion** (keep High as is; change Elevated):

| | Elevated risk |
|---|---|
| fr | *Risque accru* (or *Risque au-dessus de la moyenne*) |
| it | *Rischio sopra la media* |
| es | *Riesgo superior a la media* |

The English description, "above the scale's midpoint", supports "above average". Dutch and German are fine.

## T2. "Screened out" (high)

| nl | fr | de | it | es |
|---|---|---|---|---|
| Uitgefilterd | Écarté par le filtre | Ausgefiltert | Escluso dal filtro | Excluido por el filtro |

The Screener also says "X of Y stocks pass **your filters**", in every language with the same word. A user who sees "Écarté par le filtre" on a stock will think *their* filter removed it, not the model's screening rules. That breaks the meaning the signal label review was after: a stock that failed a named rule.

**Suggestion:** name the rules, not a filter.

| Language | Suggested label |
|---|---|
| nl | *Uitgesloten door screeningsregel* |
| fr | *Exclu par une règle de sélection* |
| de | *Durch Prüfregel ausgeschlossen* |
| it | *Escluso da una regola di selezione* |
| es | *Excluido por una regla de selección* |

These are longer, so the translators should check them in the badge width (in-context review). Shorter fallbacks: *Uitgesloten / Exclu / Ausgeschlossen / Escluso / Excluido*, with the rule shown in the reason line as now.

## T3. Yield vs. return (medium–high)

| | nl | fr | de | it | es |
|---|---|---|---|---|---|
| Yield | Rendement | Rendement | Rendite | Rendimento | Rentabilidad |
| Total return | Totaalrendement | Rendement total | Gesamtrendite | Rendimento totale | Rentabilidad total |
| Dividend yield | Dividendrendement | Rendement du dividende | Dividendenrendite | Rendimento da dividendo | Rentabilidad por dividendo |

On its own, *Rendement / Rendite / Rentabilidad* means **return** to most investors. The Screener's "Yield" column, showing for example 8.00%, then reads as "8% return". That figure doesn't promise anything, but it reads like it does.

**Suggestion:** use the dividend form wherever "Yield" means dividend yield, abbreviated for column headers:

| nl | fr | de | it | es |
|---|---|---|---|---|
| Div.rend. | Rdt div. | Div.-Rendite | Rend. div. | Rent. div. |

## T4. "Fair value" (medium)

| nl | fr | de | it | es |
|---|---|---|---|---|
| intrinsieke (model)waarde | juste valeur (du modèle) | fairer Wert | valore equo | valor razonable |

Two problems:

1. **Different concepts.** Dutch says *intrinsic value*; the others say *fair value*. The fair value is the core of the market-abuse (MAR) question: an "opinion as to the present value". Its label should mean the same in every language.
2. **A false friend.** *Juste valeur*, *valor razonable* and *valore equo* are the official IFRS 13 terms for **accounting** fair value, a market-based measurement. Readers with an accounting background may take Uvalu's model estimate for an audited figure from the annual report.

**Suggestion:** use the value-investing term everywhere, always with "model", which the English labels already carry:

| nl | fr | de | it | es |
|---|---|---|---|---|
| *intrinsieke modelwaarde* (as now) | *valeur intrinsèque du modèle* | *innerer Modellwert* | *valore intrinseco del modello* | *valor intrínseco del modelo* |

This is a terminology decision for the translators and lawyer #1 together. Note it in the glossary either way.

## T5. Form of address in legal texts (medium, a decision)

The spec chooses informal address everywhere (G-04, glossary: *je / tu / du / tu / tú*). French uses *tu / ta / ton* in 64 entries, including the disclaimers ("Pas une recommandation adaptée à **ta** situation"). In French-speaking Belgium and France, financial services and their legal notices almost always use *vous*. *Tu* in a paid investing tool's legal texts reads as unprofessional, and possibly as less binding.

- *du* in German and *je* in Dutch are common in fintech, so keep those.
- Italian and Spanish *tu / tú* are acceptable but less usual in finance. Ask the translators.

**Suggestion:** switch French to *vous*, at least in legal texts, disclaimers and the methodology. Record the decision as an exception to G-04.

## T6. "Mid score" (low)

| fr | es | it |
|---|---|---|
| Score moyen | Puntuación media | Punteggio medio |

*Moyen / media / medio* also mean "the average", so "a stock with the average score". *Score intermédiaire / Puntuación intermedia / Punteggio intermedio* says "middle band" without implying a mean. *Middenscore* and *Mittlerer Score* are fine.

## T7. Glossary out of date (low)

`locales/glossary.csv` still has:

- **"BUY / MONITOR / AVOID / VETO / Strong Buy: keep English"** and **"Hard veto"**. Both were replaced by the model signals and "Screened out".
- **No rows** for the current signal labels, "Model signal", the risk bands, "model fair value", or "quality screen / screening rule".

The glossary is what the translators will start from, so update it with T1–T6 before sending it out.

## What is right

- Margin of safety in all five languages.
- Low score, No signal and Model signal.
- The Belgian tax terms (*RV 30 %*, *Pr.M. 30 %*).
- The FSMA line in every language. The German *Wertpapierfirma* matches the German text of MiFID II itself, and the Spanish *empresa de servicios de inversión* is the correct term.
- The "not a recommendation tailored to you" tooltip, apart from the form of address (T5).

## Recommended changes, in order of value

1. **T1:** separate names for Elevated and High risk in fr, it and es (TR1).
2. **T2:** "Screened out" names the screening rules, not "the filter", in all five (TR1).
3. **T3:** dividend forms for "Yield" in all five (TR1).
4. **T4:** one fair-value concept in all languages, decided with lawyer #1; glossary note (TR2).
5. **T5:** a decision on *vous* for French legal texts (TR2).
6. **T6 and T7:** "Mid score" wording and the glossary update, before the packs go to the translators (TR3).
7. **In-context review** by the native specialists in the running app, per language, after TR1–TR3 (TR4).

Each change to a label is a change to a legal text. Bump the strings through the normal fuzzy-review loop (`tools/i18n_update.py`), and keep L6, the legal review of the translated disclaimers, open until a fluent reviewer signs off.
