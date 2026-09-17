"""Independent hand derivation of the euro fund's parametric VaR at 2026-06-30 (BOOK-1a, MD-H1).

Run with packages/shared-python on sys.path (or from that directory).

Reads ONLY the book's own generated inputs (marks, loadings, factor returns) and the kernel's
published conventions (sample covariance over the 30 most recent business-day returns with an
n-1 denominator, quantized HALF_UP to 20 dp; factor exposure = loading x market value, quantized
HALF_UP; VaR = z(0.99) x sqrt(w' S w) HALF_UP 6 dp). It never calls the kernel.
"""

from decimal import ROUND_HALF_UP, Decimal, getcontext

from irp_shared.demo_tenant import book

getcontext().prec = 50
paths = book.generate_paths()
D = Decimal
Q20 = D(1).scaleb(-20)
Q6 = D("0.000001")
YE = book.YEAR_END
Z = D("2.326347874041")  # VAR_Z_SCORES["0.9900"], quoted verbatim from risk/bootstrap.py:738
efi_accounts = {a.code for s in book.FUNDS[1].sleeves for a in s.accounts}
specs = [i for i in book.INSTRUMENTS if i.account in efi_accounts]
# 1. market value per instrument in EUR (all EUR-denominated, base EUR, FX = 1)
mv = {i.code: (i.quantity * paths.marks[i.code][YE]) for i in specs}
total = sum(mv.values(), D(0))
print("EFI instruments:", len(specs), " total MV EUR @2026-06-30:", total)
# 2. loadings -> factor exposures (home-currency loading is zero, so FX_EUR gets none)
factors = ["RATES_EUR_10Y", "CREDIT_IG", "CREDIT_HY"]
expo = {f: D(0) for f in factors}
Q20e = D(1).scaleb(-20)
for i in specs:
    rows = []
    if i.rate_loading != 0:
        rows.append(("RATES_EUR_10Y", i.rate_loading))
    if i.credit_factor is not None and i.credit_loading != 0:
        rows.append((i.credit_factor, i.credit_loading))
    for f, w in rows:
        expo[f] = expo[f] + (w * mv[i.code]).quantize(Q20e, rounding=ROUND_HALF_UP)
for f in factors:
    print(f"exposure[{f}] = {expo[f]}")
# 3. sample covariance over the 30 most recent business days <= 2026-06-30
days = [d for d in book.RETURN_DAYS if d <= YE][-30:]
print("window:", days[0], "..", days[-1], "n=", len(days))
series = {f: [paths.factor_returns[f][d] for d in days] for f in factors}
n = D(len(days))
means = {f: sum(series[f], D(0)) / n for f in factors}
cov = {}
for a in factors:
    for b in factors:
        acc = sum(
            ((x - means[a]) * (y - means[b]) for x, y in zip(series[a], series[b], strict=False)),
            D(0),
        )
        cov[(a, b)] = (acc / (n - 1)).quantize(Q20, rounding=ROUND_HALF_UP)
for a in factors:
    print("cov", a, [str(cov[(a, b)]) for b in factors])
# 4. the quadratic form and the VaR
rad = sum((expo[a] * cov[(a, b)] * expo[b] for a in factors for b in factors), D(0))
sigma = rad.sqrt()
var = (Z * sigma).quantize(Q6, rounding=ROUND_HALF_UP)
print("radicand:", rad)
print("sigma:", sigma.quantize(Q6, rounding=ROUND_HALF_UP))
print("VaR 99/1d EUR:", var)
