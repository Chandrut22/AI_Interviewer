# Interview transcript - CHANDRU T

**[0:00] Interview start** - Python Web Developer Intern (intern) - 10 minute budget

## [0:00] Topic: JWT

_priority 3, budget 3:00, target depth 3, opening difficulty 2_

**[0:00] Interviewer** (opening, difficulty 2/5, 45s): Describe the key steps you would take to generate and verify JWTs in a Python web API, including which standard claims you would include in the token payload and how you would securely manage the signing secret.

**[0:45] Candidate** (45.0s) _(timed out)_: _no answer_

> _Evaluation: 1.0/5 - No answer given within the time limit._

**[0:45] Interviewer** (opening, difficulty 2/5, 45s): What is the purpose of the 'exp' claim in a JWT, and how does a Python web API typically enforce it when verifying a token?

**[1:16] Candidate** (30.7s): The `exp` claim sets token expiration; PyJWT rejects expired tokens during verification.

> _Evaluation: 3.2/5 - Correct but overly brief; mentions exp purpose and PyJWT rejection without detailing verification steps._

**[1:16] Interviewer** (followup, difficulty 2/5, 45s): What is the purpose of the 'nbf' (Not Before) claim in a JWT, and how would a Python web API typically enforce it during token verification?

**[1:45] Candidate** (29.0s): The `nbf` claim delays token validity; PyJWT rejects tokens before that timestamp.

> _Evaluation: 3.6/5 - Correctly identifies nbf purpose and notes PyJWT enforcement but provides minimal detail._

**[1:45] Interviewer** (opening, difficulty 2/5, 45s): Explain the difference between using a symmetric signing algorithm (e.g., HS256) and an asymmetric one (e.g., RS256) for JWTs in a Python web service, and describe a scenario where you would prefer each.

**[2:06] Candidate** (21.2s): HS256 shares one secret; RS256 uses public-private keys. HS256 suits single services; RS256 suits distributed verification.

> _Evaluation: 3.2/5 - Correctly distinguishes symmetric vs asymmetric signing and gives generic use‑cases, but is shallow and lacks concrete examples._

_[2:06] End of topic: JWT - The JWT topic has reached its target depth (3/3). Although some allocated time remains, continuing would not add meaningful depth and we need to preserve time for the two remaining topics._

## [2:06] Topic: Oauth

_priority 3, budget 3:00, target depth 3, opening difficulty 2_

**[2:06] Interviewer** (opening, difficulty 2/5, 45s): Describe the sequence of HTTP requests your application makes to exchange a Google OAuth2 authorization code for an access token, and explain how you store the resulting token securely for subsequent API calls.

**[2:27] Candidate** (21.2s): Exchange authorization code via Google token endpoint; securely store access token encrypted server-side.

> _Evaluation: 3.0/5 - Brief but correct answer lacking detail and specifics._

**[2:27] Interviewer** (followup, difficulty 2/5, 45s): What role does the 'redirect_uri' parameter play in the token exchange request to Google's token endpoint, and why must it match the value used in the initial authorization request?

**[2:44] Candidate** (16.7s): It prevents redirect attacks; `redirect_uri` must match the authorization request exactly for validation.

> _Evaluation: 3.2/5 - The answer correctly notes that redirect_uri must match to prevent attacks, but provides only a minimal explanation._

**[2:44] Interviewer** (followup, difficulty 2/5, 47s): When the access token expires, describe the steps your application takes to obtain a new one using a refresh token, and detail how you store and protect that refresh token on the server.

**[3:00] Candidate** (16.1s): Send refresh token to Google’s token endpoint; securely encrypt, restrict access, rotate, and revoke when necessary.

> _Evaluation: 3.2/5 - Concise but lacks detail on the refresh flow and storage implementation._

_[3:00] End of topic: Oauth - The Oauth topic has reached its target depth (3/3) and used only a fraction of its allocated time. With ample global budget remaining and another topic pending, we should move on to the next topic._

## [3:00] Topic: MiddleWare

_priority 2, budget 3:00, target depth 2, opening difficulty 1_

**[3:00] Interviewer** (opening, difficulty 1/5, 45s): Can you explain what a FastAPI middleware is and describe how it fits into the request‑response lifecycle?

**[3:16] Candidate** (16.0s): i don't know about this topic

> _Evaluation: 1.2/5 - The candidate provided no answer and demonstrated no knowledge of FastAPI middleware._

**[3:16] Interviewer** (clarification, difficulty 1/5, 45s): Write a minimal FastAPI middleware that logs each incoming request's HTTP method and path, then adds a custom header `X-Processed: true` to the response.

**[3:31] Candidate** (15.1s): can u move on to next topic

> _Evaluation: None/5 - Candidate requested to skip the current topic._

_[3:31] End of topic: MiddleWare - Candidate requested to skip the current topic._
