# Observed timing audit

Shared throttling is included in elapsed time. Queue subtraction is not an unthrottled speed estimate.

Median queue fraction: 19.1%. Isolated timing eligible: 0/32.

| Run | Elapsed | Queue wait (union) | Observed remainder |
| --- | --- | --- | --- |
| queue-r1-aaa-execution | 459.0s | 70.9s | 388.1s |
| queue-r1-aab-execution | 511.9s | 92.5s | 419.4s |
| queue-r1-aba-execution | 459.8s | 95.1s | 364.6s |
| queue-r1-abb-execution | 564.8s | 134.4s | 430.5s |
| queue-r1-baa-execution | 544.2s | 105.0s | 439.1s |
| queue-r1-bab-execution | 516.2s | 113.2s | 403.0s |
| queue-r1-bba-execution | 1015.3s | 228.1s | 787.2s |
| queue-r1-bbb-execution | 658.5s | 162.7s | 495.8s |
| queue-r2-aab-execution | 634.4s | 103.9s | 530.5s |
| queue-r2-aba-execution | 575.2s | 127.7s | 447.4s |
| queue-r2-abb-execution | 639.9s | 143.3s | 496.6s |
| queue-r2-baa-execution-reviewed | 391.6s | 79.1s | 312.5s |
| queue-r2-bab-execution-reviewed | 575.1s | 146.4s | 428.7s |
| queue-r2-bba-execution-reviewed | 464.4s | 115.1s | 349.3s |
| queue-r2-bbb-execution-reviewed | 498.5s | 99.0s | 399.6s |
| queue-r2-aaa-execution | 446.3s | 92.9s | 353.4s |
| queue-r3-aba-execution-reviewed | 590.2s | 108.3s | 481.9s |
| queue-r3-abb-execution-reviewed | 468.2s | 102.3s | 365.9s |
| queue-r3-baa-execution | 667.2s | 127.0s | 540.2s |
| queue-r3-bab-execution | 683.8s | 110.9s | 573.0s |
| queue-r3-bba-execution | 673.3s | 143.9s | 529.4s |
| queue-r3-bbb-execution | 698.6s | 121.0s | 577.7s |
| queue-r3-aaa-execution-reviewed | 538.5s | 102.9s | 435.6s |
| queue-r3-aab-execution-reviewed | 533.6s | 98.7s | 434.9s |
| queue-r4-abb-execution | 616.4s | 113.5s | 502.9s |
| queue-r4-baa-execution | 470.4s | 79.5s | 390.9s |
| queue-r4-bab-execution | 554.7s | 94.8s | 460.0s |
| queue-r4-bba-execution | 452.0s | 77.9s | 374.1s |
| queue-r4-bbb-execution | 497.6s | 85.5s | 412.1s |
| queue-r4-aaa-execution | 522.1s | 56.2s | 465.9s |
| queue-r4-aab-execution | 620.1s | 73.8s | 546.3s |
| queue-r4-aba-execution | 515.4s | 26.7s | 488.7s |

The remainder includes model responses, tool execution and other overhead. Do not rank unconstrained workflow speed from this table. Request-wait sums may double-count overlapping waits; the union does not. The 30-minute phase safety cap includes queue waiting and is not an active-time budget. See [timing.json](timing.json) for provenance and exclusions.
