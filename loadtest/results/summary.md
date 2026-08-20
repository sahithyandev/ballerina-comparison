| Stack | Endpoint | Req/s | Avg | Fastest | Slowest | Total | Status codes |
|---|---|---|---|---|---|---|---|
| go | GET /posts/{id} | 4327.0714 | 0.0116s | 0.0019s | 0.0402s | 30.0060s | 200x129838 |
| go | POST /posts | 4033.6122 | 0.0025s | 0.0004s | 0.0379s | 10.0015s | 201x40342 |
| ballerina | GET /posts/{id} | 3478.8055 | 0.0144s | 0.0037s | 0.1482s | 30.0097s | 200x104398 |
| ballerina | POST /posts | 1545.9387 | 0.0029s | 0.0005s | 0.1015s | 20.0034s | 201x30923 |
