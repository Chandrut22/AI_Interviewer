# Interview transcript - CHANDRU T

**[0:00] Interview start** - Python Web Developer Intern (intern) - 30 minute budget

## [0:00] Topic: JWT

_priority 3, budget 8:48, target depth 3, opening difficulty 2_

**[0:00] Interviewer** (opening, difficulty 2/5, 176s): How would you implement a token expiration strategy using JWT in a Python web application, and what considerations would you take into account to balance security and user experience?

**[0:39] Candidate** (39.4s): Set short-lived access tokens, secure refresh tokens, rotate them, and balance expiry with usability.

> _Evaluation: 2.6/5 - Answer is relevant but lacks depth and specificity; needs more detail._

**[0:39] Interviewer** (followup, difficulty 2/5, 176s): What specific expiration durations would you set for access and refresh tokens in a typical web application, and what factors influence those choices?

**[1:05] Candidate** (25.9s): Access tokens: 15 minutes; refresh tokens: 7–30 days, based on risk, sensitivity, and usability.

> _Evaluation: 3.8/5 - The answer correctly identifies typical expiration windows and mentions influencing factors, but lacks depth and detailed rationale._

**[1:05] Interviewer** (opening, difficulty 2/5, 176s): Describe how you would implement JWT revocation in a stateless authentication system, for example when a user logs out or changes their password, and discuss the trade‑offs of your chosen approach.

**[1:39] Candidate** (33.8s): Use Redis blocklists keyed by JWT `jti`; revoke on logout/password change, trading statelessness for security.

> _Evaluation: 3.6/5 - Answer is relevant but lacks depth and detail._

> _[1:39] Time adjustment: Transferred 428s of unused time from JWT to OAuth._

_[1:39] End of topic: JWT - Target depth reached for JWT (3/3)._

## [1:39] Topic: OAuth

_priority 3, budget 15:56, target depth 3, opening difficulty 2_

**[1:39] Interviewer** (opening, difficulty 2/5, 176s): Explain how you would implement Google OAuth2 in a Flask application, including how you would store the access token securely and handle token refresh.

**[2:04] Candidate** (25.4s): Use Authlib, exchange codes, encrypt tokens server-side, refresh expired access tokens securely.

> _Evaluation: 3.0/5 - Answer covers the basics but lacks concrete implementation details and depth._

**[2:04] Interviewer** (followup, difficulty 2/5, 176s): When persisting a Google OAuth2 access token in your Flask app’s database, which encryption algorithm would you choose, how would you manage the encryption key lifecycle, and how would you ensure the key never leaks to the application runtime environment?

**[2:22] Candidate** (17.9s): Use AES-256-GCM, manage keys via KMS with rotation, granting runtime least-privilege access.

> _Evaluation: 4.2/5 - The answer correctly identifies AES-256-GCM, KMS key rotation, and least‑privilege access, but lacks depth on implementation details._

> _Difficulty up: 2 -> 3_

**[2:22] Interviewer** (followup, difficulty 3/5, 176s): If your KMS service is temporarily unavailable, how would you ensure your application can still decrypt existing tokens and continue to operate, and what steps would you take to mitigate the risk of exposing the key during this outage?

**[2:47] Candidate** (24.6s): Use cached data keys securely, restrict access, monitor outages, and avoid plaintext key persistence.

> _Evaluation: 2.8/5 - Answer is relevant but lacks depth and specificity; it provides generic mitigation steps but no concrete fallback strategy._

> _[2:47] Time adjustment: Transferred 888s of unused time from OAuth to MiddleWare._

_[2:47] End of topic: OAuth - Target depth reached for OAuth (3/3)._

## [2:47] Topic: MiddleWare

_priority 2, budget 18:08, target depth 2, opening difficulty 1_

**[2:47] Interviewer** (opening, difficulty 1/5, 100s): Describe how you would implement a custom middleware in a Flask application to log request details and measure response time, and discuss any trade‑offs or potential performance impacts.

**[3:34] Candidate** (47.2s): Use global variables, log all request data, skip timing, and ignore performance overhead.

> _Evaluation: 1.0/5 - Answer fails to address the question and lacks necessary details._

**[3:34] Interviewer** (clarification, difficulty 1/5, 100s): Explain how you would design a Flask middleware that logs request details and measures response time, ensuring it does not introduce significant latency or race conditions in a multi-threaded environment. What considerations would you make regarding logging verbosity and timing precision?

**[4:03] Candidate** (28.4s): Use `before_request` and `after_request`, thread-safe logging, `perf_counter()`, and configurable verbosity.

> _Evaluation: 3.8/5 - Answer is relevant and correct but lacks depth and detail._

**[4:03] Interviewer** (opening, difficulty 1/5, 100s): You need to add a custom header to every response and log the size of the response body in a Flask middleware. How would you implement this so that it works correctly with streaming responses and does not interfere with the response generation? What trade‑offs would you consider regarding memory usage and performance?

**[4:31] Candidate** (28.7s): Use `after_request` to add headers and log `Content-Length`; avoid buffering streams to minimize memory overhead.

> _Evaluation: 2.8/5 - Answer is partially correct but lacks depth and specificity for streaming responses._

> _[4:31] Time adjustment: Transferred 983s of unused time from MiddleWare to TanStack Router._

_[4:31] End of topic: MiddleWare - Target depth reached for MiddleWare (2/2)._

## [4:31] Topic: TanStack Router

_priority 2, budget 19:43, target depth 2, opening difficulty 1_

**[4:31] Interviewer** (opening, difficulty 1/5, 100s): In TanStack Router, how would you configure a nested route structure for a dashboard that contains a 'profile', 'settings', and 'reports' subpage, and what are the key considerations for optimizing route loading and data fetching in this setup?

**[5:13] Candidate** (42.1s): Are you using TanStack Router with file-based routing or code-based routing?

**[5:13] Interviewer** (clarification, difficulty 1/5, 100s): Using code-based routing in TanStack Router, how would you set up a nested route hierarchy for a dashboard that includes 'profile', 'settings', and 'reports' subpages, and what key considerations should you keep in mind for optimizing route loading and data fetching in this setup?

**[5:35] Candidate** (22.0s): Use `createRoute` with a dashboard parent, nested child routes, lazy loading, and route-level data loaders.

> _Evaluation: 3.0/5 - Answer is brief but touches on key concepts; however, it lacks detail and concrete examples._

**[5:35] Interviewer** (followup, difficulty 1/5, 100s): What are the trade‑offs between lazy loading the 'reports' component versus prefetching it when the dashboard is first loaded, and how would you decide which approach to use?

**[5:58] Candidate** (22.8s): Do you want a code-based implementation or a conceptual explanation?

**[5:58] Interviewer** (clarification, difficulty 1/5, 100s): Explain how you would configure a nested route hierarchy for a dashboard that includes 'profile', 'settings', and 'reports' subpages using TanStack Router, and discuss the trade‑offs between lazy loading the 'reports' component versus prefetching it when the dashboard is first loaded, including key considerations for route loading and data fetching.

**[6:34] Candidate** (36.3s): Using TanStack Router, I would create a parent dashboard route with nested profile, settings, and reports routes. Lazy-load reports to reduce initial bundle size, or prefetch it for faster navigation. Use route loaders, caching, and parallel fetching to optimize performance.

> _Evaluation: 3.6/5 - Answer covers the basics but lacks depth and concrete details._

> _[6:34] Time adjustment: Transferred 1059s of unused time from TanStack Router to TanStack Query._

_[6:34] End of topic: TanStack Router - Target depth reached for TanStack Router (2/2)._

## [6:34] Topic: TanStack Query

_priority 2, budget 20:59, target depth 2, opening difficulty 1_

**[6:34] Interviewer** (opening, difficulty 1/5, 100s): When using TanStack Query in a React application, how would you handle a scenario where you need to fetch data from two related endpoints that depend on each other's responses, and you want to avoid unnecessary refetches when the data changes? Describe the approach and any relevant hooks or options you would use.

**[7:28] Candidate** (53.9s): Do the two endpoints have a strict dependency, or can they be fetched in parallel?

> _Evaluation: None/5 - Doubt threshold reached; moving to a new question._

**[7:28] Interviewer** (opening, difficulty 1/5, 100s): Assuming the second endpoint requires data from the first, how would you use TanStack Query hooks and options to fetch both endpoints efficiently, ensuring that the second query only runs after the first succeeds and that unnecessary refetches are avoided when the data changes?

**[8:07] Candidate** (38.7s): i don'tknow

> _Evaluation: 1.0/5 - Answer does not address the question._

**[8:07] Interviewer** (clarification, difficulty 1/5, 100s): Explain how you would implement optimistic updates for a mutation that modifies data fetched by a TanStack Query, and how you would keep the cache in sync with the server while handling potential errors.

**[8:17] Candidate** (9.8s): i don't know

> _Evaluation: 1.0/5 - Answer does not address the question._

_[8:17] End of topic: TanStack Query - Moving on from TanStack Query: candidate received depth 1 on two consecutive answers._
