# Skill: bank transaction normaliser
- Read the bank statement line and return a JSON object with the keys date, amount, currency and category.
- Determine the sign of the amount: if the line contains "CR" or the word "REFUND" treat the amount as positive, otherwise make it negative.
- Parse dates flexibly: accept YYYY‑MM‑DD, DD/MM/YYYY, DD/MM/YY, or "DD MMM" (e.g., "13 FEB"). Convert two‑digit years to 20YY; if the year is missing, use 2026 as the default year. Output dates in ISO format (YYYY‑MM‑DD).
- Infer currency: default to "EUR" unless a dollar sign ($) appears, in which case use "USD".
- Map transaction descriptions to the allowed category vocabulary (all lower‑case):
  * groceries → "groceries"
  * software → "software"
  * dining → "dining"
  * transport → "transport"
  * travel → "travel"
  * income → "income"
  * refund → "refund"
  * any other description → choose the closest term from the list above based on common keywords (e.g., "card payment" → "income" if it is a credit, otherwise appropriate category).
- Always output a JSON object with exactly the keys: date, amount, currency, category, using the formats shown in the expected answers.
- Add "utilities" to the allowed category vocabulary.
- Map descriptions containing keywords such as "electric", "energy", "gas", "power" to the category "utilities".
- When a date string lacks a year component, assume the year 2026.
- Infer currency: default to "EUR" unless a dollar sign ($) appears (use "USD") or a pound sign (£) appears (use "GBP").
- Map descriptions containing keywords such as "fee", "fees", "account maint", "fx fee" to the category "fees" (overriding other category rules).
- Map descriptions containing the standalone keyword "to" (case‑insensitive) to the category "transfer", overriding other mappings. Additionally, map common grocery retailer keywords such as "centra", "supermarket", "market", "tesco" to the category "groceries".
