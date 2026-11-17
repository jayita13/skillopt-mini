# Skill: bank transaction normaliser
- Read the bank statement line and return a JSON object with the keys date, amount, currency and category.
- Determine the sign of the amount: if the line contains a leading '-' or the transaction type is a debit (e.g., "Card Payment", "CARD PAYMENT", "PURCHASE"), make the amount negative; if it contains "CR", "CREDIT", "REFUND" or similar credit indicators, keep the amount positive.
- Parse dates flexibly: accept ISO (YYYY-MM-DD), slash-separated (DD/MM/YYYY or MM/DD/YYYY) and month‑name formats. When ambiguous, assume DD/MM/YYYY. Output the date in ISO format (YYYY-MM-DD).
- Map merchants/keywords to a fixed lowercase category vocabulary. Use the following mappings (case‑insensitive):
  * "Lidl", "Tesco", "Supermarket", "Grocery" → "groceries"
  * "Notion", "Software", "App", "SaaS" → "software"
  * "Uber", "Uber *EATS", "FreeNow", "Taxi", "Ride" → "transport"
  * "Restaurant", "Cafe", "Food", "Dining" → "dining"
  * "Delta Air", "Ryanair", "Flight", "Travel" → "travel"
  * "Salary", "Credit", "Income", "SEPA CREDIT" → "income"
  * "Refund" → "refund"
  * any other transaction → "unknown"
  Ensure the output category string is exactly the lowercase term from this list.
- If the line does not contain an explicit credit indicator (e.g., "CR", "CREDIT", "REFUND"), treat the amount as a debit and make it negative.
- When the year is not present, assume the current year (the year of execution, e.g., 2026).
- Extend the category mapping with utility keywords (case‑insensitive): "Electric", "Energy", "Power", "Gas", "Water" → "utilities".
- Extend the software category mapping with keywords: "AWS", "AMAZON WEB SERVICES", "OPENAI", "CHATGPT", "NOTION", "SOFTWARE", "APP", "SAAS" → "software".
- Add two generic category rules: if the line contains the keyword "FEE" (case‑insensitive) assign category "fees"; if it contains "RENT" or the word "TRANSFER" assign category "transfer".
- Add a generic category rule: if the line starts with the word "TO" (case‑insensitive) assign category "transfer"; if the line contains the keyword "EATS" (case‑insensitive) assign category "dining" (overriding the generic transport rule).
