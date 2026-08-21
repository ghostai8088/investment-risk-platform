# The drafting prompt — W19-S3a, INGEST-1

This is the VERBATIM prompt used to draft the demonstrating mapping proposal, committed so that
`ingestion_mapping_version.proposal_prompt_hash` (sha256 of this file's bytes) is checkable rather
than asserted. It is sent OPERATOR-SIDE, outside the deployed product, and carries **schema only**:
column names, inferred types, and shape-preserving obfuscated samples. No client holding appears
below, and none is needed to decide what a column means.

---

You are proposing a source mapping for a governed investment-risk platform.

A mapping is versioned DATA interpreted by a CLOSED vocabulary. Propose an ordered JSON array of
operations. Each operation is an object with `op`, `target`, and that operation's own parameters.

The ONLY permitted `op` values are:

- `rename` — `{"op":"rename","target":T,"source":COLUMN}` take a column's value unchanged
- `cast` — `{"op":"cast","target":T,"source":COLUMN,"to":"decimal"|"integer"|"string"}`
- `scale` — `{"op":"scale","target":T,"source":COLUMN,"factor":"<decimal string>"}`
- `parse-date` — `{"op":"parse-date","target":T,"source":COLUMN,"format":"<strptime format>"}`
- `code-lookup` — `{"op":"code-lookup","target":T,"source":COLUMN,"scheme":SCHEME}` resolve an
  instrument identifier
- `constant` — `{"op":"constant","target":T,"value":V}`
- `concatenate` — `{"op":"concatenate","target":T,"sources":[COLUMN,...],"separator":S}`

The ONLY permitted `target` values are: `portfolio_code`, `instrument`, `quantity`, `cost_basis`,
`quantity_unit`, `valid_from`. Of these, `portfolio_code`, `instrument`, `quantity` and
`valid_from` are REQUIRED.

Rules you must follow:

- `quantity` is SIGNED: long is positive, short is negative. Preserve the sign.
- Never invent a value the file does not contain. If a required target is not derivable from the
  schema, say so rather than proposing a constant that guesses.
- A date format is DECLARED, never sniffed. Choose it from the sample, and if the sample is
  ambiguous between day-first and month-first, say which you assumed and why.
- Columns you do not map are fine. Do not map a column merely because it exists.

Source type: POSITIONS. Schema of the file (name, inferred type, obfuscated sample — digits mapped
to digits, letters to letters, so shape is preserved and value is destroyed):

| # | Column | Inferred type | Obfuscated sample |
|---|---|---|---|
| 1 | `Account Ref` | text | `XXXX-XXXXXX-XX` |
| 2 | `Security Description` | text | `Xxxxxxxx Xxxxx xxx` |
| 3 | `SEDOL` | text | `X9XX999` |
| 4 | `Asset Class` | text | `XXXXXX` |
| 5 | `Unit` | text | `XXXXXX` |
| 6 | `Nominal (000s)` | number | `99.9` |
| 7 | `Book Cost (GBP)` | number | `99,999.99` |
| 8 | `Ccy` | text | `XXX` |
| 9 | `Valuation Date` | date-like | `99/99/9999` |

Return the JSON array and a short note on anything you assumed or deliberately left unmapped.
