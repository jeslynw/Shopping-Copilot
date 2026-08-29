
## §3b Miss analysis (V1 sessions that never hit)

misses: 25/200 · target rank in final-turn query: {'51–200': 9, '11–50': 12, '201–3000': 3, 'absent': 1}
by scenario: {'intent_override': 3, 'browsing': 9, 'buying': 9, 'boundary': 4} · by difficulty: {'hard': 3, 'medium': 13, 'easy': 9}

| sample | scenario | difficulty | target rank | disclosed constraints (first 3) |
|---|---|---|---|---|
| public_0002 | intent_override | hard | 66 | Buckle closure; Imported; leather |
| public_0015 | browsing | medium | 11 | Made in the USA or Imported; Ethylene Vinyl Acetate sole; fabric |
| public_0016 | browsing | medium | 128 | Imported; Rubber sole; leather |
| public_0020 | buying | easy | 291 | cotton; Imported; Solid colors: 100% Cotton |
| public_0028 | buying | easy | 142 | leather; Leather; Polyester lining |
| public_0035 | boundary | medium | 323 | fabric |
| public_0040 | browsing | medium | 88 | Imported; cotton; 100% Cotton |
| public_0041 | boundary | medium | 120 | polyester |
| public_0050 | boundary | medium | 19 | leather; 100% Leather |
| public_0058 | buying | easy | 18 | polyester; Imported; Zipper closure |
| public_0076 | browsing | medium | 17 | Imported; cotton; Solid colors: 80% Cotton, 20% Polyester |
| public_0087 | browsing | medium | 286 | Imported; Button closure; cotton |
| public_0092 | browsing | medium | 35 | Imported; Button closure; polyester |
| public_0094 | buying | easy | 159 | leather; Synthetic sole; Shaft measures approximately 8" from arc |
| public_0120 | browsing | medium | 34 | Snap closure; leather; Leather lining |
| public_0126 | browsing | medium | 54 | Imported; Pull On closure; polyester |
| public_0133 | buying | easy | 23 | Imported; Polycarbonate frame; Polycarbonate lens |
| public_0144 | intent_override | hard | 97 | Zipper closure; Imported; polyester |
| public_0145 | buying | easy | 29 | cotton; Imported; Cotton |
| public_0151 | browsing | medium | 33 | Imported; Rubber sole; leather |
| public_0159 | buying | easy | 13 | cotton; Imported; Drawstring closure |
| public_0174 | buying | easy | 117 | polyester; Imported; Tie closure |
| public_0180 | boundary | medium | None |  |
| public_0194 | buying | easy | 31 | rayon; Pull On closure; Hand Wash Only |
| public_0198 | intent_override | hard | 21 | Imported; PU; leather |

Reading: the tail is reachable — a ranking problem inside the BM25 top-N, not a recall problem (→ §3c).
