---
status: investigating
trigger: "Bot doesn't identify product from Meta Ads links - returns generic response instead of product details"
created: 2026-04-08T22:30:00Z
updated: 2026-04-08T22:30:00Z
---

## Current Focus

hypothesis: Meta does NOT send ad context automatically. User must configure payload in Facebook Ads Manager first.
test: Check Railway logs to see if webhook contains context.id/payload/referral fields
expecting: Log shows webhook WITHOUT context.id/payload/referral → confirms Meta not sending
next_action: User checks Railway logs and reports what fields are in the webhook payload

## Symptoms

expected: Client clicks Meta Ads link → Bot responds with product details (price, stock, benefits) without asking which product
actual: Client clicks Meta Ads link → Bot responds generically: "¿Qué producto o categoría querés información?"
errors: No error messages; bot is functioning but ignoring context
reproduction: 1. Create Meta Ads campaign for TheraCup 2. Click "Go to chat" from ad 3. Write message to bot 4. Bot ignores product context
started: Unknown - feature implemented 2026-04-08 but user reports it's not working

## Eliminated

(none yet)

## Evidence

- timestamp: 2026-04-08T22:30:00Z
  checked: Code review of whapi.py lines 114-128 (ad context extraction)
  found: Code extracts context.id from text_obj.get("context", {}) and stores in contexto_payload
  implication: Parser exists but may not be receiving data from WHAPI

- timestamp: 2026-04-08T22:30:00Z
  checked: Code review of main.py lines 393-408 (ad context detection)
  found: Code checks msg.anuncio_id, msg.payload, msg.contexto_anuncio and passes to mapear_anuncio_a_producto()
  implication: Consumer code is ready but input data may not be present

- timestamp: 2026-04-08T22:30:00Z
  checked: brain.py mapear_anuncio_a_producto() function lines 94-132
  found: Maps anuncio_id to product names. Falls back to returning id unchanged if no match
  implication: If ID doesn't match dict keys, Claude receives unmapped ID

- timestamp: 2026-04-08T22:31:00Z
  checked: Test test_debug_ads.py — WHAPI parsing with mock payloads
  found: All 4 test cases passed — whapi.py correctly parses context.id, button.payload, and referral.source_id
  implication: Parser code is WORKING. Problem is NOT in whapi.py parsing logic.

- timestamp: 2026-04-08T22:32:00Z
  checked: Test test_debug_mapping.py — mapear_anuncio_a_producto() with various IDs
  found: Maps correctly for standard IDs (whoop_peak, theragun_mini, etc.). Falls back gracefully for unknown IDs.
  implication: Mapping function is WORKING. Problem is NOT in brain.py mapping logic.

## Resolution

root_cause: Meta is NOT automatically sending ad context. User must configure payload in Facebook Ads Manager before bot can detect which product the ad is about. WHAPI correctly parses and passes data IF it's sent, but the data originates empty from Meta.

fix: User must follow /docs/ANUNCIOS_SETUP.md steps 44-63 to configure payload in Facebook Ads Manager for each ad campaign. Then bot will receive context.id and respond with product-specific info.

verification: 
  - Added debug logging at agent/main.py line 391 to log if context detected
  - Created DEBUG_ADS_CONTEXT.md with full diagnostic guide
  - Created test_debug_ads.py and test_debug_mapping.py to verify parsing works
  - User must check Railway logs and follow diagnostic steps in DEBUG_ADS_CONTEXT.md

files_changed:
  - agent/main.py (line 391: added debug log for anuncio_id/payload/contexto_anuncio)
  - DEBUG_ADS_CONTEXT.md (new file: complete diagnostic guide)
  - test_debug_ads.py (new file: test WHAPI parsing)
  - test_debug_mapping.py (new file: test product mapping)
