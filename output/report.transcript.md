# Interview transcript - CHANDRU T

**[0:00] Interview start** - Python Web Developer Intern (intern) - 30 minute budget

## [0:00] Topic: JSON Web Tokens (JWT)

_priority 3, budget 6:00, target depth 2, opening difficulty 2_

**[0:00] Interviewer** (opening, difficulty 2/5, 72s): Describe the three parts of a JWT and explain how each part is used when a server validates a token during an authentication request.

**[0:58] Candidate** (58.2s): Header identifies algorithm; payload stores claims; signature verifies integrity and authenticity securely.

> _Evaluation: 3.8/5 - Answer covers the basics but lacks depth and specificity._

**[0:58] Interviewer** (followup, difficulty 2/5, 75s): After decoding a JWT, what exact cryptographic operation does the server perform with the header's 'alg' and the payload to confirm the signature?

**[1:20] Candidate** (22.1s): do u mean alg is algorthim ?

> _Evaluation: None/5 - Candidate raised a doubt: User is asking for clarification about the meaning of 'alg' rather than providing an answer._

**[1:20] Interviewer** (clarification, difficulty 2/5, 93s): Explain the cryptographic steps a server performs to verify a JWT signature, including how the algorithm specified in the header is used with the header and payload.

**[2:36] Candidate** (76.2s): Server decodes header, selects algorithm, recomputes signature using header-payload, compares.

> _Evaluation: 3.4/5 - The answer is concise and relevant but lacks depth and specificity for a thorough JWT signature verification explanation._

_[2:36] End of topic: JSON Web Tokens (JWT) - Target depth 2 reached._

## [2:36] Topic: OAuth 2.0

_priority 3, budget 6:00, target depth 2, opening difficulty 2_

**[2:36] Interviewer** (opening, difficulty 2/5, 72s): What are the main components of the OAuth 2.0 flow you used with Google, and why is the authorization code grant considered more secure than the implicit grant?

**[3:25] Candidate** (48.4s): OAuth uses authorization server, client, resource server, and user; code grant protects tokens better.

> _Evaluation: 2.8/5 - Answer is on topic but lacks depth and detail, missing key security rationale for the authorization code grant._

**[3:25] Interviewer** (followup, difficulty 2/5, 77s): Explain how you used the state parameter in the OAuth 2.0 authorization code flow to guard against CSRF attacks, and describe what would happen if you omitted it.

**[4:02] Candidate** (37.5s): State links request to session, preventing CSRF; without it, attackers could inject authorization codes.

> _Evaluation: 4.0/5 - Answer correctly identifies the role of state but lacks depth and concrete detail._

_[4:02] End of topic: OAuth 2.0 - Target depth 2 reached._

## [4:02] Topic: FastAPI Middleware

_priority 3, budget 6:00, target depth 2, opening difficulty 1_

**[4:02] Interviewer** (opening, difficulty 1/5, 72s): How would you implement a FastAPI middleware that logs the request method, path, and response status code, and what considerations would you have for asynchronous operation and error handling?

**[4:40] Candidate** (38.1s): Use `@app.middleware("http")`, await `call_next`, log status, and handle exceptions safely.

> _Evaluation: 3.2/5 - Answer covers the basics but lacks depth and detail._

**[4:40] Interviewer** (followup, difficulty 1/5, 80s): When handling a streaming response in FastAPI, how would you modify your middleware to log the response status code without consuming the response body, and what pitfalls should you avoid?

**[5:20] Candidate** (39.0s): Wrap streaming body without consuming it; log status immediately, avoiding buffering, delays, and memory issues.

> _Evaluation: 3.0/5 - Answer is brief and lacks concrete implementation details, missing key pitfalls._

_[5:20] End of topic: FastAPI Middleware - Target depth 2 reached._

## [5:20] Topic: TanStack Router

_priority 3, budget 6:00, target depth 2, opening difficulty 1_

**[5:20] Interviewer** (opening, difficulty 1/5, 72s): Explain how you would set up nested routes in TanStack Router and handle data loading for a child route, including how to manage loading states and errors.

**[5:46] Candidate** (27.0s): do u mean tanstack router handing ?

> _Evaluation: None/5 - Candidate raised a doubt: The user is asking for clarification about the question, not providing an answer._

**[5:46] Interviewer** (clarification, difficulty 1/5, 83s): Describe how you would configure nested routes in TanStack Router, load data for a child route, and manage the loading and error states for that route.

**[6:13] Candidate** (26.9s): i think using the usemutation and usequery

> _Evaluation: 1.0/5 - Answer does not address the question._

**[6:13] Interviewer** (followup, difficulty 1/5, 102s): When leveraging TanStack Router’s loader functions for nested routes, how would you implement request cancellation to prevent race conditions or stale data from affecting the UI, and what trade‑offs does this approach introduce compared to ignoring cancellation?

**[6:47] Candidate** (33.4s): using the rate limiter in redis

> _Evaluation: 1.0/5 - Answer does not address the question._

**[6:47] Interviewer** (followup, difficulty 1/5, 136s): How would you cancel an in‑flight loader request in TanStack Router when a user navigates away from a nested route, and what specific hooks or utilities would you use to avoid race conditions between the cancelled request and a new one?

**[7:26] Candidate** (39.4s): do you mean about the inflight loader request working in tansstack ?

> _Evaluation: None/5 - Candidate raised a doubt: The user is asking for clarification about the question, not providing an answer._

> _Evaluation: None/5 - Doubt threshold reached; moving on from this question._

**[7:26] Interviewer** (opening, difficulty 1/5, 180s): In a TanStack Router setup with nested routes, how would you design the loader for a child route that depends on a parameter from its parent route, ensuring that the loader re‑fetches data only when that parameter changes, and how would you handle caching and stale data scenarios?

**[7:56] Candidate** (29.6s): using the props drilling

> _Evaluation: 1.0/5 - Answer does not address the question._

_[7:56] End of topic: TanStack Router - Question cap for this topic reached._

## [7:56] Topic: TanStack Query

_priority 3, budget 6:00, target depth 2, opening difficulty 1_

**[7:56] Interviewer** (opening, difficulty 1/5, 72s): Describe how you would use TanStack Query to implement infinite scrolling for a paginated API, including how you handle loading state, errors, and caching strategy.

**[8:38] Candidate** (42.6s): Use `useInfiniteQuery`, track page cursors, show loading/error states, and cache each page.

> _Evaluation: 3.2/5 - Answer is correct but lacks depth and specificity._

**[8:38] Interviewer** (followup, difficulty 1/5, 79s): How would you configure TanStack Query to retry a failed page load, including the retry count, backoff strategy, and when to stop retrying, and why did you choose those values?

**[9:12] Candidate** (33.7s): Use three retries, exponential backoff, stop on permanent errors; balances reliability and latency.

> _Evaluation: 3.6/5 - Answer is concise but lacks depth; provides basic config but no justification details._

**[9:12] Interviewer** (opening, difficulty 1/5, 94s): Suppose you have a paginated list of items fetched with TanStack Query's `useInfiniteQuery`. After a user performs a mutation that adds a new item to the list, how would you ensure the UI reflects this change without refetching the entire list, and what considerations would you make regarding cache updates and query invalidation?

**[9:56] Candidate** (44.3s): Update cached pages directly with `setQueryData`; invalidate afterward only when server consistency requires.

> _Evaluation: 3.0/5 - Answer addresses the core idea but lacks detail on pagination handling and cache strategy._

**[9:56] Interviewer** (followup, difficulty 1/5, 119s): When you use setQueryData to insert a new item into an infinite query cache, what steps would you take to update the pagination metadata—such as the next page cursor—to avoid stale or duplicate data, and how would you verify that this update works correctly in a test scenario?

**[10:50] Candidate** (53.2s): Update `pages`, recompute cursors, remove duplicates, then test cache and pagination metadata.

> _Evaluation: 2.6/5 - Answer is on topic but lacks depth and detail._

**[10:50] Interviewer** (opening, difficulty 1/5, 180s): How would you configure TanStack Query so that multiple components can consume the same paginated data without triggering duplicate network requests, while still ensuring each component’s UI updates correctly when new data arrives? Discuss the role of shared query keys, staleTime, and any cache update strategies you would employ.

**[11:36] Candidate** (46.6s): Use shared query keys, suitable `staleTime`, cached data, and targeted invalidation for synchronized updates.

> _Evaluation: 3.0/5 - Answer is relevant but too brief and lacks the detail needed to fully address the question._

**[11:36] Interviewer** (opening, difficulty 1/5, 139s): If the API provides a total item count along with each page, how would you integrate that into TanStack Query so the UI can show the total count and still support infinite scrolling without refetching? Discuss how you would store the count, update it on mutations, and what query options you would set to keep the count fresh.

**[12:12] Candidate** (35.7s): Store total count in query metadata; update mutations, use staleTime.

> _Evaluation: 2.6/5 - Answer is partially correct but lacks depth and detail._

**[12:12] Interviewer** (opening, difficulty 1/5, 103s): When using `useInfiniteQuery` to fetch a cursor‑based paginated list, how would you implement a 'refresh' button that re‑fetches only the first page while preserving the rest of the cached pages, and what query client methods would you use to achieve that?

**[13:31] Candidate** (78.7s): what u mean useInfinitequery ?

> _Evaluation: None/5 - Candidate raised a doubt: User is asking for clarification about the useInfiniteQuery concept, indicating confusion rather than providing an answer._

> _Evaluation: None/5 - Doubt threshold reached; moving on from this question._

**[13:31] Interviewer** (opening, difficulty 1/5, 45s): When using `useInfiniteQuery` for cursor‑based pagination, how would you implement optimistic updates for a delete mutation that removes an item from the cached list, ensuring the UI immediately reflects the removal while maintaining consistency with the server, and what query client methods would you use to revert the optimistic change if the mutation fails?

**[14:16] Candidate** (45.0s) _(timed out)_: _no answer_

> _Evaluation: 1.0/5 - No answer given within the time limit._

_[14:16] End of topic: TanStack Query - Topic time budget spent._
