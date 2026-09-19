# FIXED-AUTHORITY-SCALE-001 — PRECONTACT SEAL

Sealed before scientific contact. No model call under any experimental arm
has been made as of this seal.

Frozen artifacts and SHA-256:

- tasks/t1/buggy_binary_search.py
  6ed6debf0ea94d59ab9b509c54cedf9a74a98d197dbd5ce4548dcde4228382f1
- tasks/t1/test_binary_search.py
  975abafcbd9340d01d24d1501d58f9531f845843ba5fcc08bea3884a61db0a2d
- tasks/t2/buggy_lru_cache.py
  f110e5eaa2bf0ef8ccd20041bec969aa9867fffd1597a7d6a5a2af858efb48a3
- tasks/t2/test_lru_cache.py
  8ad4be9b456f7bba5ea6b33cb0ca6ac87653cfd62b785695663a773cf05ab75
- tasks/t3/buggy_merge_intervals.py
  c1a230a749b410c002ecaad3bf385846a6a4c55d186e2750a224cb2c66f053ef
- tasks/t3/test_merge_intervals.py
  f683d4540889c2cfaa1654fe636a84ff8da06b79ae03ebef9bfd95852c302c72
- apparatus/prompts.json
  bd86af81caec8dc2edf70308ab83f31726d1cb4404b273f9d00c2f64bbb8da19
- apparatus/driver.py
  30aee2a3c8464aac43aa1b5cc2550dfcebae0f2cc3f06c7dbdbf000084ec0e6c
  (128 AST statements; ceiling 200)
- PREREGISTRATION.md
  7c9b213879ce4a0d3132a9419f97755106b96228c7ce799904866b71cfff315b

From this point: no prompt tuning, no role redesign, no task replacement, no
budget changes, no threshold changes, no arm additions, no retrying failed
runs to improve results, no -002. Transport retries only per the frozen
failure policy. First model API call after this seal = scientific contact;
its timestamp is recorded in runs/runs.jsonl.
