# Interview transcript - CHANDRU T

**[0:00] Interview start** - Python Web Developer Intern (intern) - 10 minute budget

## [0:00] Topic: MiddleWare

_priority 4, budget 3:30, target depth 3, opening difficulty 2_

**[0:00] Interviewer** (opening, difficulty 2/5, 70s): In FastAPI, describe how you would implement a custom middleware that logs the request path and processing time for every endpoint, and explain how you would ensure it does not interfere with the framework's built‑in exception handling.

**[0:14] Candidate** (14.0s): In FastAPI, describe how you would implement a custom middleware that logs the request path and processing time for every endpoint, and explain how you would ensure it does  │
│ not interfere with the framework's built‑in exception handling. ?

**[0:14] Interviewer** (clarification, difficulty 2/5, 70s): How would you write a FastAPI middleware that logs every request's path and its processing time, and what would you do to ensure this middleware does not interfere with FastAPI's built‑in exception handling?

**[0:59] Candidate** (44.7s): do u ask about the is there any build in exception in fastapi ?

**[0:59] Interviewer** (clarification, difficulty 2/5, 70s): Design a FastAPI middleware that logs each request's path and its processing time. How would you implement it and ensure it does not interfere with FastAPI's built‑in exception handling?

**[1:20] Candidate** (21.8s): In FastAPI, describe how you would implement a custom middleware that logs the request path and processing time for every endpoint, and explain how you would ensure it does  │
│ not interfere with the framework's built‑in exception handling.

> _Evaluation: None/5 - Doubt threshold reached; moving to a new question._

**[1:20] Interviewer** (opening, difficulty 2/5, 70s): Explain how you would use FastAPI’s middleware system to add a custom header, such as X‑Request‑ID, to every response, and describe how you would test that this header is present on multiple endpoints without affecting the normal flow of requests.

**[1:53] Candidate** (32.9s): do u ask about the iddleware of system ?

> _Evaluation: None/5 - Doubt threshold reached; moving to a new question._

**[1:53] Interviewer** (opening, difficulty 2/5, 70s): Describe how you would implement a FastAPI middleware that checks for a custom header (e.g., X-Feature-Flag) and, if present, stores its value in the request state for downstream handlers. How would you ensure the middleware does not block or alter requests that do not contain this header?

**[2:38] Candidate** (44.4s): do u ask about how to implement the middleware in fastapi

> _Evaluation: None/5 - Doubt threshold reached; moving to a new question._

**[2:38] Interviewer** (opening, difficulty 2/5, 52s): Write a FastAPI middleware that checks for an API key in the `Authorization` header on every request, returns a `401 Unauthorized` response if the key is missing or invalid, and otherwise lets the request proceed—how would you implement this and ensure it does not interfere with other middleware or exception handling?

**[3:18] Candidate** (39.8s): do u ask about the how u handle the auth header ?

> _Evaluation: None/5 - Doubt threshold reached; moving to a new question._

**[3:18] Interviewer** (opening, difficulty 2/5, 45s): FastAPI allows adding middleware via the `@app.middleware('http')` decorator or by calling `app.add_middleware`. If you need a middleware that reads the request body and modifies it before passing to the route, which method would you choose and why? What are the implications for async vs sync route handlers?

**[3:46] Candidate** (28.6s): i don't know about this topic

> _Evaluation: None/5 - Candidate requested to skip the current topic._

_[3:46] End of topic: MiddleWare - Candidate cannot answer, topic not covered_

## [3:46] Topic: JWT

_priority 3, budget 2:45, target depth 2, opening difficulty 2_

**[3:46] Interviewer** (opening, difficulty 2/5, 55s): Explain how you would generate a JWT for a user login flow in a Flask application, including choosing a signing algorithm, setting claims like expiration, and ensuring the token is securely transmitted.

**[4:07] Candidate** (20.7s): i don't kown about this topic

> _Evaluation: None/5 - Candidate requested to skip the current topic._

> _[4:07] Time adjustment: Transferred 144s of unused time from JWT to Oauth._

_[4:07] End of topic: JWT - Candidate cannot engage with JWT topic, so skip._

## [4:07] Topic: Oauth

_priority 3, budget 5:09, target depth 2, opening difficulty 2_

**[4:07] Interviewer** (opening, difficulty 2/5, 55s): What are the main components of OAuth2 and how does the authorization code flow work when integrating Google OAuth2 into a Python web application?

**[4:33] Candidate** (25.7s): i dont't know about this topic

> _Evaluation: 1.0/5 - Candidate does not demonstrate knowledge of OAuth2._

> _Difficulty down: 2 -> 1. Weak answer, lower difficulty for next question._

**[4:33] Interviewer** (opening, difficulty 1/5, 55s): When implementing Google OAuth2 in a Flask application, how would you securely store and refresh the access token, and what steps would you take to handle token expiration and revocation?

**[5:05] Candidate** (32.0s): When implementing Google OAuth2 in a Flask application, how would you securely store and refresh the access token, and what steps would you take to handle token expiration   │
│ and revocation?

> _Evaluation: None/5 - Doubt threshold reached; moving to a new question._

**[5:05] Interviewer** (opening, difficulty 1/5, 55s): In a Flask application that uses Google OAuth2, explain how you would store the access and refresh tokens securely, implement automatic token refresh, and handle token revocation, ensuring that sensitive data is not exposed to the client and that the application remains responsive to token expiration.

**[5:28] Candidate** (23.7s): Encrypt tokens server-side, refresh automatically before expiry, revoke when needed, and reauthenticate on failure.

> _Evaluation: 2.8/5 - Answer covers key concepts but lacks detail._

> _Difficulty up: 1 -> 2. Answer was shallow; increase difficulty slightly._

**[5:28] Interviewer** (followup, difficulty 2/5, 55s): What table structure would you use to store encrypted tokens, how would you secure the encryption keys, and how would you programmatically refresh a token before it expires while handling revocation errors in a Flask view?

**[5:47] Candidate** (19.1s): Use a token table with encrypted credentials, KMS-managed keys, expiry timestamps, automatic refresh, and revocation-triggered reauthentication.

> _Evaluation: 3.4/5 - Candidate gave a concise but incomplete answer, covering key concepts but lacking concrete details._

**[5:47] Interviewer** (followup, difficulty 2/5, 55s): Provide the full SQL CREATE TABLE statement you would use to store encrypted OAuth tokens, including columns for user_id, access_token, refresh_token, expiry, and any necessary constraints or indices. Then give a concise Flask view snippet that checks if the stored access token is expired, refreshes it using Google’s token endpoint, updates the database record, and gracefully handles revocation errors by prompting re‑authentication.

**[6:20] Candidate** (32.8s): The table should store encrypted tokens, track expiration, and associate each token record with a user. The Flask view should refresh expired access tokens server-side and require re-authentication if Google reports that the refresh token has been revoked or invalidated.

> _Evaluation: 2.6/5 - Answer is incomplete; lacks concrete SQL and code._

> _Difficulty up: 2 -> 3._

_[6:20] End of topic: Oauth - Depth target reached and follow-ups exhausted; move to next topic_
