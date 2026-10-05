# Enterprise Google images and video in Rook

Rook uses a person's Google authorization to generate media in a firm's Google Cloud project. The firm controls access and pays for API usage in that project. Google's current documentation calls the platform **Gemini Enterprise Agent Platform**; its API service and IAM names still use `aiplatform`. A Workspace/Gemini subscription alone does not establish the project billing and IAM configuration required by this API workflow. [Google's project setup](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start).

## Who sets up what

| Item | Owner | Purpose |
|---|---|---|
| Desktop OAuth client and consent screen | Rook maintainer, or the pilot firm's administrator | Identifies the Rook application when Google asks for consent |
| Cloud project, billing, API, model access/quota | Firm administrator | Controls where generation runs and is billed |
| Google sign-in and consent | Each employee | Authorizes Rook to act with that employee's project permissions |

These can be two separate Cloud projects: the app registration identifies Rook, while the generation project belongs to the firm. Rook sends the chosen generation project explicitly in each model request. This implementation accepts a downloaded desktop client JSON file locally; automatic distribution of a centrally registered Rook client is a later packaging decision, not an implemented setup shortcut.

## First pilot: administrator's steps

For the practice pilot, use the owner's Workspace account before onboarding another firm. Keep the downloaded client JSON, account email, actual project ID, private ledger/media and unsanitized pilot logs outside both the repository and every Git worktree. A suitable Windows location is `%LOCALAPPDATA%/Rook/data/enterprise-google-pilot/`; it is not a source folder. Enter the actual project and client path only in the local Rook settings. Do not paste the client file, tokens, account identifiers or private console screenshots into chat or commit them. Committed examples and acceptance fixtures use synthetic labels such as `pilot-account-01` and `pilot-project-01`. Local acceptance source evidence and the mapping from labels to real identifiers remain private. Before any evidence is committed, scan it locally for the held credential values and account/project identifiers without printing them.

1. Select or create a firm Cloud project. Copy its **project ID**, for example `my-firm-media`, rather than its display name or numeric project number. Link billing and enable the Agent Platform API, whose service ID is `aiplatform.googleapis.com`. Confirm access/quota for the two models below. [Project setup and roles](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start).
2. Give the employee permission to generate in that project. Google's documented starting role is Agent Platform User (`roles/aiplatform.user`); an administrator can choose an equivalent restricted custom role. OAuth consent does not grant project IAM permissions. [Google IAM guidance](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/general/access-control).
3. In Google Auth Platform, configure Branding, Audience and Data Access for the OAuth app. Rook requests `https://www.googleapis.com/auth/cloud-platform`. For a pilot restricted to one Workspace organization, an Internal audience may be suitable. For people outside the registering organization, use External and add pilot test users while testing. Review Google's publication/verification requirements before distributing to firms broadly. [Consent configuration](https://developers.google.com/workspace/guides/configure-oauth-consent).
4. Create an OAuth client of type **Desktop app** and download its JSON file. Use a desktop file with an `installed` section. Rook opens the system browser and receives consent on an ephemeral localhost port using PKCE; a web-application client is unsuitable. Keep the file locally and supply its full path in Rook. [Google desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app).
5. If Workspace app controls block consent, the firm's administrator must approve the OAuth application. Rook cannot bypass that policy.

## Employee's steps in Rook

Open RookChat Settings → Enterprise Google. Read the current local settings first. Enter the firm's project ID, `us-central1` as the shared text/video location, and the full desktop JSON path. Click Connect Google account and complete the browser consent using the employee account that has project access.

Image generation uses `vertex_ai/gemini-3.1-flash-image` in `global`. Video uses `vertex_ai/veo-3.1-fast-generate-001` in `us-central1`. Choose the explicit **Google Enterprise** media entry in RookVision. Existing API-key choices retain their behavior.

The location field is shared with Vertex text and Chirp. Reading settings preserves another existing location; enabling video requires deliberately saving `us-central1`, which also changes that routing. Disconnecting, switching authorization, or saving project/location interrupts jobs bound to the previous configuration. Video Stop monitoring stops Rook locally; Google's operation may continue and incur charges.

## What we need to prove the pilot works

We will verify the installed build, then submit one image and three short videos: normal completion with token refresh, disconnect while running, and restart while running. We will check image dimensions, video decoding/duration/playback, ledger states and exact request counts. Mock tests and the memory probe are reported separately. If a video finishes before an intervention, that case is inconclusive; no extra billed submission is automatic.

The next practical setup step is choosing the pilot firm's Cloud project and who will create the desktop OAuth app. There is no need to paste authorization tokens, passwords or the client JSON contents into a chat.
