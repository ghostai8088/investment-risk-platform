# Outward benchmark: what a CRO's portfolio-risk overview shows (2026-09-18)

| Field | Value |
|---|---|
| Purpose | The outward-facing check required by `product_rebaseline_2026-09-17.md` section 4.7 (Part 4 rule 6b). It sits ahead of CRO-1's planning gate. |
| Citation rule | Roadmap Part 4 rule 6a, strengthened 2026-07-30: citations enter records only as verbatim quotes with locators, checked by an independent citation lane that reads only the cited source and the claim to test, never the draft's framing (CITE-7). |
| Yardstick checked | J-CRO-1 to J-CRO-8 in `personas_and_user_journeys.md` (the "Monday morning" walk, ratified DP-RB2-3). |
| Date accessed | 2026-09-18, all sources. |
| Status | CHECKED 2026-09-18 by an independent citation lane (Opus 5) in two passes: all seven sources re-fetched; **41 of 41 quoted passages verbatim** (executed: `grep -c '^> '` → 41). Pass one checked the 33 passages of the first draft and raised 13 findings, folded (section 6); the fold added seven passages (S1-d, S3-c twice, S3-d, S5-e, S6-f, S7-f) from the extracted texts, pass two re-fetched S1, S3, S4 and S6 and checked the five of the seven that come from those sources (S1-d, S3-c twice, S3-d, S6-f) — verbatim, with three locator or annotation defects fixed (CITE-2, CITE-6, CITE-7) — and supplied the 41st, S4-b, from its own extraction. S5-e (MSCI) and S7-f (BlackRock) were not in pass two's fetch, though the first form of this row said they were (VF1-01); they were checked at the round-2 fold on 2026-09-18 against a fresh `curl` fetch of msci.com (HTTP 200, 391,844 bytes) and blackrock.com (HTTP 200, 528,114 bytes), each byte-identical by SHA-256 to pass one's fetch: both verbatim after the same normalisation. So the 41 split 33 in pass one, five plus S4-b in pass two, two at round 2. Nothing below was written from memory. Every quote was copied from a file fetched on the access date. |

## 1. Method, and what failed

Each source was downloaded with `curl` and the text was extracted locally (pypdf for PDFs, tag stripping for HTML). Quotes were copied from the extracted text. Where pypdf split a word with a stray space (for example "Va R", "integr ated", "mo st", "arbi trage"), the word was joined, and typographic quotes and apostrophes were rendered as ASCII where pypdf or the HTML produced them. Dashes are kept as printed: three passages carry an em or en dash from the source (S5-c, S6-c, S7-b; executed over the 41 passages: `grep -cP '^> .*[\x{2014}\x{2013}]'` → 3; the only other non-ASCII characters are the bullet glyphs in S5-b, S5-c and S5-e). Nothing else was altered: no words were added, dropped or reordered in any passage (F-7). The first lane's count of "eleven of the 33 passages" with ASCII folding was its own tally over the first draft and is not re-measured here (CITE-6). Page numbers for PDFs are the PDF page index; where the document prints its own page number the printed number is given too.

Fetches that failed, and why:

- IOSCO, "Recommendations for a Framework Assessing Leverage in Investment Funds" (IOSCOPD645.pdf): HTTP 403 from iosco.org on both `curl` (two user agents) and the WebFetch tool. Not quoted. Search-result snippets about it are not used.
- MSCI product web pages (`riskmetrics-riskmanager`, `barra-one`): `curl` returned a reCAPTCHA interstitial, not the page. The WebFetch tool did return text for the RiskManager page, but through a summarising relay, so those sentences are not treated as verbatim and are not quoted. The MSCI RiskManager factsheet PDF fetched cleanly and is used instead.
- MSCI 2026 RiskManager factsheet PDF (the `downloads/web/...factsheet 2026.pdf` link): the server returned an HTML page, not a PDF. Not quoted. The May 2024 factsheet is used.
- SimCorp Axioma Risk (`simcorp.com/products/axioma-risk`): HTTP 404. Not quoted.
- FactSet risk analytics pages: the HTML shell returned no rendered body text (JavaScript-rendered). Not quoted. FactSet search snippets are not used.
- Federal Register HTML for SEC rule 18f-4: returned a 10 KB stub. The SEC's own PDF of the adopting release fetched cleanly and is used instead.
- sec.gov rate-limits repeat fetches: the citation lane's first re-fetch of the same PDF got HTTP 403 "SEC.gov | Request Rate Threshold Exceeded" from `curl` on both the `/rules/` and `/files/` paths, and obtained the file (406 pages, 2.7 MB) through the WebFetch fallback (F-0). The second lane pass found a working `curl` route: `https://www.sec.gov/files/rules/final/2020/ic-34084.pdf` with an SEC-style descriptive user agent that names a contact (HTTP 200, 2,779,848 bytes, 406 pages); the `/rules/final/` path still returned the 403 page. A re-checker should use the `/files/` path with that user agent (CITE-7b).

## 2. Sources and verbatim quotes

Seven sources fetched. Four are regulator or standard-setter text (ESMA/CESR, ESMA, SEC, FCA). Three are vendor public documentation (MSCI, Bloomberg, BlackRock).

### S1. CESR (now ESMA), Guidelines on Risk Measurement and the Calculation of Global Exposure and Counterparty Risk for UCITS

- URL: https://www.esma.europa.eu/sites/default/files/library/2015/11/10_788.pdf
- Publisher: Committee of European Securities Regulators (CESR), ref. CESR/10-788. Document date 28 July 2010. Hosted by ESMA.
- Accessed: 2026-09-18.

Quote S1-a (section 3.6.4 Back Testing, Box 18, paragraphs 2, 4 and 6; PDF page 29):

> "The back testing program should provide for each business day a comparison of the one-day value-at-risk measure generated by the UCITS model for the UCITS' end-of-day positions to the one-day change of the UCITS' portfolio value by the end of the subsequent business day."

> "The UCITS should determine and monitor the 'overshootings' on the basis of this back testing program. An 'overshooting' is a one-day change in the portfolio's value that exceeds the related one-day value-at-risk measure calculated by the model."

> "The UCITS senior management should be informed at least on a quarterly basis (and where applicable the UCITS competent authority should be informed on a semi-annual basis), if the number of overshootings for each UCITS for the most recent 250 business days exceeds 4 in the"

(The sentence continues on the next page; the extracted line ends there.)

Quote S1-b (section 3.6.5 Stress testing, explanatory text paragraph 65; PDF page 31, which prints 31; F-3 corrected the locator from page 30):

> "The stress tests should be integrated into the UCITS risk management process. That is to say that the stress test calculation results should be monitored and analyzed by the Risk Management function and they should be submitted for review to the Senior Management. The results should be considered when making investment decisions for the UCITS. If the stress test calculation results reveal particular vulnerability to a given set of circumstances, then they should give rise, if applicable and appropriate, to prompt steps and corrective actions for managing the risks appropriately (for instance hedging or reduction of exposures)."

Quote S1-c (section 3, Box 10 paragraph 2, and explanatory text paragraph 40; PDF page 22):

> "A UCITS should always set the maximum VaR limit according to its defined risk profile."

> "As part of the overall risk management process, a UCITS must establish, implement and maintain a documented system of internal limits concerning the measures used to manage and control the relevant risks for each UCITS. The VaR limits should always be set according to the defined risk profile."

Quote S1-d (section 3.8 VaR: Additional safeguards and disclosure, sub-section 3.8.1 Additional safeguards, explanatory text paragraph 74; PDF page 34; added at F-1; CITE-2 corrected the section from "3.6" — section 3.6 ends at 3.6.5 Stress testing, about ten pages earlier):

> "UCITS that resort to leveraged arbitrage strategies while measuring their global exposure with VaR, should therefore take appropriate additional measures to monitor their risk profile (e.g. use CVaR or other methods able to detect the potential impact of low-probability market events)."

(CVaR, conditional value-at-risk, is expected shortfall under another name. pypdf printed "arbi trage"; joined.)

### S2. ESMA, Guidelines on reporting obligations under Articles 3(3)(d) and 24(1), (2) and (4) of the AIFMD

- URL: https://www.esma.europa.eu/sites/default/files/library/2015/11/2014-869.pdf
- Publisher: European Securities and Markets Authority (ESMA), ref. ESMA/2014/869. Hosted by ESMA.
- Accessed: 2026-09-18.

Quote S2-a (heading "Risk profile of the AIF", sub-heading "Market risk profile", paragraphs 110 and 111; PDF page 28):

> "Under this section, AIFMs should report the following measures of risk: - The Net DV01 in three buckets defined by maturity of the security <5yrs, 5-15yrs and >15yrs; - The CS01 in three buckets defined by maturity of the security <5yrs, 5-15yrs and >15yrs; - The Net Equity Delta;"

> "AIFMs should always use the same methodology. When AIFMs report a "0" value for any measures of risk they should explain the reasons for this value."

(Footnote markers "3" and "4" after "15yrs" and "CS01" in the source are dropped here.)

### S3. U.S. Securities and Exchange Commission, "Use of Derivatives by Registered Investment Companies and Business Development Companies" (adopting release for rule 18f-4)

- URL: https://www.sec.gov/rules/final/2020/ic-34084.pdf
- Publisher: SEC, Release No. IC-34084 (adopted 2020).
- Accessed: 2026-09-18.

Quote S3-a (section I overview, bullet "Limit on fund leverage risk"; PDF pages 28 to 29):

> "The rule will generally require funds when engaging in derivatives transactions to comply with an outer limit on fund leverage risk based on VaR. This outer limit is based on a relative VaR test that compares the fund's VaR to the VaR of a "designated reference portfolio" for that fund."

> "These include permitting a fund to use its securities portfolio as the reference portfolio for purposes of the relative VaR test (instead of requiring a fund to compare its VaR against the VaR of a designated index for the relative VaR test), and increasing the relative and absolute VaR limits from 150% and 15% to 200% and 20%, respectively."

Quote S3-b (section I overview, the enumerated list inside the paragraph on the Form N-PORT / N-LIQUID / N-CEN amendments, not a bullet; PDF page 32; F-10):

> "(2) as applicable, information regarding a fund's VaR and designated reference portfolio, and VaR backtesting results; (3) VaR test breaches, to be reported to the Commission in a non-public current report; and (4) for a fund that is operating as a limited derivatives user, information about the fund's derivatives exposure and the number of business days that its derivatives exposure exceeded 10% of its net assets."

Quote S3-c (section II.D.1 "Use of VaR", the passage on stressed VaR and expected shortfall; PDF pages 92 to 93, which print 92 and 93; added at F-1; footnote marker "302" dropped from the first passage — marker "301" ends the sentence BEFORE the quoted span, and the second passage carries no marker; CITE-7b):

> "A few commenters suggested requiring funds to measure expected shortfall or stressed VaR, in addition to complying with the applicable proposed VaR-based tests, to address this incentive. Although we are not adopting a requirement that funds use stressed VaR or expected shortfall, funds may incorporate these methodologies into their derivatives risk management programs."

> "Expected shortfall analysis is similar to VaR, but accounts for tail risk by taking the average of the potential losses beyond the specified confidence level. For example, if a fund's VaR at a 99% confidence level is $100, the fund's expected shortfall would be the average of the potential losses in the 1% "tail," which are the losses that exceed $100."

Quote S3-d (section II.G.1 "Amendments to Form N-PORT", the paragraph on how the Commission will use reported VaR data; PDF page 202, which prints 202; added at F-12; no footnote marker falls inside the quoted span — marker "663" ends the sentence before it; CITE-7b):

> "These data points will also facilitate the Commission's monitoring efforts. For example, these data points can be used to identify changes in a fund's VaR over time, and trends involving a single fund or group of funds regarding their VaRs."

### S4. FCA Handbook, COLL 6.12 Risk management policy and risk measurement

- URL: https://www.handbook.fca.org.uk/handbook/COLL/6/12.html
- Publisher: Financial Conduct Authority (UK). The page states the section "was last updated on 01/01/2021".
- Accessed: 2026-09-18.

Quote S4-a (COLL 6.12.9 R, paragraphs (1)(a) to (1)(b) and (2)(a) to (2)(f)):

> "(1) An authorised fund manager of a UCITS scheme must adopt adequate and effective arrangements, processes and techniques in order to: (a) measure and manage at any time the risks to which that UCITS is or might be exposed; and (b) ensure compliance with limits concerning global exposure and counterparty risk, in accordance with COLL 5.2.11B R (Counterparty risk and issuer concentration) and COLL 5.3 (Derivative exposure)."

> "(2) For the purposes of (1), the authorised fund manager must take the following actions for each UCITS it manages: (a) put in place such risk measurement arrangements, processes and techniques as are necessary to ensure that the risks of positions taken and their contribution to the overall risk profile are accurately measured on the basis of sound and reliable data and that the risk measurement arrangements, processes and techniques are adequately documented; (b) conduct, where appropriate, periodic back-tests in order to review the validity of risk measurement arrangements which include model-based forecasts and estimates; (c) conduct, where appropriate, periodic stress tests and scenario analyses to address risks arising from potential changes in market conditions that might adversely impact the UCITS; (d) establish, implement and maintain a risk limit system for each UCITS; (e) ensure that the current level of risk complies with that risk limit system; and (f) establish, implement and maintain adequate procedures that, in the event of actual or anticipated breaches to that risk limit system, result in timely remedial actions in the best interests of unitholders."

(The handbook renders each sub-paragraph on its own line; they are joined with spaces here. The words are unchanged.)

Quote S4-b (COLL 6.12.11 R, paragraphs (1) and (2); the handbook prints "[Note: article 40(3) of the UCITS implementing Directive]" beneath (2); the rule is rendered "COLL 6.12.11 01/01/2021 R" between COLL 6.12.10 R (3) and COLL 6.12.12 R; added at CITE-5 from the second lane pass's own extraction):

> "(1) An authorised fund manager must employ an appropriate liquidity risk management process in order to ensure that each UCITS it manages is able to comply at any time with COLL 6.2.16 R (Sale and redemption). (2) Where appropriate, the authorised fund manager must conduct stress tests to enable it to assess the liquidity risk of the UCITS under exceptional circumstances."

(Sub-paragraphs joined with spaces, as for S4-a. No typographic characters occur in this passage, so nothing was folded. S4-b is a liquidity-risk rule and supports no J-CRO line; it is cited in section 4 only.)

### S5. MSCI, RiskMetrics RiskManager factsheet

- URL: https://www.msci.com/documents/1296102/1636401/RiskMetrics_RiskManager.pdf/1a878a4c-364e-444e-9239-2c89e07d1574
- Publisher: MSCI Inc. The document says "Data as of May 2024" and "©2024 MSCI Inc." (document code CFS0524).
- Accessed: 2026-09-18.

Quote S5-a (page 1, opening paragraph):

> "RiskManager provides risk analytics across a broad range of publicly traded instruments and private assets including Value-at-Risk (VaR) simulation methodologies, rigorous stress tests, factor risk exposure and decomposition, market exposure, and sensitivity analysis."

> "Risk teams can access results via an interactive web application, ready-to-use reports, APIs, and MSCI AI Portfolio Insights' dashboard visualizations and data warehouse."

Quote S5-b (page 2, heading "Key features"):

> "Market risk • Parametric, historical simulation, and Monte Carlo simulation VaR • Market exposure and sensitivities • Statistical and financial metrices"

> "Factor risk • Portfolio and position risk decomposition • Active risk and exposure drilldown • Single security analytics with country and sector exposures"

(The word "metrices" is as printed in the source.)

Quote S5-c (page 2, heading "Extensive suite of risk measures for", first bullets):

> "Ready-to-use library of historical events and hypothetical scenarios. • User-defined stress tests combining granular: – Risk factor stress tests. – Model parameter stress tests."

Quote S5-d (page 3, closing line):

> "RiskManager is designed to deliver efficient workflows, modelling transparency, and modern reporting tools to help risk teams manage risk across asset classes, from a granular holdings level to a macro factor level."

Quote S5-e (page 2, heading "Key features", the counterparty block; added at F-5):

> "Counterparty credit risk • Potential future exposure and expected positive exposure • Credit and debit value adjustment"

### S6. Bloomberg, "Portfolio & Risk Analytics, PORT <GO>" brochure

- URL: https://data.bloomberglp.com/professional/sites/4/Portfolio_and_Risk_Analytics_Brochure4.pdf
- Publisher: Bloomberg L.P. ("A Bloomberg Professional Service Offering"). The brochure's back matter reads "©2015 Bloomberg Finance L.P. All rights reserved. S604201473 0715", i.e. July 2015; its screen descriptions are 2015-era vendor practice (F-2 corrected "carries no date").
- Accessed: 2026-09-18.

Quote S6-a (section "UNDERSTAND YOUR PORTFOLIO'S FUTURE RISK EXPOSURES", printed pages 10 // 11, PDF page 7):

> "Bloomberg has developed fundamental risk factor models to help you measure and analyze portfolio risk through multiple lenses, including tracking error, stress testing, and VaR."

Quote S6-b (same section, "TRACKING ERROR" bullets and the "Tracking Error tab" caption):

> "Calculate risk in absolute terms or relative to your benchmark, another portfolio, fund or index"

> "Only Bloomberg provides the ability to click through to the underlying fundamental data for full risk data transparency"

> "Analyze your portfolio's ex-ante (predicted) risk by using one of Bloomberg's multi-factor risk models"

Quote S6-c (same section, "VALUE-AT-RISK" and "SCENARIO ANALYSIS" bullets):

> "Support for Monte Carlo, Historical, and Parametric VaR Methods across multiple confidence levels to calculate the maximum expected loss"

> "Evaluate your portfolio using a variety of historical stress scenarios—such as the global financial meltdown in 2008 or the Libyan oil crisis in 2011"

> "Create your own custom stress tests to gain greater insight into your portfolio's risk and validate current portfolio exposures"

Quote S6-d (section "PERFORMANCE ATTRIBUTION", printed pages 04 // 05, PDF page 4):

> "Break down your portfolio by asset class, sector, geographic region, duration, credit quality or any other custom classification"

Quote S6-e (section "ANALYZE YOUR PORTFOLIO'S HISTORICAL PERFORMANCE", printed pages 02 // 03, PDF page 3):

> "Examine standard deviation, beta, realized tracking error and dozens of other commonly used risk/return measures"

Quote S6-f (section "FACTOR-BASED PERFORMANCE ATTRIBUTION", printed pages 04 // 05, PDF page 4; added at F-4; CITE-6b corrected the heading from "PERFORMANCE ATTRIBUTION", which is S6-d's heading on the same page — a layout-aware extraction places this sentence under the third heading of the page):

> "Security returns are decomposed into the portion coming from exposure to risk model factors, such as industry, country, style, currency, curve and spread, and the portion coming from selection effect"

### S7. BlackRock, "Risk Management Services | Aladdin by BlackRock" (Aladdin Risk product page)

- URL: https://www.blackrock.com/aladdin/products/aladdin-risk
- Publisher: BlackRock, Inc. The page carries no publication date.
- Accessed: 2026-09-18.

Quote S7-a (section "A connected view of portfolio risk", key benefit 01, "See the whole portfolio, clearly"; F-11):

> "Gain a comprehensive, connected view of risk and performance across public and private markets. By applying consistent analytics across asset classes, Aladdin Risk enables more transparent, aligned analysis across strategies and teams, helping you understand portfolio positioning with greater clarity."

Quote S7-b (heading "Understand and manage what drives risk"):

> "Analyze exposures at a granular level—by factor, sector, or security—to uncover the underlying drivers of portfolio behavior. Combined with scenario analysis and stress testing, this enables teams to anticipate how portfolios may respond to changing market conditions and manage risk more proactively."

Quote S7-c (heading "Governance and Risk Radar"):

> "Scale portfolio oversight through integrated governance, compliance, and exception monitoring workflows. Risk Radar helps teams detect, analyze, and resolve risk issues through a transparent and auditable framework, supporting risk threshold monitoring, mandate compliance, and automated escalation workflows."

Quote S7-d (FAQ, "How can firms improve risk oversight across public and private investments?"):

> "By integrating public and private portfolio data within Aladdin's risk platform, investors gain a consolidated view of exposures, performance, and risk across all asset classes, including look-through into underlying fund holdings."

Quote S7-e (heading "Total Fund outcomes"; the phrase "Total Portfolio Approach" is in that block's first sentence, not the heading; F-11):

> "Aladdin Risk helps teams evaluate allocation changes, new exposures, and future commitments within a consistent framework, so they can assess trade-offs and make total fund decisions with greater confidence."

Quote S7-f (heading "Scenario analysis and portfolio modeling", the first sentence of its block; added at F-8):

> "Assess portfolio outcomes through stress testing, scenario analysis, performance attribution, and what-if modeling."

## 3. Map from J-CRO lines to sources

"Supports" means the source describes the thing the line puts on the screen. It does not mean the source describes the exact screen. No source describes a fund-ranked landing page for a CRO.

| Line | What the line shows | Sources that support it (PARTIAL where the cited quotes support only the generic half; F-6) | Note |
|---|---|---|---|
| J-CRO-1 | Funds ranked by limit headroom, with change since last close | PARTIAL — S4-a (risk limit system, current level of risk must comply), S7-c (risk threshold monitoring, escalation) support a limit system and threshold monitoring only; "headroom" appears in no fetched source | Limits and threshold monitoring are described. Ranking funds by headroom across a firm is not described anywhere. Change since last close is not described anywhere. |
| J-CRO-2 | Headline row: total exposure, VaR and ES at governed confidence and horizon with as-of date, tracking error vs benchmark, provenance one click away | S1-a (one-day VaR against end-of-day positions), S3-a (fund VaR vs reference portfolio VaR), S5-a and S5-b (VaR, market exposure), S6-a, S6-b, S6-c (tracking error, VaR at multiple confidence levels, absolute or relative to benchmark), S6-b (click through to underlying data), S3-c (expected shortfall) and S1-d (CVaR) | Expected shortfall is NAMED by one fetched source and CVaR by another (F-1, CITE-3): SEC IC-34084 (S3-c, PDF pages 92-93) names "expected shortfall", defines it, and states that funds "may incorporate these methodologies into their derivatives risk management programs" while declining to require it; CESR/10-788 (S1-d, PDF page 34, explanatory text paragraph 74) never uses the words "expected shortfall" (executed over the re-fetched text: 0 hits; "CVaR": 1 hit) — it recommends "CVaR or other methods able to detect the potential impact of low-probability market events" for leveraged arbitrage strategies, and CVaR is expected shortfall under another name (the file's gloss, not the source's words). Neither describes it as a headline display item. "Provenance one click away" is closest to S6-b's click-through to underlying data. As-of date is not stated as a display item anywhere. |
| J-CRO-3 | Limit posture: in force, breached, near threshold (80 percent), open breaches with owners and due dates | PARTIAL — S1-c (documented internal VaR limits), S3-b (VaR test breaches reported), S4-a (d), (e), (f) (risk limit system, compliance, timely remedial action on breaches), S7-c (threshold monitoring, escalation workflows) support a limit system with breach handling; the line's distinctive half is not described (CC-13) | Breach owners, response due dates, and the 80 percent near-threshold band are not in any source. Not walkable before UTIL-1 by design. |
| J-CRO-4 | Exposure composition by asset class, currency, sector, factor family; public beside private | PARTIAL — S5-b (country and sector exposures, factor decomposition), S6-d (break down by asset class, sector, region, duration, credit quality), S7-a, S7-b, S7-d (exposures by factor, sector, security; public and private on one view) support the composition view; currency as a composition axis is not described (CC-13) | Currency as a standalone exposure-composition axis on a risk overview is not described in any fetched quote; S6-f (PDF page 4, under "FACTOR-BASED PERFORMANCE ATTRIBUTION", CITE-6b) does name currency among the risk-model factors portfolios have exposure to, beside "currency effect" under attribution (F-4). |
| J-CRO-5 | Private sleeve: appraisal volatility beside desmoothed volatility with the difference; unfunded commitment and next call | PARTIAL — S5-a (private assets in scope), S7-a, S7-d, S7-e (public and private, look-through, future commitments) support only that a private sleeve exists on the same view; none mentions desmoothing at all (zero hits for "desmooth", "de-smooth", "smoothing" or "appraisal" across all seven sources) | No source mentions desmoothing, appraisal smoothing, or a reported-vs-desmoothed volatility comparison. S7-e mentions "future commitments" only as something evaluated in allocation decisions. |
| J-CRO-6 | Scenario P&L under the tenant's scenarios | S1-b (stress test results reviewed by senior management and used in decisions), S4-a (c), S5-c (historical events, hypothetical, user-defined stress tests), S6-c (historical and custom stress scenarios), S7-b | Strong support. This is the best-covered line. |
| J-CRO-7 | VaR series over the last quarter and rolling drawdown, as charts | PARTIAL — S1-a (daily VaR vs daily P&L, overshootings over 250 days), S3-d (the SEC's use of reported VaR to identify changes in a fund's VaR over time) | Backtesting (S1-a) and the SEC's stated use of reported VaR to identify changes in a fund's VaR over time (S3-d, PDF page 202) both imply a VaR series; no source describes a VaR trend chart or rolling drawdown on a risk overview (F-12). "Drawdown" appears in S3 only in the capital-call sense. |
| J-CRO-8 | Drill from total exposure to hierarchy nodes and holdings, sum holding | S5-b ("Active risk and exposure drilldown"), S5-d ("from a granular holdings level to a macro factor level"), S6-b (click through to underlying data), S7-b (exposures at a granular level by factor, sector, security), S7-d (look-through into underlying fund holdings) | Drill-down is widely described. "The sum holding" as a checked property is not described anywhere. |

J-CRO lines that NO source mentions at all: none of the eight is entirely absent. The parts of lines that no source mentions are: fund ranking by headroom and change since last close (J-CRO-1); the as-of date as a display item (J-CRO-2; expected shortfall itself is named by S3-c, and CVaR by S1-d, but neither as a headline item); breach owners, due dates and the 80 percent band (J-CRO-3); currency as a standalone exposure-composition axis on a risk overview (J-CRO-4, though S6-f names currency among the risk-model factors a portfolio has exposure to); desmoothing and the reported-vs-desmoothed difference (J-CRO-5, the whole point of the line); VaR trend and rolling drawdown charts (J-CRO-7); the sum-holding check (J-CRO-8). Five of the eight rows therefore carry PARTIAL (J-CRO-1, 3, 4, 5, 7); the first draft marked three and left J-CRO-3 and J-CRO-4 unmarked although their notes said the same thing (CC-13).

## 4. Things the sources show that the J-CRO lines do not ask for

- VaR backtesting: daily comparison of one-day VaR to realised P&L, an overshooting count over 250 days, and quarterly reporting to senior management when the count exceeds a threshold (S1-a; S3-b; S4-a (b)). The platform has backtesting families (BT-1, BT-3) but no J-CRO line shows the overshooting count.
- A relative VaR test against a designated reference portfolio, with a 200 percent relative and 20 percent absolute ceiling, and breach reporting to the regulator (S3-a, S3-b). J-CRO-2 shows VaR; no line shows VaR as a ratio to a reference portfolio's VaR.
- Fixed-income and credit sensitivities as reported risk measures: Net DV01 and CS01 in maturity buckets, Net Equity Delta (S2-a); "market exposure and sensitivities" (S5-b). No J-CRO line shows sensitivities.
- Counterparty credit risk and issuer concentration limits (S4-a (1)(b); S5-e). No J-CRO line. (F-5: the first draft cited S5-a for counterparty credit risk; that quote does not contain the term, S5-e does.)
- Liquidity risk and liquidity stress tests (S4-b, COLL 6.12.11 R (1) and (2); S5 lists liquidity risk). No J-CRO line. (CITE-5: the first draft cited the rule bare, with no verbatim passage; S4-b now carries it.)
- Multiple VaR methods and multiple confidence levels shown side by side (S5-b, S6-c). J-CRO-2 shows one governed confidence and horizon.
- What-if and trade simulation on proposed changes (S6 brochure section "SIMULATE TRADES"; S7 "what-if" scenarios). No J-CRO line; this is a PM concern, not the CRO walk.
- Performance attribution beside risk (S6-d, S7-f). No J-CRO line. (F-8: S7-a says "risk and performance", not attribution; S7-f names attribution.)
- Mandate compliance and automated escalation workflows as part of the same oversight screen (S7-c). J-CRO-3 shows breaches and owners but no escalation workflow.
- Documented risk-measurement arrangements, periodic back-tests that validate model-based forecasts, and the requirement that stress test results feed investment decisions and corrective action such as hedging (S1-b; S4-a (a) for documentation and S4-a (b) for the periodic back-tests). "Model validation" as a named service appears only in S5, page 2 ("expert setup, installation, integration, and model validation"), which is not quoted (F-9). This is process, not a screen item, but a CRO overview in these sources sits inside a documented limit-and-review process.

## 5. What this benchmark does and does not claim

- It shows that VaR, stress and scenario results, limits with breach handling, exposure breakdown by classification, and drill-down to holdings are standard content in both regulator text and vendor documentation. J-CRO-2, 6 and 8 rest on that; J-CRO-3 and J-CRO-4 rest on it for their generic half only (a limit system with breach handling; a composition view) — owners, due dates, the 80 percent band and currency as a composition axis are in no source (PARTIAL, CC-13).
- It shows that no fetched source describes the private-sleeve desmoothing comparison (J-CRO-5) or the trend charts (J-CRO-7). Those lines rest on the owner's ratification (DP-RB2-3) and on the platform's own thesis, not on an outward claim. Expected shortfall, by contrast, is named by a regulator (S3-c) as a measure funds may use, and CESR (S1-d) names CVaR, which is expected shortfall under another name (CITE-3: the gloss is this file's, not the source's), so J-CRO-2's ES element does have outward support; what no source describes is ES as a headline display item (F-1).
- It does not claim any source describes a CRO landing page ranked by fund headroom. J-CRO-1 is the platform's own design.
- The Bloomberg evidence (S6) is a July 2015 brochure, a decade old; S5 (May 2024) and S7 (undated live page) carry the current-practice weight (F-2).
- The citation lane checked every quote above against re-fetched sources on 2026-09-18 (section 6).

## 6. How this benchmark was checked

**Pass one.** An independent different-engine citation lane (Opus 5) was given the quoted passages, the J-CRO line texts and the claims to test — not the draft's framing or argument, per roadmap Part 4 rule 6a ("reads ONLY the cited source (never the draft's framing)"; CITE-7 corrected the first attestation, which said the lane "saw only the sources" and then described it re-judging the draft's rows). It re-fetched all seven sources on 2026-09-18 (S3 through the WebFetch fallback after sec.gov returned 403 to `curl`), extracted the text into the session scratchpad (`cite/s1.txt` to `s7.txt`), and compared every quoted passage of the first draft character by character after whitespace normalisation: 33 of 33 first-draft passages VERBATIM, none altered, none not found, none unreachable; the section 1 failure list re-tested and still true (iosco.org 403, simcorp.com 404). It re-judged all eight J-CRO mapping rows against the sources and the source rule (7 sources, 4 regulator or standard-setter, 3 vendor; both thresholds cleared). It checked 67 claims and raised 13 findings: 1 HIGH (F-1, expected shortfall named by S3, CVaR by S1), 5 MED (F-2 the Bloomberg date, F-3 an S1-b page off by one, F-4 currency named as a risk-model factor in S6, F-5 a quote label carrying a fact true of the source but not of the quote, F-6 mapping rows asserting support for lines whose distinctive half no quote describes — three marked PARTIAL at the fold, five after CC-13), 7 LOW (F-0 the attestation, F-7 ASCII folding undisclosed, F-8 S7-a cited for attribution, F-9 "model validation" not in the cited passages, F-10 a bullet that is an enumerated list, F-11 two S7 headings, F-12 S3 page 202 under-cited). All 13 were folded into this file on 2026-09-18 by re-reading the extracted texts (the new quotes S1-d, S3-c, S3-d, S5-e, S6-f and S7-f were copied from them and their PDF pages re-derived from the extraction's page markers); none was refuted. The findings are labelled by id where they changed a sentence.

**Pass two (the ratification-diff verification, 2026-09-18).** The seven passages added at the fold had not been lane-checked (CITE-1, CC-3: the file then said "33 of 33" over a file holding 40). A second citation lane (Opus 5, sources only, 21 claims checked) re-fetched S1, S3, S6 and S4 and checked the five of the seven that come from those sources: S1-d, S3-c (both passages), S3-d and S6-f are VERBATIM after the same normalisation. The other two fold-added passages, S5-e (MSCI factsheet) and S7-f (BlackRock page), come from sources pass two did not fetch; the first form of this paragraph listed them among the seven checked (VF1-01, round 2 of the ratification-diff verification). They were checked at the round-2 fold on 2026-09-18 against a fresh `curl` fetch: msci.com HTTP 200, 391,844 bytes, SHA-256 `c397ff88...`; blackrock.com HTTP 200, 528,114 bytes, SHA-256 `15fd3f13...`; both files byte-identical to pass one's fetch of the same day. S5-e is VERBATIM on PDF page 2 and S7-f is VERBATIM as the first sentence under the heading "Scenario analysis and portfolio modeling" (executed: `norm(quote) in norm(text)` → True for both, against the fresh fetch and against pass one's extraction). Four findings, all folded: CITE-2 (S1-d sits in section 3.8.1, not 3.6 — paragraph and page were right), CITE-6 (S6-f sits under "FACTOR-BASED PERFORMANCE ATTRIBUTION", not "PERFORMANCE ATTRIBUTION"), CITE-7 (the S3-c and S3-d footnote annotations claimed removals of markers that were never inside the quoted spans; and a working `curl` route for S3 recorded in section 1), CITE-5 (COLL 6.12.11 was cited bare in section 4; the lane supplied its verbatim text, added as S4-b). The file now holds 41 quoted passages, all 41 checked: 33 in pass one, five plus S4-b in pass two, two at round 2 (executed after the round-2 fold: `grep -c '^> '` → 41).
